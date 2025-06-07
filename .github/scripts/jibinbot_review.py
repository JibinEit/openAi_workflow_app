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

# ── 2) READ THE PULL REQUEST PAYLOAD ────────────────────────────────────
with open(EVENT_PATH, "r") as f:
    event = json.load(f)

pr_number = event["pull_request"]["number"]
full_sha  = event["pull_request"]["head"]["sha"]
repo      = gh.get_repo(REPO_NAME)
pr        = repo.get_pull(pr_number)

# ── 3) GATHER CHANGED FILES → exit if none, skip .github ─────────────
changed_files = [f.filename for f in pr.get_files()
                 if f.patch and not f.filename.lower().startswith('.github/')]
if not changed_files:
    pr.create_issue_comment(
        "🤖 brandOptics AI Neural Intelligence Review:\n"
        "> No relevant code changes detected (excluding .github). 🎉"
    )
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI code-review",
        state="success",
        description="✅ No relevant code changes detected."
    )
    exit(0)

# ── 4) LOAD LINTER/ANALYZER REPORTS ────────────────────────────────────
def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except:
        return None

reports_dir = Path('.github/linter-reports')
eslint_report       = load_json(reports_dir / 'eslint.json')
flake8_report       = load_json(reports_dir / 'flake8.json')
shellcheck_report   = load_json(reports_dir / 'shellcheck.json')
dartanalyzer_report = load_json(reports_dir / 'dartanalyzer.json')
dotnet_report       = load_json(reports_dir / 'dotnet-format.json')

# ── 5) READ ORIGINAL CODE LINE ─────────────────────────────────────────
def get_original_line(path, line_no):
    try:
        with open(path) as f:
            return f.readlines()[line_no-1].rstrip('\n')
    except:
        return ''

# ── 6) EXTRACT DIFF CONTEXT ────────────────────────────────────────────
def get_patch_context(patch, target_line, ctx=3):
    lines = patch.splitlines()
    hunk = []
    file_line = None
    for l in lines:
        if l.startswith('@@'):
            parts = l.split()[2]
            start = int(parts.split(',')[0][1:])
            file_line = start - 1
            hunk = [l]
        elif file_line is not None:
            if l.startswith((' ', '+')):
                file_line += 1
            if abs(file_line - target_line) <= ctx:
                hunk.append(l)
            if file_line > target_line + ctx:
                break
    return '\n'.join(hunk)

# ── 7) AI SUGGESTION ───────────────────────────────────────────────────
def ai_suggest_fix(code, patch_ctx, path, line_no):
    prompt = dedent(f"""
You are a Dart/Flutter expert.
Below is the changed code section from `{path}` around line {line_no} causing `{code}`:
```diff
{patch_ctx}
```
Provide:
1. Fix: copy-friendly snippet
2. Refactor: best-practice improvements
3. Why: brief rationale
Output only labeled sections.
""")
    try:
        resp = openai.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role':'system','content':'You are a helpful assistant.'},
                {'role':'user','content':prompt}
            ],
            temperature=0.0,
            max_tokens=300
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"AI failed: {e}\n{patch_ctx}"

# ── 8) AGGREGATE ISSUES ────────────────────────────────────────────────
issues = []

# — ESLint
if isinstance(eslint_report, list):
    for file_report in eslint_report:
        file_path = os.path.relpath(file_report.get('filePath', ''), start=os.getcwd())
        if file_path in changed_files:
            for msg in file_report.get('messages', []):
                line = msg.get('line')
                if line:
                    issues.append({
                        'file': file_path,
                        'line': line,
                        'code': msg.get('ruleId', 'ESLint'),
                        'message': msg.get('message', '')
                    })

# — Flake8
if isinstance(flake8_report, dict):
    for abs_path, errors in flake8_report.items():
        file_path = os.path.relpath(abs_path, start=os.getcwd())
        if file_path in changed_files:
            for err in errors:
                ln = err.get('line_number') or err.get('line')
                if ln:
                    issues.append({
                        'file': file_path,
                        'line': ln,
                        'code': err.get('code', 'Flake8'),
                        'message': err.get('text', '')
                    })

# — ShellCheck
if isinstance(shellcheck_report, list):
    for entry in shellcheck_report:
        file_path = os.path.relpath(entry.get('file', ''), start=os.getcwd())
        line = entry.get('line')
        if file_path in changed_files and line:
            issues.append({
                'file': file_path,
                'line': line,
                'code': entry.get('code', 'ShellCheck'),
                'message': entry.get('message', '')
            })

# — Dart Analyzer
if isinstance(dartanalyzer_report, dict):
    for diag in dartanalyzer_report.get('diagnostics', []):
        loc = diag.get('location', {})
        file_path = os.path.relpath(loc.get('file', ''), start=os.getcwd())
        ln = loc.get('range', {}).get('start', {}).get('line')
        if file_path in changed_files and ln:
            issues.append({
                'file': file_path,
                'line': ln,
                'code': diag.get('code', 'DartAnalyzer'),
                'message': diag.get('problemMessage') or diag.get('message', '')
            })

# — .NET Format
if isinstance(dotnet_report, dict):
    diags = dotnet_report.get('Diagnostics') or dotnet_report.get('diagnostics')
    if isinstance(diags, list):
        for d in diags:
            file_path = os.path.relpath(d.get('Path', '') or d.get('path', ''), start=os.getcwd())
            ln = d.get('Region', {}).get('StartLine')
            if file_path in changed_files and ln:
                issues.append({
                    'file': file_path,
                    'line': ln,
                    'code': 'DotNetFormat',
                    'message': d.get('Message', '')
                })

# ── 9) GROUP BY FILE ──────────────────────────────────────────────────
file_groups = {}
for issue in issues:
    file_groups.setdefault(issue['file'], []).append(issue)

# ── 10) BUILD COMMENT ─────────────────────────────────────────────────
sections = []
for file_path, its in sorted(file_groups.items()):
    sections.append(f"**File =>** `{file_path}`")
    sections.append("")
    sections.append("| Line number | Issue | Suggested Fix by AI |")
    sections.append("|:-----------:|:------|:---------------------|")
    gh_file = next(f for f in pr.get_files() if f.filename == file_path)
    patch = gh_file.patch or ''
    for it in sorted(its, key=lambda x: x['line']):
        ln = it['line']
        issue_txt = f"`{it['code']}` {it['message']}"
        ctx = get_patch_context(patch, ln)
        ai_out = ai_suggest_fix(it['code'], ctx, file_path, ln)
        fix_match = re.search(r'Fix:\s*(```[\s\S]*?```|[^\n]+)', ai_out)
        fix_snip = fix_match.group(1).strip() if fix_match else it['message']
        if not fix_snip.startswith('```'):
            fix_cell = f'```dart\n{fix_snip}\n```'
        else:
            fix_cell = fix_snip
        sections.append(f"| {ln} | {issue_txt} | {fix_cell} |")
    sections.append("")

if not sections:
    sections = ['🎉 No issues detected. Ready to merge! 🎉']

comment_body = '\n'.join(['## 🤖 brandOptics AI Review Suggestions', ''] + sections)

# ── 11) POST & STATUS ─────────────────────────────────────────────────
pr.create_issue_comment(comment_body)
repo.get_commit(full_sha).create_status(
    context='brandOptics AI code-review',
    state='failure' if issues else 'success',
    description='🚧 Issues detected—please refine your code.' if issues else '✅ No code issues detected.'
)
print(f"Posted AI review for PR #{pr_number}")