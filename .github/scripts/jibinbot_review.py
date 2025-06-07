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
BASE_REF      = os.getenv("GITHUB_BASE_REF")  # target branch (e.g., 'main')

if not OPENAI_API_KEY or not AI_TOKEN or not BASE_REF:
    print("⛔️ Missing one of OPENAI_API_KEY, GITHUB_TOKEN, or GITHUB_BASE_REF.")
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
        "> Thank you! No changes detected. Ready for merge! 🎉"
    )
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI code-review",
        state="success",
        description="✅ No changes detected. All clear for merge."
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

reports_dir          = Path('.github/linter-reports')
eslint_report        = load_json_if_exists(reports_dir / 'eslint.json')
flake8_report        = load_json_if_exists(reports_dir / 'flake8.json')
shellcheck_report    = load_json_if_exists(reports_dir / 'shellcheck.json')
dartanalyzer_report  = load_json_if_exists(reports_dir / 'dartanalyzer.json')
dotnet_report        = load_json_if_exists(reports_dir / 'dotnet-format.json')

# ── 5) HELPER TO READ A SPECIFIC LINE FROM DISK ────────────────────────
def get_original_line(path: str, line_no: int) -> str:
    try:
        with open(path, 'r') as f:
            lines = f.readlines()
            if 1 <= line_no <= len(lines):
                return lines[line_no - 1].rstrip("\n")
    except Exception:
        pass
    return ""

# ── 6) AI SUGGEST FIX & REFACTOR FUNCTIONS ─────────────────────────────
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

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful Dart/Flutter assistant."},
            {"role": "user",   "content": prompt}
        ],
        temperature=0.0,
        max_tokens=60
    )
    return response.choices[0].message.content.strip().strip("```dart").strip("```")


def ai_refactor_suggestion(code_block: str, file_path: str) -> str:
    prompt = dedent(f"""
        You are a senior software engineer. Refactor the following code snippet
        from `{file_path}` for clarity, maintainability, and best practices.

        ```
        {code_block}
        ```

        Provide only the refactored code without explanation.
    """).strip()

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a senior code reviewer."},
            {"role": "user",   "content": prompt}
        ],
        temperature=0.2,
        max_tokens=300
    )
    return response.choices[0].message.content.strip().strip("```")

# ── 7) EXTRACT NEW CODE BLOCKS FROM DIFF ──────────────────────────────
def extract_new_code_blocks() -> list[dict]:
    blocks = []
    for file_path in changed_files:
        try:
            diff = subprocess.check_output(
                ['git', 'diff', f'origin/{BASE_REF}', full_sha, '--', file_path],
                text=True,
                errors='ignore'
            )
            current = []
            for line in diff.splitlines():
                if line.startswith('+') and not line.startswith('+++'):
                    current.append(line[1:])
                else:
                    if current:
                        blocks.append({'file': file_path, 'code': '\n'.join(current)})
                        current = []
            if current:
                blocks.append({'file': file_path, 'code': '\n'.join(current)})
        except Exception as e:
            print(f"⚠️ Could not diff {file_path}: {e}")
    return blocks

# ── 8) EXTRACT ALL ISSUES FROM LINTER/ANALYZER JSONS ──────────────────
issues: list[dict] = []

# — ESLint
if isinstance(eslint_report, list):
    for file_report in eslint_report:
        abs_path = file_report.get('filePath')
        if not abs_path:
            continue
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path.startswith('.github/') or rel_path not in changed_files:
            continue
        for msg in file_report.get('messages', []):
            line     = msg.get('line')
            code     = msg.get('ruleId') or 'ESLint'
            text     = msg.get('message') or ''
            severity = msg.get('severity', 0)
            sev_text = 'Error' if severity == 2 else 'Warning'
            if line:
                issues.append({
                    'file': rel_path,
                    'line': line,
                    'code': code,
                    'message': f"{sev_text}: [{code}] {text}"
                })

# — Flake8
if isinstance(flake8_report, dict):
    for abs_path, errors in flake8_report.items():
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path.startswith('.github/') or rel_path not in changed_files:
            continue
        for err in errors:
            line = err.get('line_number') or err.get('line')
            code = err.get('code') or ''
            text = err.get('text') or ''
            if line:
                issues.append({
                    'file': rel_path,
                    'line': line,
                    'code': code,
                    'message': f"Warning: [{code}] {text}"
                })

