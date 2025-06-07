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
    print("⛔️ Missing credentials.")
    exit(1)
openai.api_key = OPENAI_API_KEY
gh = Github(AI_TOKEN)

# ── 2) READ PR PAYLOAD ─────────────────────────────────────────────────
with open(EVENT_PATH) as f:
    event = json.load(f)
pr_number = event["pull_request"]["number"]
full_sha  = event["pull_request"]["head"]["sha"]
repo      = gh.get_repo(REPO_NAME)
pr        = repo.get_pull(pr_number)

# ── 3) GATHER CHANGED FILES (excl .github/) ─────────────────────────────
changed_files = [f.filename for f in pr.get_files() if f.patch and not f.filename.lower().startswith('.github/')]
if not changed_files:
    pr.create_issue_comment("🤖 brandOptics AI Review: No relevant changes detected. 🎉")
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI code-review", state="success",
        description="✅ No relevant code changes."
    )
    exit(0)

# ── 4) LOAD ANALYZER REPORTS ────────────────────────────────────────────
def load_json(path: Path):
    try: return json.loads(path.read_text())
    except: return None
reports_dir = Path('.github/linter-reports')
eslint_report        = load_json(reports_dir/'eslint.json')
flake8_report        = load_json(reports_dir/'flake8.json')
shellcheck_report    = load_json(reports_dir/'shellcheck.json')
dartanalyzer_report  = load_json(reports_dir/'dartanalyzer.json')
dotnet_report        = load_json(reports_dir/'dotnet-format.json')

# ── 5) ORIGINAL LINE HELPER ───────────────────────────────────────────
def get_original_line(path, line_no):
    try:
        with open(path) as f: return f.readlines()[line_no-1].rstrip('\n')
    except: return ''

# ── 6) DIFF CONTEXT HELPER ─────────────────────────────────────────────
def get_patch_context(patch, target_line, ctx=3):
    file_line, hunk = None, []
    for l in patch.splitlines():
        if l.startswith('@@'):
            start = int(l.split()[2].split(',')[0][1:])
            file_line = start-1
            hunk = [l]
        elif file_line is not None:
            if l[0] in (' ', '+'): file_line += 1
            if abs(file_line-target_line)<=ctx: hunk.append(l)
            if file_line>target_line+ctx: break
    return '\n'.join(hunk)

# ── 7) AI SUGGESTION ───────────────────────────────────────────────────
def ai_suggest_fix(code, ctx_patch, path, line_no):
    prompt = dedent(f"""
You are a Dart/Flutter expert.
Below is the diff around line {line_no} in `{path}` ({code}):
```diff
{ctx_patch}
```
Provide labeled sections:
Fix: copy-friendly corrected snippet
Refactor: best-practice improvements
Why: brief rationale
Output only these sections.
""")
    try:
        resp = openai.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role':'system','content':'You are a helpful assistant.'},
                {'role':'user','content':prompt}],
            temperature=0.0, max_tokens=300
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"AI error: {e}\n{ctx_patch}"

# ── 8) COLLECT ISSUES ──────────────────────────────────────────────────
issues=[]
# ESLint
if isinstance(eslint_report,list):
    for r in eslint_report:
        p=os.path.relpath(r.get('filePath',''))
        if p in changed_files:
            for m in r.get('messages',[]):
                ln=m.get('line');
                if ln: issues.append({'file':p,'line':ln,'code':m.get('ruleId','ESLint'),'msg':m.get('message','')})
# Flake8
if isinstance(flake8_report,dict):
    for ap,errs in flake8_report.items():
        p=os.path.relpath(ap)
        if p in changed_files:
            for e in errs:
                ln=e.get('line_number') or e.get('line')
                if ln: issues.append({'file':p,'line':ln,'code':e.get('code','Flake8'),'msg':e.get('text','')})
# ShellCheck
if isinstance(shellcheck_report,list):
    for e in shellcheck_report:
        p=os.path.relpath(e.get('file',''))
        ln=e.get('line')
        if p in changed_files and ln: issues.append({'file':p,'line':ln,'code':e.get('code','ShellCheck'),'msg':e.get('message','')})
# Dart Analyzer
if isinstance(dartanalyzer_report,dict):
    for d in dartanalyzer_report.get('diagnostics',[]):
        loc=d.get('location',{});p=os.path.relpath(loc.get('file',''))
        ln=loc.get('range',{}).get('start',{}).get('line')
        if p in changed_files and ln: issues.append({'file':p,'line':ln,'code':d.get('code','DartAnalyzer'),'msg':d.get('problemMessage') or d.get('message','')})
# .NET Format
if isinstance(dotnet_report,dict):
    for d in (dotnet_report.get('Diagnostics') or dotnet_report.get('diagnostics') or []):
        p=os.path.relpath(d.get('Path','') or d.get('path',''))
        ln=d.get('Region',{}).get('StartLine')
        if p in changed_files and ln: issues.append({'file':p,'line':ln,'code':'DotNetFormat','msg':d.get('Message','')})

# ── 9) GROUP & COMMENT ────────────────────────────────────────────────
file_groups={}
for i in issues: file_groups.setdefault(i['file'],[]).append(i)

md_lines=[]
for f,its in sorted(file_groups.items()):
    md_lines.append(f"**File =>** `{f}`")
    md_lines.append("")
    md_lines.append("| Line number | Issue | Suggested Fix by AI |")
    md_lines.append("|:-----------:|:------|:---------------------|")
    ghf=next(x for x in pr.get_files() if x.filename==f)
    patch=ghf.patch or ''
    for it in sorted(its,key=lambda x:x['line']):
        ln=it['line']; issue_txt=f"`{it['code']}` {it['msg']}"
        ctx=get_patch_context(patch,ln)
        ai_out=ai_suggest_fix(it['code'],ctx,f,ln)
        fix_match=re.search(r'Fix:\s*([\s\S]*?)(?=\n[A-Z][a-z]+:|$)',ai_out)
        fix_snip=fix_match.group(1).strip() if fix_match else ai_out.splitlines()[0].strip()
        # inline multi-line with HTML <br>
        fix_html=fix_snip.replace('`','&#96;').replace('\n','<br>')
        md_lines.append(f"| {ln} | {issue_txt} | <code>{fix_html}</code> |")
    md_lines.append("")

if not md_lines: md_lines=['🎉 No issues detected. Ready to merge! 🎉']

body='\n'.join(['## 🤖 brandOptics AI Review Suggestions','']+md_lines)
pr.create_issue_comment(body)
repo.get_commit(full_sha).create_status(
    context='brandOptics AI code-review',
    state='failure' if issues else 'success',
    description='🚧 Issues detected—please refine your code.' if issues else '✅ No code issues.'
)
print(f"Posted AI review for PR #{pr_number}")