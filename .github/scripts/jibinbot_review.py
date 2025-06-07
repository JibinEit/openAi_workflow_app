#!/usr/bin/env python3
import os
import json
import re
import difflib
from pathlib import Path
from textwrap import dedent

import openai
from github import Github

# ── 1) ENVIRONMENT & CLIENT SETUP ───────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AI_TOKEN      = os.getenv("GITHUB_TOKEN")
REPO_NAME     = os.getenv("GITHUB_REPOSITORY")
EVENT_PATH    = os.getenv("GITHUB_EVENT_PATH")

if not OPENAI_API_KEY or not AI_TOKEN:
    print("⛔️ Missing either OPENAI_API_KEY or GITHUB_TOKEN.")
    exit(1)

openai.api_key = OPENAI_API_KEY
gh = Github(AI_TOKEN)

# ── 2) READ THE PULL REQUEST PAYLOAD ────────────────────────────────────
with open(EVENT_PATH, "r") as f:
    event = json.load(f)

pr_number = event["pull_request"]["number"]
full_sha  = event["pull_request"]["head"]["sha"]
repo      = gh.get_repo(REPO_NAME)
pr        = repo.get_pull(pr_number)

# ── 3) GATHER CHANGED FILES → if no changes, exit early ─────────────────
changed_files = [f.filename for f in pr.get_files() if f.patch]
if not changed_files:
    pr.create_issue_comment(
        "🤖 brandOptics AI Neural Intelligence Review:\n"
        "> Thank you for your contribution! I’ve examined the changes and found no textual updates requiring attention. Your submission is polished and ready for merge! 🎉"
    )
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI code-review",
        state="success",
        description="✅ No text changes detected. All clear for merge."
    )
    exit(0)

# ── 4) LOAD LINTER/ANALYZER JSONS ──────────────────────────────────────
def load_json_if_exists(path: Path):
    if path.exists():
        text = path.read_text().strip()
        if text:
            try:
                return json.loads(text)
            except Exception as e:
                print(f"⚠️ Failed to parse JSON from {path}: {e}")
                return None
        return None
    return None

reports_dir          = Path(".github/linter-reports")
eslint_report        = load_json_if_exists(reports_dir / "eslint.json")
flake8_report        = load_json_if_exists(reports_dir / "flake8.json")
shellcheck_report    = load_json_if_exists(reports_dir / "shellcheck.json")
dartanalyzer_report  = load_json_if_exists(reports_dir / "dartanalyzer.json")
dotnet_report        = load_json_if_exists(reports_dir / "dotnet-format.json")

# ── 5) HELPER TO READ A SPECIFIC LINE FROM DISK ────────────────────────
def get_original_line(path: str, line_no: int) -> str:
    try:
        with open(path, "r") as f:
            lines = f.readlines()
            if 1 <= line_no <= len(lines):
                return lines[line_no - 1].rstrip("\n")
    except Exception:
        pass
    return ""

# ── 6) HELPER TO EXTRACT DIFF HUNK CONTEXT ─────────────────────────────
def get_patch_context(patch: str, target_line: int, context: int = 3) -> str:
    """
    Extracts the unified-diff hunk around `target_line` from the given `patch`,
    including `context` lines above and below.
    """
    lines = patch.splitlines()
    hunk = []
    current_file_line = None
    for l in lines:
        if l.startswith("@@"):
            # parse hunk header: @@ -old,+new @@
            plus_info = l.split()[2]  # e.g. '+12,8'
            start, _ = plus_info[1:].split(",")
            current_file_line = int(start) - 1
            hunk = [l]
        elif current_file_line is not None:
            prefix = l[:1]
            if prefix in (" ", "+"):
                current_file_line += 1
            if abs(current_file_line - target_line) <= context:
                hunk.append(l)
            if current_file_line > target_line + context:
                break
    return "\n".join(hunk)

# ── 7) AI SUGGESTION WITH CONTEXTUAL PROMPT ────────────────────────────
def ai_suggest_fix(code: str, patch_context: str, file_path: str, line_no: int) -> str:
    prompt = dedent(f"""
        You are a Dart/Flutter expert.
        Below is the *full changed code section* (with context) from file `{file_path}`, around line {line_no}, which triggers lint/analysis error `{code}`:
        ```diff
        {patch_context}
        ```
        Please provide three sections:
        1. **Fix:** A corrected version of the changed snippet.
        2. **Refactor:** Any higher-level refactor or best-practice improvement.
        3. **Why:** A brief explanation of what you did and why.
        Output only these labeled sections with no extra commentary.
    """).strip()

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful Dart/Flutter assistant."},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.0,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"# (AI request failed: {e})\n{patch_context}"

# ── 8) EXTRACT ALL ISSUES FROM LINTER/ANALYZER JSONs ──────────────────
issues: list[dict] = []

# — ESLint
if isinstance(eslint_report, list):
    for file_report in eslint_report:
        abs_path = file_report.get("filePath")
        if not abs_path:
            continue
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path.startswith(".github/") or rel_path not in changed_files:
            continue
        for msg in file_report.get("messages", []):
            line     = msg.get("line")
            code     = msg.get("ruleId") or "ESLint"
            text     = msg.get("message") or ""
            severity = msg.get("severity", 0)
            sev_text = "Error" if severity == 2 else "Warning"
            if line:
                issues.append({"file": rel_path, "line": line, "code": code, "message": f"{sev_text}: [{code}] {text}"})

