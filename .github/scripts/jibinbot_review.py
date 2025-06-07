#!/usr/bin/env python3
import os
import json
import re
from pathlib import Path
from textwrap import dedent

import openai
from github import Github

# ── 1) SETUP ──────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
REPO_NAME      = os.getenv("GITHUB_REPOSITORY")
EVENT_PATH     = os.getenv("GITHUB_EVENT_PATH")
if not OPENAI_API_KEY or not GITHUB_TOKEN:
    print("⛔️ Missing OpenAI or GitHub token.")
    exit(1)
openai.api_key = OPENAI_API_KEY
gh = Github(GITHUB_TOKEN)

# ── 2) LOAD PR DATA ────────────────────────────────────────────────────
with open(EVENT_PATH) as f:
    event = json.load(f)
pr_number = event["pull_request"]["number"]
full_sha  = event["pull_request"]["head"]["sha"]
repo      = gh.get_repo(REPO_NAME)
pr        = repo.get_pull(pr_number)

# ── 3) DETECT CHANGED FILES (exclude .github/) ─────────────────────────
changed_files = [f.filename for f in pr.get_files()
                 if f.patch and not f.filename.lower().startswith('.github/')]
if not changed_files:
    pr.create_issue_comment(
        "🤖 brandOptics AI Review — no relevant code changes detected."
    )
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI code-review",
        state="success",
        description="✅ No relevant code changes detected."
    )
    exit(0)

# ── 4) LOAD LINTER REPORTS ─────────────────────────────────────────────
def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except:
        return None

reports_dir = Path('.github/linter-reports')
elsint_report       = load_json(reports_dir / 'eslint.json')
flake8_report       = load_json(reports_dir / 'flake8.json')
shellcheck_report   = load_json(reports_dir / 'shellcheck.json')
dartanalyzer_report = load_json(reports_dir / 'dartanalyzer.json')
dotnet_report       = load_json(reports_dir / 'dotnet-format.json')

# ── 5) HELPERS ─────────────────────────────────────────────────────────
def get_patch_context(patch: str, line_no: int, ctx: int = 3) -> str:
    file_line = None
    hunk = []
    for l in patch.splitlines():
        if l.startswith('@@ '):
            parts = l.split()
            start_info = parts[2]  # e.g. +12,7
            file_line = int(start_info.split(',')[0][1:]) - 1
            hunk = [l]
        elif file_line is not None:
            prefix = l[:1]
            if prefix in (' ', '+', '-'):
                if prefix != '-':
                    file_line += 1
                if abs(file_line - line_no) <= ctx:
                    hunk.append(l)
                if file_line > line_no + ctx:
                    break
    return "\n".join(hunk)

# ── 6) AI SUGGESTION ───────────────────────────────────────────────────
def ai_suggest_fix(code: str, patch_ctx: str, file_path: str, line_no: int) -> str:
    prompt = dedent(f"""
You are a Dart/Flutter expert.
Below is the diff around line {line_no} in `{file_path}` (error: {code}):
```diff
{patch_ctx}
```
Provide exactly three labeled sections:

Fix:
  Copy-friendly corrected snippet (include fences if multi-line).
Refactor:
  Higher-level best-practice improvements.
Why:
  Brief rationale.
""")
    resp = openai.chat.completions.create(
        model='gpt-4o-mini',
        messages=[
            {'role': 'system', 'content': 'You are a helpful assistant.'},
            {'role': 'user',   'content': prompt}
        ],
        temperature=0.0,
        max_tokens=400
    )
    return resp.choices[0].message.content.strip()

# ── 7) COLLECT ISSUES ──────────────────────────────────────────────────
issues = []

# ESLint
if isinstance(eslint_report, list):
    for rep in eslint_report:
        path = os.path.relpath(rep.get('filePath', ''), start=os.getcwd())
        if path in changed_files:
            for msg in rep.get('messages', []):
                ln = msg.get('line')
                if ln:
                    issues.append({
                        'file': path,
                        'line': ln,
                        'code': msg.get('ruleId', 'ESLint'),
                        'message': msg.get('message', '')
                    })