# — ShellCheck
if isinstance(shellcheck_report, list):
    for entry in shellcheck_report:
        abs_path = entry.get('file')
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path.startswith('.github/') or rel_path not in changed_files:
            continue
        line = entry.get('line')
        code = entry.get('code') or ''
        text = entry.get('message') or ''
        if line:
            issues.append({
                'file': rel_path,
                'line': line,
                'code': code,
                'message': f"Warning: [{code}] {text}"
            })

# — Dart Analyzer
if isinstance(dartanalyzer_report, dict):
    for diag in dartanalyzer_report.get('diagnostics', []):
        loc      = diag.get('location', {})
        abs_path = loc.get('file')
        if not abs_path:
            continue
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path.startswith('.github/') or rel_path not in changed_files:
            continue
        line       = loc.get('range', {}).get('start', {}).get('line')
        code       = diag.get('code') or 'DartAnalyzer'
        text       = diag.get('problemMessage') or diag.get('message') or ''
        severity   = diag.get('severity')
        sev_text   = 'Error' if severity == 'ERROR' else 'Warning' if severity == 'WARNING' else 'Info'
        if line is not None:
            issues.append({
                'file': rel_path,
                'line': line,
                'code': code,
                'message': f"{sev_text}: [{code}] {text}"
            })

# — .NET Format
if isinstance(dotnet_report, dict):
    diags = dotnet_report.get('Diagnostics') or dotnet_report.get('diagnostics')
    if isinstance(diags, list):
        for d in diags:
            abs_path = d.get('Path') or d.get('path')
            rel_path = os.path.relpath(abs_path, start=os.getcwd())
            if rel_path.startswith('.github/') or rel_path not in changed_files:
                continue
            line = d.get('Region', {}).get('StartLine') or d.get('region', {}).get('startLine')
            message = d.get('Message') or d.get('message') or ''
            if line is not None:
                issues.append({
                    'file': rel_path,
                    'line': line,
                    'code': 'DotNetFormat',
                    'message': f"Warning: {message}"
                })

# ── 9) ORGANIZE ISSUES & BUILD MARKDOWN ─────────────────────────────
file_to_issues: dict[str, list[dict]] = {}
for issue in issues:
    file_to_issues.setdefault(issue['file'], []).append(issue)

md = ["## 🤖 brandOptics AI – Automated Code Review Suggestions\n"]

if issues:
    total_issues   = len(issues)
    files_affected = len(file_to_issues)
    md.append(f"⚠️ **Overall Summary:** {total_issues} issue{'s' if total_issues != 1 else ''} across {files_affected} file{'s' if files_affected != 1 else ''}.\n")
    md.append("### Index of Affected Files")
    for fp in sorted(file_to_issues.keys()):
        count = len(file_to_issues[fp])
        anchor = fp.lower().replace('/', '').replace('.', '')
        md.append(f"- [{fp}](#{anchor}) — {count} issue{'s' if count != 1 else ''}")
    md.append("")

    for fp, fis in sorted(file_to_issues.items()):
        anchor = fp.lower().replace('/', '').replace('.', '')
        md.append(f"### File: `{fp}`\n<a name=\"{anchor}\"></a>")
        md.append("| Line | Lint / Diagnostic | Original Code | Suggested Fix |")
        md.append("|:----:|:----------------:|:-------------:|:-------------:|")
        for issue in sorted(fis, key=lambda x: x['line']):
            ln = issue['line']
            code = issue['code']
            msg  = issue['message']
            orig = get_original_line(fp, ln).replace('`', '\`').replace('|', '\|')
            sugg = ai_suggest_fix(code, orig, fp, ln).replace('`', '\`').replace('|', '\|')
            md.append(f"| {ln} | `{code}`<br>{msg} | `{orig}` | `{sugg}` |")
        md.append("")
else:
    md.append("🎉 **No lint or analysis issues detected.** All clear!\n")

# ── 10) ADD PROFESSIONAL REFACTORING SUGGESTIONS ─────────────────────
new_blocks = extract_new_code_blocks()
if new_blocks:
    md.append("## 💡 Professional Refactoring Suggestions\n")
    for blk in new_blocks:
        refactored = ai_refactor_suggestion(blk['code'], blk['file'])
        md.append(f"### File: `{blk['file']}`\n```dart\n{refactored}\n```\n")

summary_body = "\n".join(md)

# ── 11) POST COMMENT & SET STATUS ────────────────────────────────────
pr.create_issue_comment(summary_body)
if issues:
    pr.create_review(
        body=(f"🤖 **brandOptics AI Neural Intelligence Engine** found {total_issues} issue{'s' if total_issues != 1 else ''} across {files_affected} file{'s' if files_affected != 1 else ''}."),
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

print(f"brandOptics AI has posted a consolidated code review on PR #{pr_number}.")