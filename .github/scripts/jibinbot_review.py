#!/usr/bin/env python3
import os
import json
import re
import subprocess
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

reports_dir          = Path(".github/linter-reports")
eslint_report        = load_json_if_exists(reports_dir / "eslint.json") or []
flake8_report        = load_json_if_exists(reports_dir / "flake8.json") or {}
shellcheck_report    = load_json_if_exists(reports_dir / "shellcheck.json") or []
dartanalyzer_report  = load_json_if_exists(reports_dir / "dartanalyzer.json") or {}
dotnet_report        = load_json_if_exists(reports_dir / "dotnet-format.json") or {}

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

# ── 6) CALL OPENAI FOR A “BETTER” SUGGESTION ────────────────────────────
def ai_suggest_fix(code: str, original: str, file_path: str, line_no: int) -> str:
    prompt = dedent(f"""
        You are a Dart/Flutter expert. Below is a single line of Dart code
        from file `{file_path}`, line {line_no}, which triggers lint/analysis
        error `{code}`:

        ```dart
        {original}
        ```

        Rewrite just that line (or minimal snippet) to satisfy the lint/diagnostic.
        Output only the corrected code—no extra explanation.
    """).strip()

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful Dart/Flutter assistant."},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.0,
            max_tokens=60
        )
        suggestion = response.choices[0].message.content.strip()
        return re.sub(r"^```dart\s*|\s*```$", "", suggestion).strip()
    except Exception as e:
        return original

# ── 7) EXTRACT ALL ISSUES FROM LINTER/ANALYZER JSONs ──────────────────
issues: list[dict] = []

# — ESLint
if isinstance(eslint_report, list):
    for file_report in eslint_report:
        abs_path = file_report.get("filePath") or ""
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
                issues.append({
                    "file":    rel_path,
                    "line":    line,
                    "code":    code,
                    "message": f"{sev_text}: [{code}] {text}"
                })

# — Flake8
if isinstance(flake8_report, dict):
    for abs_path, errors in flake8_report.items():
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path.startswith(".github/") or rel_path not in changed_files:
            continue
        for err in errors:
            line = err.get("line_number") or err.get("line")
            code = err.get("code") or ""
            text = err.get("text") or ""
            if line:
                issues.append({
                    "file": rel_path,
                    "line": line,
                    "code": code,
                    "message": f"Warning: [{code}] {text}"
                })

# — ShellCheck
if isinstance(shellcheck_report, list):
    for entry in shellcheck_report:
        abs_path = entry.get("file") or ""
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path.startswith(".github/") or rel_path not in changed_files:
            continue
        line = entry.get("line")
        code = entry.get("code") or ""
        text = entry.get("message") or ""
        if line:
            issues.append({
                "file":    rel_path,
                "line":    line,
                "code":    code,
                "message": f"Warning: [{code}] {text}"
            })

# — Dart Analyzer
if isinstance(dartanalyzer_report, dict):
    for diag in dartanalyzer_report.get("diagnostics", []):
        loc      = diag.get("location", {})
        abs_path = loc.get("file") or ""
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path.startswith(".github/") or rel_path not in changed_files:
            continue
        line     = loc.get("range", {}).get("start", {}).get("line")
        code     = diag.get("code") or "DartAnalyzer"
        text     = diag.get("problemMessage") or diag.get("message") or ""
        severity = diag.get("severity", "")
        sev_text = "Error" if severity == "ERROR" else "Warning" if severity == "WARNING" else "Info"
        if line is not None:
            issues.append({
                "file":    rel_path,
                "line":    line,
                "code":    code,
                "message": f"{sev_text}: [{code}] {text}"
            })

# — .NET Format
if isinstance(dotnet_report, dict):
    diags = dotnet_report.get("Diagnostics") or dotnet_report.get("diagnostics") or []
    for d in diags:
        abs_path = d.get("Path") or d.get("path") or ""
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path.startswith(".github/") or rel_path not in changed_files:
            continue
        region  = d.get("Region") or d.get("region") or {}
        line    = region.get("StartLine") or region.get("startLine")
        message = d.get("Message") or d.get("message") or ""
        if line is not None:
            issues.append({
                "file":    rel_path,
                "line":    line,
                "code":    "DotNetFormat",
                "message": f"Warning: {message}"
            })

