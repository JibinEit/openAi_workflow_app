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
    print("⛔️ Missing OpenAI or GitHub token.")
    exit(1)

openai.api_key = OPENAI_API_KEY
gh = Github(AI_TOKEN)

# ── 2) READ THE PULL REQUEST PAYLOAD ────────────────────────────────────
with open(EVENT_PATH) as f:
    event = json.load(f)
pr_number = event["pull_request"]["number"]
full_sha  = event["pull_request"]["head"]["sha"]
repo      = gh.get_repo(REPO_NAME)
pr        = repo.get_pull(pr_number)

# ── 3) GATHER CHANGED FILES (excluding .github/) ─────────────────────────
changed_files = [f.filename for f in pr.get_files()
                 if f.patch and not f.filename.lower().startswith('.github/')]
if not changed_files:
    pr.create_issue_comment(
        "🤖 brandOptics AI Review — No relevant code changes detected (excluding .github). 🎉"
    )
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI code-review",
        state="success",
        description="✅ No relevant code changes detected."
    )
    exit(0)

# ── 4) LOAD LINTER/ANALYZER REPORTS ────────────────────────────────────
def load_json(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            print(f"⚠️ Failed to parse JSON: {path}")
    return None

reports_dir = Path('.github/linter-reports')
eslint_report        = load_json(reports_dir / 'eslint.json')
flake8_report        = load_json(reports_dir / 'flake8.json')
shellcheck_report    = load_json(reports_dir / 'shellcheck.json')
dartanalyzer_report  = load_json(reports_dir / 'dartanalyzer.json')
dotnet_report        = load_json(reports_dir / 'dotnet-format.json')

# ── 5) HELPER: READ ORIGINAL SOURCE LINE ─────────────────────────────────
def get_original_line(path: str, line_no: int) -> str:
    try:
        with open(path) as f:
            lines = f.readlines()
            return lines[line_no-1].rstrip('\n') if 1 <= line_no <= len(lines) else ''
    except Exception:
        return ''

# ── 6) HELPER: EXTRACT DIFF CONTEXT ─────────────────────────────────────
def get_patch_context(patch: str, target_line: int, ctx: int = 3) -> str:
    lines = patch.splitlines()
    file_line = None
    hunk = []
    for l in lines:
        if l.startswith('@@'):  # new hunk
            parts = l.split()[2]  # +start,count
            file_line = int(parts.split(',')[0][1:]) - 1
            hunk = [l]
        elif file_line is not None:
            prefix = l[:1]
            if prefix in (' ', '+'):
                file_line += 1
            if abs(file_line - target_line) <= ctx:
                hunk.append(l)
            if file_line > target_line + ctx:
                break
    return '\n'.join(hunk)

# ── 7) AI SUGGESTION ───────────────────────────────────────────────────
def ai_suggest_fix(code: str, ctx_patch: str, file_path: str, line_no: int) -> str:
    prompt = dedent(f"""
You are a Dart/Flutter expert.
Below is a diff around line {line_no} in `{file_path}` (error: {code}):
```diff
{ctx_patch}
```
Please provide three labeled sections:

Fix:
  A copy-friendly corrected snippet (include fences if multi-line).
Refactor:
  Higher-level best-practice improvements.
Why:
  A brief rationale.

Output only these sections, exactly as labeled.
""")
    response = openai.chat.completions.create(
        model='gpt-4o-mini',
        messages=[
            {'role': 'system', 'content': 'You are a helpful Dart/Flutter assistant.'},
            {'role': 'user',   'content': prompt}
        ],
        temperature=0.0,
        max_tokens=400
    )
    return response.choices[0].message.content.strip()

# ── 8) AGGREGATE ISSUES ────────────────────────────────────────────────
issues = []
# ESLint
if isinstance(eslint_report, list):
    for rep in eslint_report:
        p = os.path.relpath(rep.get('filePath',''))
        if p in changed_files:
            for msg in rep.get('messages', []):
                ln = msg.get('line')
                if ln:
                    issues.append({
                        'file': p, 'line': ln,
                        'code': msg.get('ruleId','ESLint'),
                        'message': msg.get('message','')
                    })
# Flake8
if isinstance(flake8_report, dict):
    for ap, errs in flake8_report.items():
        p = os.path.relpath(ap)
        if p in changed_files:
            for e in errs:
                ln = e.get('line_number') or e.get('line')
                if ln:
                    issues.append({
                        'file': p, 'line': ln,
                        'code': e.get('code','Flake8'),
                        'message': e.get('text','')
                    })
# ShellCheck
if isinstance(shellcheck_report, list):
    for ent in shellcheck_report:
        p = os.path.relpath(ent.get('file',''))
        ln = ent.get('line')
        if p in changed_files and ln:
            issues.append({
                'file': p, 'line': ln,
                'code': ent.get('code','ShellCheck'),
                'message': ent.get('message','')
            })
# Dart Analyzer
if isinstance(dartanalyzer_report, dict):
    for d in dartanalyzer_report.get('diagnostics', []):
        loc = d.get('location', {})
        p   = os.path.relpath(loc.get('file',''))
        ln  = loc.get('range',{}).get('start',{}).get('line')
        if p in changed_files and ln:
            issues.append({
                'file': p, 'line': ln,
                'code': d.get('code','DartAnalyzer'),
                'message': d.get('problemMessage') or d.get('message','')
            })
# .NET Format
if isinstance(dotnet_report, dict):
    diags = dotnet_report.get('Diagnostics') or dotnet_report.get('diagnostics')
    if isinstance(diags, list):
        for d in diags:
            p  = os.path.relpath(d.get('Path') or d.get('path',''))
            ln = d.get('Region',{}).get('StartLine')
            if p in changed_files and ln:
                issues.append({
                    'file': p, 'line': ln,
                    'code': 'DotNetFormat',
                    'message': d.get('Message','')
                })

# ── 9) GROUP ISSUES BY FILE ───────────────────────────────────────────
file_to_issues = {}
for issue in issues:
    file_to_issues.setdefault(issue['file'], []).append(issue)

# ── 10) BUILD COMMENT BODY ───────────────────────────────────────────
md = ['## 🤖 brandOptics AI Review Suggestions', '']
for file_path, file_issues in sorted(file_to_issues.items()):
    md.append(f"**File =>** `{file_path}`")
    md.append('')
    md.append('| Line number | Issue | Suggested Fix by AI |')
    md.append('|:-----------:|:------|:---------------------|')
    gh_file = next(f for f in pr.get_files() if f.filename == file_path)
    patch   = gh_file.patch or ''
    for issue in sorted(file_issues, key=lambda x: x['line']):
        ln      = issue['line']
        msg     = f"`{issue['code']}` {issue['message']}"
        ctx     = get_patch_context(patch, ln)
        ai_resp = ai_suggest_fix(issue['code'], ctx, file_path, ln)
        # extract Fix section (including fences if present)
        match = re.search(r'Fix:\s*(```[\s\S]*?```|.+)', ai_resp)
        fix_content = match.group(1).strip() if match else ''
        md.append(f"| {ln} | {msg} | {fix_content} |")
    md.append('')
if not file_to_issues:
    md.append('🎉 No issues detected. Ready to merge! 🎉')

body = '\n'.join(md)

# ── 11) POST COMMENT & SET STATUS ────────────────────────────────────
pr.create_issue_comment(body)
state = 'failure' if issues else 'success'
repo.get_commit(full_sha).create_status(
    context='brandOptics AI code-review',
    state=state,
    description='🚧 Issues detected—please refine your code.' if issues else '✅ No code issues detected.'
)
print(f"Posted AI review for PR #{pr_number}")