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
REPO_NAME     = os.getenv("GITHUB_REPOSITORY")
EVENT_PATH    = os.getenv("GITHUB_EVENT_PATH")

if not OPENAI_API_KEY or not AI_TOKEN:
    print("⛔️ Missing either OPENAI_API_KEY or GITHUB_TOKEN.")
    exit(1)

openai.api_key = OPENAI_API_KEY
gh = Github(AI_TOKEN)

# ── 2) READ THE PULL REQUEST PAYLOAD ───────────────────────────────────
with open(EVENT_PATH, "r") as f:
    event = json.load(f)

pr_number = event["pull_request"]["number"]
full_sha  = event["pull_request"]["head"]["sha"]
repo      = gh.get_repo(REPO_NAME)
pr        = repo.get_pull(pr_number)

# ── 3) GATHER CHANGED FILES AND PATCHES ─────────────────────────────────
file_changes = {f.filename: f.patch for f in pr.get_files() if f.patch}
if not file_changes:
    pr.create_issue_comment(
        "🤖 brandOptics AI Neural Intelligence Review:\n"
        "> No textual changes detected — code is ready for merge! 🎉"
    )
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI code-review",
        state="success",
        description="✅ No changes detected. All clear."
    )
    exit(0)

# ── 4) LOAD LINTER/ANALYZER REPORTS ────────────────────────────────────
def load_json_if_exists(path: Path):
    if path.exists():
        text = path.read_text().strip()
        if text:
            try:
                return json.loads(text)
            except Exception as e:
                print(f"⚠️ Failed to parse JSON from {path}: {e}")
    return None

reports_dir         = Path(".github/linter-reports")
eslint_report       = load_json_if_exists(reports_dir / "eslint.json")
flake8_report       = load_json_if_exists(reports_dir / "flake8.json")
shellcheck_report   = load_json_if_exists(reports_dir / "shellcheck.json")
dartanalyzer_report = load_json_if_exists(reports_dir / "dartanalyzer.json")
dotnet_report       = load_json_if_exists(reports_dir / "dotnet-format.json")

# ── 5) HELPER TO READ ORIGINAL LINE ─────────────────────────────────────
def get_original_line(path: str, line_no: int) -> str:
    try:
        with open(path, "r") as f:
            lines = f.readlines()
            if 1 <= line_no <= len(lines):
                return lines[line_no - 1].rstrip("\n")
    except Exception:
        pass
    return ""

# ── 6) AI SUGGESTION WITH EXTENDED CONTEXT & BEST PRACTICES ─────────────
def ai_suggest_fix(code: str, original: str, file_path: str, line_no: int, patch: str) -> str:
    prompt = dedent(f"""
        You are a Dart/Flutter expert reviewing this PR. Below is the complete git diff for `{file_path}`:

        ```diff
        {patch}
        ```

        The diagnostic `{code}` was raised at line {line_no} on this original code:
        ```dart
        {original}
        ```

        Considering overall code context and best practices, suggest a precise fix and explain why it's optimal.
        Return only a markdown table row with pipes and four columns: issue, original, suggestion, rationale.
    """)
    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful Dart/Flutter assistant."},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.0,
            max_tokens=300
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"| `{code}` | `{original}` | _AI error_ | `{e}` |"

# ── 7) COLLECT ISSUES FROM REPORTS ─────────────────────────────────────
issues = []

# ESLint
if isinstance(eslint_report, list):
    for file_report in eslint_report:
        abs_path = file_report.get("filePath")
        rel_path = os.path.relpath(abs_path, start=os.getcwd()) if abs_path else None
        if rel_path and rel_path in file_changes:
            for msg in file_report.get("messages", []):
                line = msg.get("line")
                code = msg.get("ruleId") or "ESLint"
                text = msg.get("message")
                sev  = "Error" if msg.get("severity") == 2 else "Warning"
                if line:
                    issues.append({"file": rel_path, "line": line, "code": code, "message": f"{sev}: {text}"})