# Flake8
if isinstance(flake8_report, dict):
    for abs_path, errs in flake8_report.items():
        path = os.path.relpath(abs_path, start=os.getcwd())
        if path in changed_files:
            for err in errs:
                ln = err.get('line_number') or err.get('line')
                if ln:
                    issues.append({
                        'file': path,
                        'line': ln,
                        'code': err.get('code', 'Flake8'),
                        'message': err.get('text', '')
                    })

# ShellCheck
if isinstance(shellcheck_report, list):
    for entry in shellcheck_report:
        path = os.path.relpath(entry.get('file', ''), start=os.getcwd())
        ln = entry.get('line')
        if path in changed_files and ln:
            issues.append({
                'file': path,
                'line': ln,
                'code': entry.get('code', 'ShellCheck'),
                'message': entry.get('message', '')
            })

# Dart Analyzer
if isinstance(dartanalyzer_report, dict):
    for diag in dartanalyzer_report.get('diagnostics', []):
        loc = diag.get('location', {})
        path = os.path.relpath(loc.get('file', ''), start=os.getcwd())
        ln = loc.get('range', {}).get('start', {}).get('line')
        if path in changed_files and ln:
            issues.append({
                'file': path,
                'line': ln,
                'code': diag.get('code', 'DartAnalyzer'),
                'message': diag.get('problemMessage') or diag.get('message', '')
            })

# .NET Format
if isinstance(dotnet_report, dict):
    diags = dotnet_report.get('Diagnostics') or dotnet_report.get('diagnostics')
    if isinstance(diags, list):
        for d in diags:
            path = os.path.relpath(d.get('Path') or d.get('path', ''), start=os.getcwd())
            ln = d.get('Region', {}).get('StartLine')
            if path in changed_files and ln:
                issues.append({
                    'file': path,
                    'line': ln,
                    'code': 'DotNetFormat',
                    'message': d.get('Message', '')
                })

# ── 8) GROUP BY FILE & FORMAT OUTPUT ─────────────────────────────────
file_groups = {}
for issue in issues:
    file_groups.setdefault(issue['file'], []).append(issue)

md = ['## 🤖 brandOptics AI Review Suggestions', '']
for fs, iss in sorted(file_groups.items()):
    md.append(f"**File =>** `{fs}`")
    md.append('')
    # Table header
    md.append('| Line | Issue | Fix (summary) |')
    md.append('|:----:|:------|:--------------|')
    ghf = next(f for f in pr.get_files() if f.filename == fs)
    patch = ghf.patch or ''
    details = []
    for it in sorted(iss, key=lambda x: x['line']):
        ln = it['line']
        issue_md = f"`{it['code']}` {it['message']}"
        ctx = get_patch_context(patch, ln)
        ai_out = ai_suggest_fix(it['code'], ctx, fs, ln)
        # Extract full Fix block
        m = re.search(r'Fix:\s*```dart([\s\S]*?)```', ai_out)
        full_fix = m.group(1).strip() if m else ai_out.splitlines()[0].strip()
        summary = full_fix.splitlines()[0].strip().replace('|', '\\|')
        md.append(f"| {ln} | {issue_md} | `{summary}` |")
        details.append((ln, full_fix, ai_out))
    md.append('')
    # Append collapsible details
    for ln, full_fix, ai_out in details:
        md.append(f"<details><summary>Full fix for line {ln}</summary>")
        md.append('```dart')
        md.append(full_fix)
        md.append('```')
        # Refactor & Why
        ref = re.search(r'Refactor:\s*([\s\S]*?)(?=\nWhy:|$)', ai_out)
        why = re.search(r'Why:\s*([\s\S]*)', ai_out)
        if ref:
            md.append('**Refactor:**')
            md.append(ref.group(1).strip())
        if why:
            md.append('**Why:**')
            md.append(why.group(1).strip())
        md.append('</details>')
        md.append('')
if not issues:
    md.append('🎉 No issues detected. Ready to merge! 🎉')

# ── 9) POST COMMENT & STATUS ───────────────────────────────────────────
body = '\n'.join(md)
pr.create_issue_comment(body)
repo.get_commit(full_sha).create_status(
    context='brandOptics AI code-review',
    state='failure' if issues else 'success',
    description='🚧 Issues detected—please refine your code.' if issues else '✅ No code issues detected.'
)
print(f"Posted AI review for PR #{pr_number}")