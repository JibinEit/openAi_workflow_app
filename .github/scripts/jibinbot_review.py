#!/usr/bin/env python3
import os
import json
import re
from pathlib import Path
from textwrap import dedent

import openai
from github import Github

# ── 1) ENVIRONMENT & CLIENT SETUP ───────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AI_TOKEN      = os.getenv("GITHUB_TOKEN")
REPO_NAME      = os.getenv("GITHUB_REPOSITORY")
EVENT_PATH     = os.getenv("GITHUB_EVENT_PATH")

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
    pr.create_issue_comment("👀 brandOptics AI: No textual changes detected—nothing to review.")
    repo.get_commit(full_sha).create_status(
    context="brandOptics AI 🤖/code-review",
    state="success",
    description="✅ brandOptics AI: No issues detected. Ready to merge! 🎉🚀"
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

reports_dir       = Path(".github/linter-reports")
eslint_report     = load_json_if_exists(reports_dir / "eslint.json")
flake8_report     = load_json_if_exists(reports_dir / "flake8.json")
shellcheck_report = load_json_if_exists(reports_dir / "shellcheck.json")
dartanalyzer_report = load_json_if_exists(reports_dir / "dartanalyzer.json")
dotnet_report     = load_json_if_exists(reports_dir / "dotnet-format.json")

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
    """
    Ask GPT-4o-mini to rewrite just the offending Dart line so it no
    longer triggers the lint/diagnostic. Return only the corrected snippet.
    """
    prompt = dedent(f"""
        You are a Dart/Flutter expert. Below is a single line of Dart code
        from file `{file_path}`, line {line_no}, which triggers lint/analysis
        error `{code}`:

        ```dart
        {original}
        ```

        Rewrite just that line (or minimal snippet) to satisfy the lint/diagnostic.
        Output only the corrected code with appropriate quoting or
        definitions—no extra explanation.
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
        # Strip triple backticks if present
        return re.sub(r"^```dart\s*|\s*```$", "", suggestion).strip()
    except Exception as e:
        return f"# (AI request failed: {e})\n{original}"

# ── 7) EXTRACT ALL ISSUES FROM LINTER/ANALYZER JSONs ──────────────────
issues: list[dict] = []

# — ESLint
if isinstance(eslint_report, list):
    for file_report in eslint_report:
        abs_path = file_report.get("filePath")
        if not abs_path:
            continue
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path not in changed_files:
            continue
        for msg in file_report.get("messages", []):
            line     = msg.get("line")
            code     = msg.get("ruleId") or ""
            text     = msg.get("message") or ""
            severity = msg.get("severity", 0)
            sev_text = "Error" if severity == 2 else "Warning"
            full_msg = f"{sev_text}: [{code}] {text}"
            if line:
                issues.append({
                    "file":    rel_path,
                    "line":    line,
                    "code":    code or "ESLint",
                    "message": full_msg
                })

# — Flake8
if isinstance(flake8_report, dict):
    for abs_path, errors in flake8_report.items():
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path not in changed_files:
            continue
        for err in errors:
            line = err.get("line_number") or err.get("line") or None
            code = err.get("code") or ""
            text = err.get("text") or ""
            if line:
                issues.append({
                    "file":   rel_path,
                    "line":   line,
                    "code":   code,
                    "message": f"Warning: [{code}] {text}"
                })

# — ShellCheck
if isinstance(shellcheck_report, list):
    for entry in shellcheck_report:
        abs_path = entry.get("file")
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path not in changed_files:
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

# — Dart Analyzer (use "diagnostics" key) 
if isinstance(dartanalyzer_report, dict):
    for diag in dartanalyzer_report.get("diagnostics", []):
        loc      = diag.get("location", {})
        abs_path = loc.get("file")
        if not abs_path:
            continue
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path not in changed_files:
            continue
        range_info = loc.get("range", {}).get("start", {})
        line       = range_info.get("line")
        code       = diag.get("code") or "DartAnalyzer"
        text       = diag.get("problemMessage") or diag.get("message") or ""
        severity   = diag.get("severity", "")
        sev_text   = (
            "Error"   if severity == "ERROR" else
            "Warning" if severity == "WARNING" else
            "Info"
        )
        if line:
            issues.append({
                "file":    rel_path,
                "line":    line,
                "code":    code,
                "message": f"{sev_text}: [{code}] {text}"
            })

# — .NET Format
if isinstance(dotnet_report, dict):
    diags = dotnet_report.get("Diagnostics") or dotnet_report.get("diagnostics")
    if isinstance(diags, list):
        for d in diags:
            abs_path = d.get("Path") or d.get("path") or ""
            rel_path = os.path.relpath(abs_path, start=os.getcwd())
            if rel_path not in changed_files:
                continue
            region  = d.get("Region") or d.get("region") or {}
            line    = region.get("StartLine") or region.get("startLine") or None
            message = d.get("Message") or d.get("message") or ""
            if line:
                issues.append({
                    "file":   rel_path,
                    "line":   line,
                    "code":   "DotNetFormat",
                    "message": f"Warning: {message}"
                })

# ── 8) BUILD A PER-FILE TABLE IN MARKDOWN (using inline code only) ─────
file_to_issues: dict[str, list[dict]] = {}
for issue in issues:
    file_to_issues.setdefault(issue["file"], []).append(issue)

md = ["## 🤖 brandOptics AI – Automated Code Review Suggestions\n"]

for file_path, file_issues in file_to_issues.items():
    md.append(f"### File: `{file_path}`\n")
    # Table header (blank line before / after to ensure proper rendering)
    md.append("")  
    md.append("| Line | Lint / Diagnostic                         | Original Code                           | Suggested Fix                              |")
    md.append("|:----:|:-------------------------------------------|:----------------------------------------|:--------------------------------------------|")

    for issue in sorted(file_issues, key=lambda x: x["line"]):
        ln       = issue["line"]
        code     = issue["code"]
        msg      = issue["message"]
        original = get_original_line(file_path, ln).strip()
        suggested = ai_suggest_fix(code, original, file_path, ln).splitlines()[0].strip()

        # Escape any backticks or pipes inside the code snippet
        orig_escaped = original.replace("`", "\\`").replace("|", "\\|")
        sugg_escaped = suggested.replace("`", "\\`").replace("|", "\\|")

        # Now wrap each single‐line snippet in single backticks
        lint_cell = f"`{code}`<br>{msg}"
        orig_cell = f"`{orig_escaped}`"
        sugg_cell = f"`{sugg_escaped}`"

        md.append(f"|  {ln}   | {lint_cell} | {orig_cell} | {sugg_cell} |")

    md.append("")  # blank line after each table

if not issues:
    md.append("No lint or analyzer issues found.\n")

summary_body = "\n".join(md)

# ── 9) POST THE COMMENT & SET STATUS ───────────────────────────────────
pr.create_issue_comment(summary_body)

if issues:
    # 1) Leave a “Request changes” review on the PR
# First, compute a brief high-level summary of total issues
total_issues = len(issues)
files_affected = len(file_to_issues)

# Build an overall summary string
overall_summary = (
    f"⚠️ **Overall Summary:** {total_issues} issue"
    f"{'s' if total_issues != 1 else ''} found across {files_affected} file"
    f"{'s' if files_affected != 1 else ''}."
)

# Now create the review with summary + detailed instructions
pr.create_review(
    body=f"""
{overall_summary}

✨🚫 **Hey there! brandOptics AI spotted some critical issues that need your attention before merging.** ✨

> Please review the table above for details. Below is what you’ll need to do:
>
> • **Fix Syntax Errors**  
> • **Address Lint Warnings**  
> • **Remove Unused or Undefined Symbols**

Once you’ve applied these corrections and pushed a new commit, this check will pass and the merge button will be enabled.

If you have any questions about the suggestions or need clarification on a particular issue, feel free to ask! 😊
""",
    event="REQUEST_CHANGES"
)
    # 2) Then set the failing status so branch protection will block merging
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI 🤖/code-review",
        state="failure",
        description="❌🤖 Serious code issues detected! Please fix before merging. 🔧🚫"
    )
else:
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI 🤖/code-review",
        state="success",
        description="✅🤖 No code issues detected. Ready to merge! 🎉🚀"
    )

print(f"🤖✨ brandOptics AI has 🚀 posted a sparkling code review summary on this PR! 🎉🔍✨ #{pr_number}.")