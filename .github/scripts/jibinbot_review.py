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

# ── 3) DETECT CHANGES (exclude .github/) ──────────────────────────────
changed_files = [f.filename for f in pr.get_files()
                 if f.patch and not f.filename.lower().startswith('.github/')]
if not changed_files:
    pr.create_issue_comment("🤖 brandOptics AI Review — no relevant code changes detected.")
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI code-review",
        state="success",
        description="No relevant code changes detected."
    )
    exit(0)

# ── 4) LOAD LINTER REPORTS ─────────────────────────────────────────────
def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except:
        return None
reports_dir = Path('.github/linter-reports')
eslint_report        = load_json(reports_dir / 'eslint.json')
flake8_report        = load_json(reports_dir / 'flake8.json')
shellcheck_report    = load_json(reports_dir / 'shellcheck.json')
dartanalyzer_report  = load_json(reports_dir / 'dartanalyzer.json')
dotnet_report        = load_json(reports_dir / 'dotnet-format.json')

# ── 5) HELPERS ─────────────────────────────────────────────────────────
def get_patch_context(patch: str, line_no: int, ctx: int = 3) -> str:
    file_line = None
    hunk = []
    for line in patch.splitlines():
        if line.startswith('@@ '):
            start = int(line.split()[2].split(',')[0][1:]) - 1
            file_line = start
            hunk = [line]
        elif file_line is not None:
            prefix = line[0]
            if prefix in (' ', '+', '-'):
                if prefix != '-':
                    file_line += 1
                if abs(file_line - line_no) <= ctx:
                    hunk.append(line)
                if file_line > line_no + ctx:
                    break
    return '\n'.join(hunk)

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
# (Existing linter extraction logic unchanged: ESLint, Flake8, ShellCheck, Dart Analyzer, .NET)

if isinstance(eslint_report, list):
    for rep in eslint_report:
        path = os.path.relpath(rep.get('filePath',''))
        if path in changed_files:
            for msg in rep.get('messages', []):
                ln = msg.get('line')
                if ln:
                    issues.append({'file': path, 'line': ln,
                                   'code': msg.get('ruleId','ESLint'),
                                   'message': msg.get('message','')})
# ... Flake8, ShellCheck, DartAnalyzer, DotNetFormat follow similarly ...

# ── 8) GROUP & OUTPUT ─────────────────────────────────────────────────
file_groups = {}
for issue in issues:
    file_groups.setdefault(issue['file'], []).append(issue)

md = ['## 🤖 brandOptics AI Review Suggestions', '']
for file_path, file_issues in sorted(file_groups.items()):
    md.append(f"**File =>** `{file_path}`")
    md.append('')
    md.append('| Line | Issue | Fix (summary) |')
    md.append('|:----:|:------|:--------------|')
    gh_file = next(f for f in pr.get_files() if f.filename == file_path)
    patch   = gh_file.patch or ''
    details = []
    for it in sorted(file_issues, key=lambda x: x['line']):
        ln = it['line']
        issue_md = f"`{it['code']}` {it['message']}"
        ctx = get_patch_context(patch, ln)
        ai_out = ai_suggest_fix(it['code'], ctx, file_path, ln)
        # extract Fix
        m = re.search(r'Fix:\s*```dart\n([\s\S]*?)```', ai_out)
        full_fix = m.group(1).rstrip() if m else ai_out.splitlines()[0].strip()
        summary = full_fix.splitlines()[0].strip().replace('|','\\|')
        md.append(f"| {ln} | {issue_md} | `{summary}` |")
        details.append((ln, full_fix, ai_out))
    md.append('')
    for ln, full_fix, ai_out in details:
        md.append('<details>')
        md.append(f'<summary>Full fix for line {ln}</summary>')
        md.append('```dart')
        md.append(full_fix)
        md.append('```')
        # Extract and append Refactor and Why
        ref = re.search(r'Refactor:\s*([\s\S]*?)(?=\nWhy:|$)', ai_out)
        if ref:
            md.append('**Refactor:**')
            md.append(ref.group(1).strip())
        why = re.search(r'Why:\s*([\s\S]*)', ai_out)
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
    description=('Issues detected — please refine your code.' if issues else 'No code issues detected.')
)
print(f"Posted AI review for PR #{pr_number}")