# Flake8
if isinstance(flake8_report, dict):
    for abs_path, errs in flake8_report.items():
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path in file_changes:
            for err in errs:
                line = err.get("line_number") or err.get("line")
                code = err.get("code")
                text = err.get("text")
                if line:
                    issues.append({"file": rel_path, "line": line, "code": code, "message": f"Warning: {text}"})

# ShellCheck
if isinstance(shellcheck_report, list):
    for entry in shellcheck_report:
        abs_path = entry.get("file")
        rel_path = os.path.relpath(abs_path, start=os.getcwd()) if abs_path else None
        if rel_path and rel_path in file_changes:
            line = entry.get("line")
            code = entry.get("code")
            text = entry.get("message")
            if line:
                issues.append({"file": rel_path, "line": line, "code": code, "message": f"Warning: {text}"})

# Dart Analyzer
if isinstance(dartanalyzer_report, dict):
    for diag in dartanalyzer_report.get("diagnostics", []):
        loc = diag.get("location", {}).get("range", {}).get("start", {})
        abs_path = diag.get("location", {}).get("file")
        rel_path = os.path.relpath(abs_path, start=os.getcwd()) if abs_path else None
        line = loc.get("line")
        code = diag.get("code") or "DartAnalyzer"
        text = diag.get("problemMessage") or diag.get("message")
        if rel_path in file_changes and line:
            issues.append({"file": rel_path, "line": line, "code": code, "message": text})

# .NET Format
if isinstance(dotnet_report, dict):
    diags = dotnet_report.get("Diagnostics") or dotnet_report.get("diagnostics")
    if isinstance(diags, list):
        for d in diags:
            abs_path = d.get("Path") or d.get("path")
            rel_path = os.path.relpath(abs_path, start=os.getcwd()) if abs_path else None
            region = d.get("Region") or d.get("region")
            line = region.get("StartLine") or region.get("startLine")
            msg = d.get("Message") or d.get("message")
            if rel_path in file_changes and line:
                issues.append({"file": rel_path, "line": line, "code": "DotNetFormat", "message": msg})

# ── 8) ORGANIZE & POST REVIEW ──────────────────────────────────────────
md = ["## 🤖 brandOptics AI – Automated Code Review Suggestions", ""]
if issues:
    files = sorted({i['file'] for i in issues})
    md.append(f"⚠️ **Found {len(issues)} issues across {len(files)} file{'s' if len(files)!=1 else ''}.**")
    md.append("")
    for file in files:
        md.append(f"**File => {file}**")
        md.append("")
        md.append("| Line No | Issue | Original code | AI Suggestions |")
        md.append("|:-------:|:------|:--------------|:---------------|")
        for i in sorted([x for x in issues if x['file']==file], key=lambda x: x['line']):
            ln = i['line']
            code = i['code']
            orig = get_original_line(file, ln).replace("|", "\\|")
            patch = file_changes.get(file, '').splitlines()[0]
            row = ai_suggest_fix(code, orig, file, ln, patch)
            # Normalize row
            cols = [c.strip() for c in row.strip().strip('|').split('|')]
            issue_col = cols[0] if cols else code
            suggestion_col = cols[2] if len(cols)>2 else ''
            rationale_col = cols[3] if len(cols)>3 else ''
            ai_sugg = f"{suggestion_col}"  # includes rationale if desired
            md.append(f"| {ln} | `{issue_col}` | `{orig}` | {ai_sugg} |")
        md.append("")
    body = "\n".join(md)
    pr.create_issue_comment(body)
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI code-review",
        state="failure",
        description="🚧 Issues detected — please refine your code."
    )
else:
    pr.create_issue_comment(
        "🎉 **brandOptics AI Review:** No issues detected. Ready to merge!"
    )
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI code-review",
        state="success",
        description="✅ No issues found."
    )

print(f"Posted automated review summary on PR #{pr_number}.")