# — Flake8
if isinstance(flake8_report, dict):
    for abs_path, errors in flake8_report.items():
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path.startswith(".github/") or rel_path not in changed_files:
            continue
        for err in errors:
            line = err.get("line_number") or err.get("line")
            code = err.get("code") or "Flake8"
            text = err.get("text") or ""
            if line:
                issues.append({"file": rel_path, "line": line, "code": code, "message": f"Warning: [{code}] {text}"})

# — ShellCheck
if isinstance(shellcheck_report, list):
    for entry in shellcheck_report:
        abs_path = entry.get("file")
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path.startswith(".github/") or rel_path not in changed_files:
            continue
        line = entry.get("line")
        code = entry.get("code") or "ShellCheck"
        text = entry.get("message") or ""
        if line:
            issues.append({"file": rel_path, "line": line, "code": code, "message": f"Warning: [{code}] {text}"})

# — Dart Analyzer
if isinstance(dartanalyzer_report, dict):
    for diag in dartanalyzer_report.get("diagnostics", []):
        loc      = diag.get("location", {})
        abs_path = loc.get("file")
        if not abs_path:
            continue
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path.startswith(".github/") or rel_path not in changed_files:
            continue
        range_info = loc.get("range", {}).get("start", {})
        line       = range_info.get("line")
        code       = diag.get("code") or "DartAnalyzer"
        text       = diag.get("problemMessage") or diag.get("message") or ""
        severity   = diag.get("severity")
        sev_text   = "Error" if severity == "ERROR" else "Warning" if severity == "WARNING" else "Info"
        if line:
            issues.append({"file": rel_path, "line": line, "code": code, "message": f"{sev_text}: [{code}] {text}"})

# — .NET Format
if isinstance(dotnet_report, dict):
    diags = dotnet_report.get("Diagnostics") or dotnet_report.get("diagnostics")
    if isinstance(diags, list):
        for d in diags:
            abs_path = d.get("Path") or d.get("path")
            rel_path = os.path.relpath(abs_path, start=os.getcwd())
            if rel_path.startswith(".github/") or rel_path not in changed_files:
                continue
            region  = d.get("Region") or d.get("region")
            line    = region.get("StartLine") or region.get("startLine")
            message = d.get("Message") or d.get("message")
            if line:
                issues.append({"file": rel_path, "line": line, "code": "DotNetFormat", "message": f"Warning: {message}"})

# ── 9) ORGANIZE ISSUES BY FILE ─────────────────────────────────────────
file_to_issues: dict[str, list[dict]] = {}
for issue in issues:
    file_to_issues.setdefault(issue["file"], []).append(issue)

# ── 10) BUILD INDEX & TABLES ──────────────────────────────────────────
md = ["## 🤖 brandOptics AI – Automated Code Review Suggestions\n"]
if issues:
    total_issues   = len(issues)
    files_affected = len(file_to_issues)

    md.append(f"⚠️ **Overall Summary:** {total_issues} issue{'s' if total_issues != 1 else ''} found across {files_affected} file{'s' if files_affected != 1 else ''}.\n")
    md.append("### Index of Affected Files")
    for file_path in sorted(file_to_issues.keys()):
        count = len(file_to_issues[file_path])
        anchor = file_path.lower().replace("/", "").replace(".", "")
        md.append(f"- [{file_path}](#{anchor}) — {count} issue{'s' if count != 1 else ''}")
    md.append("")
    for file_path, file_issues in sorted(file_to_issues.items()):
        anchor = file_path.lower().replace("/", "").replace(".", "")
        md.append(f"### File: `{file_path}`\n<a name=\"{anchor}\"></a>")
        md.append("| Line | Diagnostic | Suggested Fix (AI) |")
        md.append("|:----:|:-----------|:-------------------|")
        gh_file = next(f for f in pr.get_files() if f.filename == file_path)
        patch   = gh_file.patch or ""
        for issue in sorted(file_issues, key=lambda x: x["line"]):
            ln        = issue["line"]
            ctx       = get_patch_context(patch, ln, context=4)
            suggestion= ai_suggest_fix(issue["code"], ctx, file_path, ln).replace("`", "\\`")
            md.append(f"| {ln} | {issue['message']} | `{suggestion}` |")
        md.append("")
else:
    md.append("🎉 **brandOptics AI Neural Intelligence Review:** No issues detected. Your code is impeccable—ready for prime time!\n")
summary_body = "\n".join(md)

# ── 11) POST COMMENT & SET STATUS ──────────────────────────────────────
pr.create_issue_comment(summary_body)
if issues:
    pr.create_review(
        body=(
            f"🤖 **brandOptics AI Neural Intelligence Engine** has identified **{total_issues} issue{'s' if total_issues != 1 else ''}** across **{files_affected} file{'s' if files_affected != 1 else ''}**.  \n"
            "Your effort is truly appreciated—let’s refine these details together. 😊\n\n"
            "> **Next Steps:**  \n"
            "> • Resolve syntax errors  \n"
            "> • Address lint warnings  \n"
            "> • Remove unused or undefined symbols  \n\n"
            "Once these adjustments are applied and a new commit is pushed, your merge request will shine with approval."
        ),
        event="REQUEST_CHANGES"
    )
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI code-review",
        state="failure",
        description="🚧 Issues detected—please refine your code and push updates."
    )
else:
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI code-review",
        state="success",
        description="✅ No code issues detected. Ready to merge!"
    )
print(f"brandOptics AI has posted a consolidated code review summary on this PR! #{pr_number}.")