# ── 8) ORGANIZE ISSUES BY FILE ─────────────────────────────────────────
file_to_issues: dict[str, list[dict]] = {}
for issue in issues:
    file_to_issues.setdefault(issue["file"], []).append(issue)

# ── 9) BUILD INDEX WITH ISSUE COUNTS & DETAILED TABLES ─────────────────
md = ["## 🤖 brandOptics AI – Automated Code Review Suggestions\n"]
if issues:
    total_issues   = len(issues)
    files_affected = len(file_to_issues)
    md.append(f"⚠️ **Overall Summary:** {total_issues} issue{'s' if total_issues != 1 else ''} across {files_affected} file{'s' if files_affected != 1 else ''}.\n")
    md.append("### Index of Affected Files\n")
    for file_path in sorted(file_to_issues.keys()):
        count  = len(file_to_issues[file_path])
        anchor = file_path.lower().replace("/", "").replace(".", "")
        md.append(f"- [{file_path}](#{anchor}) — {count} issue{'s' if count != 1 else ''}")
    md.append("")
    for file_path, file_issues in sorted(file_to_issues.items()):
        anchor = file_path.lower().replace("/", "").replace(".", "")
        md.append(f"### File: `{file_path}`\n<a name=\"{anchor}\"></a>")
        md.append("| Line | Rule                   | Original Code                | Suggested Fix               |")
        md.append("|:----:|:-----------------------|:-----------------------------|:----------------------------|")
        for issue in sorted(file_issues, key=lambda x: x["line"]):
            ln        = issue["line"]
            code      = issue["code"]
            msg       = issue["message"]
            original  = get_original_line(file_path, ln).strip().replace("`","\\`").replace("|","\\|")
            suggestion= ai_suggest_fix(code, original, file_path, ln).replace("`","\\`").replace("|","\\|")
            md.append(f"| {ln} | `{code}`<br>{msg} | `{original}` | `{suggestion}` |")
        md.append("")
else:
    md.append("🎉 **No issues detected.** Your code is impeccable—ready for prime time!\n")

summary_body = "\n".join(md)

# ── 10) PROFESSIONAL CODE REVIEW SUGGESTIONS ─────────────────────────────
# Extract new code blocks via git diff against PR base
base_sha = event["pull_request"]["base"]["sha"]
prof_blocks: dict[str, list[str]] = {}
for f in changed_files:
    try:
        diff = subprocess.check_output(
            ['git', 'diff', base_sha, full_sha, '--', f],
            text=True, errors='ignore'
        )
        buf = []
        for line in diff.splitlines():
            if line.startswith('+') and not line.startswith('+++'):
                buf.append(line[1:])
            elif buf:
                prof_blocks.setdefault(f, []).append("\n".join(buf))
                buf = []
        if buf:
            prof_blocks.setdefault(f, []).append("\n".join(buf))
    except Exception:
        continue

if prof_blocks:
    md.append("\n---\n## 💼 Professional Code Review Suggestions")
    md.append("\nHigh-level suggestions on clarity, structure, and best practices for your new changes:")
    md.append("| File | Suggestions |")
    md.append("|:-----|:------------|")
    for fpath, blocks in prof_blocks.items():
        code_snippet = "\n\n".join(blocks)
        prompt = dedent(f"""
            You are a senior software engineer. Review the following new code from `{fpath}` and suggest concise, high-level improvements for readability, maintainability, and adherence to professional best practices. Output as a bullet list.

            ```dart
            {code_snippet}
            ```
        """)
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a senior software engineer."},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        suggestions = resp.choices[0].message.content.strip().replace("|","\\|")
        md.append(f"| {fpath} | {suggestions} |")

# ── 11) POST THE COMMENT & SET STATUS ──────────────────────────────────
pr.create_issue_comment("\n".join(md))

if issues:
    pr.create_review(
        body=(
            f"🤖 **brandOptics AI Neural Intelligence Engine** found **{total_issues} issue"
            f"{'s' if total_issues!=1 else ''}** across **{files_affected} file"
            f"{'s' if files_affected!=1 else ''}**. Please see suggestions above."
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