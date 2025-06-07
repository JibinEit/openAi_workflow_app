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
        Return only a markdown table row with pipes, four columns: issue, original, suggestion, rationale.
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
        return f"| {code} | {original} | _AI error_ | {e} |"

# ── 7) COLLECT ISSUES FROM REPORTS ─────────────────────────────────────
issues = []
# (Parse eslint_report, flake8_report, shellcheck_report, dartanalyzer_report, dotnet_report similarly, filtering on file_changes)
# ... [parsing logic remains unchanged] ...

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
            ln   = i['line']
            code = i['code']
            orig = get_original_line(file, ln).replace("|", "\\|")
            patch = file_changes.get(file, '').splitlines()[0]
            row  = ai_suggest_fix(code, orig, file, ln, patch)
            # split and merge suggestion + rationale
            parts = [p.strip() for p in row.strip().strip("|").split("|")]
            issue_label = parts[0] if parts else code
            suggestion = parts[2] + (": " + parts[3] if len(parts)>3 else "")
            md.append(f"| {ln} | `{issue_label}` | `{orig}` | {suggestion} |")
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