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
pr_number       = event["pull_request"]["number"]
full_sha        = event["pull_request"]["head"]["sha"]
repo            = gh.get_repo(REPO_NAME)
pr              = repo.get_pull(pr_number)

dev_name        = event["pull_request"]["user"]["login"]
title           = event["pull_request"]["title"]
body            = event["pull_request"]["body"] or "No description provided."
url             = event["pull_request"]["html_url"]
source_branch   = event["pull_request"]["head"]["ref"]
target_branch   = event["pull_request"]["base"]["ref"]
created_at      = event["pull_request"]["created_at"]
commits         = event["pull_request"]["commits"]
additions       = event["pull_request"]["additions"]
deletions       = event["pull_request"]["deletions"]
changed_files   = event["pull_request"]["changed_files"]

# ── Insert logo at top of comment ────────────────────────────────────
default_branch = repo.default_branch
img_url = f"https://raw.githubusercontent.com/{REPO_NAME}/{default_branch}/.github/assets/bailogo.png"

# ── 3) DETECT CHANGED FILES ─────────────────────────────────────────
changed_files = [
    f.filename for f in pr.get_files()
    if f.patch and not f.filename.lower().startswith('.github/')
]
if not changed_files:
    pr.create_issue_comment(dedent(f"""
<img src="{img_url}" width="100" height="100" />

# brandOptics AI Neural Nexus

## Review: ✅ No Issues Found

Your PR contains no code changes requiring review. 🚀
"""))
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI Neural Nexus Code Review",
        state="success",
        description="No code changes detected."
    )
    exit(0)

# ── 4) LOAD LINTER REPORTS ─────────────────────────────────────────────
def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except:
        return None

reports_dir         = Path('.github/linter-reports')
eslint_report       = load_json(reports_dir / 'eslint.json')
flake8_report       = load_json(reports_dir / 'flake8.json')
shellcheck_report   = load_json(reports_dir / 'shellcheck.json')
dartanalyzer_report = load_json(reports_dir / 'dartanalyzer.json')
dotnet_report       = load_json(reports_dir / 'dotnet-format.json')
htmlhint_report     = load_json(reports_dir / 'htmlhint.json')
stylelint_report    = load_json(reports_dir / 'stylelint.json')

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

def detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return {
        '.dart': 'Dart/Flutter',
        '.ts': 'TypeScript/Angular',
        '.js': 'JavaScript/React',
        '.jsx':'JavaScript/React',
        '.tsx':'TypeScript/React',
        '.py':'Python',
        '.java':'Java',
        '.cs':'.NET C#',
        '.go':'Go',
        '.html':'HTML',
        '.css':'CSS',
    }.get(ext, 'general programming')

FENCE_BY_LANG = {
    'Dart/Flutter':'dart','TypeScript/Angular':'ts','JavaScript/React':'js',
    'TypeScript/React':'ts','Python':'python','Java':'java',
    '.NET C#':'csharp','Go':'go','HTML':'html','CSS':'css',
    'general programming':''
}

# ── 6) COLLECT ISSUES ──────────────────────────────────────────────────
issues = []
# ESLint
if isinstance(eslint_report, list):
    for rep in eslint_report:
        path = os.path.relpath(rep.get('filePath',''))
        if path in changed_files:
            for msg in rep.get('messages', []):
                ln = msg.get('line')
                if ln:
                    issues.append({'file':path,'line':ln,'code':msg.get('ruleId','ESLint'),'message':msg.get('message','')})
# Flake8
if isinstance(flake8_report, dict):
    for ap, errs in flake8_report.items():
        path = os.path.relpath(ap)
        if path in changed_files:
            for e in errs:
                ln = e.get('line_number') or e.get('line')
                if ln:
                    issues.append({'file':path,'line':ln,'code':e.get('code','Flake8'),'message':e.get('text','')})
# ShellCheck
if isinstance(shellcheck_report, list):
    for ent in shellcheck_report:
        path = os.path.relpath(ent.get('file',''))
        ln   = ent.get('line')
        if path in changed_files and ln:
            issues.append({'file':path,'line':ln,'code':ent.get('code','ShellCheck'),'message':ent.get('message','')})
# Dart Analyzer
if isinstance(dartanalyzer_report, dict):
    for diag in dartanalyzer_report.get('diagnostics', []):
        loc = diag.get('location', {})
        path = os.path.relpath(loc.get('file',''))
        ln   = loc.get('range',{}).get('start',{}).get('line')
        if path in changed_files and ln:
            issues.append({'file':path,'line':ln,'code':diag.get('code','DartAnalyzer'),'message':diag.get('problemMessage') or diag.get('message','')})
# .NET Format
if isinstance(dotnet_report, dict):
    diags = dotnet_report.get('Diagnostics') or dotnet_report.get('diagnostics')
    if isinstance(diags, list):
        for d in diags:
            path = os.path.relpath(d.get('Path') or d.get('path',''))
            ln   = d.get('Region',{}).get('StartLine')
            if path in changed_files and ln:
                issues.append({'file':path,'line':ln,'code':'DotNetFormat','message':d.get('Message','')})
# HTMLHint & Stylelint
for report, key in [(htmlhint_report,'htmlhint'),(stylelint_report,'stylelint')]:
    if isinstance(report, list):
        for ent in report:
            path = os.path.relpath(ent.get('file',ent.get('source','')))
            ln   = ent.get('line')
            rule = ent.get('rule', key.capitalize())
            msg  = ent.get('message',ent.get('text',''))
            if path in changed_files and ln:
                issues.append({'file':path,'line':ln,'code':rule,'message':msg})

# ── 7) GROUP ISSUES ────────────────────────────────────────────────────
file_groups = {}
for issue in issues:
    file_groups.setdefault(issue['file'], []).append(issue)

# ── 8) AI SUGGESTION ───────────────────────────────────────────────────
def ai_suggest_fix(code: str, patch_ctx: str, file_path: str, line_no: int) -> str:
    lang = detect_language(file_path)
    fence = FENCE_BY_LANG.get(lang,'')
    deprecated = []
    if re.search(r'\.withOpacity\(', patch_ctx):
        deprecated.append("• Found deprecated `.withOpacity()`")
    prompt = dedent(f"""
You are an expert {lang} reviewer.
Review this diff at line {line_no} in `{file_path}`:

```diff
{patch_ctx}
```

{"".join(deprecated) + "\\n" if deprecated else ""}
Respond in this markdown:

### Original Code:
```{fence}
<<reconstruct original>>
```
### Suggested Fix:
```{fence}
<<full corrected code>>
```
### Refactor Suggestions:
<<best practices>>
### Why:
<<brief reasons>>
""")
    resp = openai.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{"role":"system","content":"You are a senior code reviewer."},
                  {"role":"user","content":prompt}],
        temperature=0.0,
        max_tokens=600
    )
    return resp.choices[0].message.content.strip()

# ── 9) BUILD & POST COMMENT ───────────────────────────────────────────
md = []

if not issues:
    md.append(f'<img src="{img_url}" width="100" height="100" />')
    md.append('')
    md.append('# brandOptics AI Neural Nexus')
    md.append('## ✅ Review: All Clear!')
    md.append('')
    md.append('No issues detected—your code is clean and ready to merge. 🚀')
    md.append('')
else:
    md.append(f'<img src="{img_url}" width="100" height="100" />')
    md.append('')
    md.append('# brandOptics AI Neural Nexus')
    md.append('## 📌 Issues & Suggestions')
    md.append(f'**Total Issues:** {len(issues)} across {len(file_groups)} files.')
    md.append('')
    for fp, grp in sorted(file_groups.items()):
        md.append(f'### File: `{fp}`')
        md.append('| Line | Code | Message |')
        md.append('|:----:|:-----|:--------|')
        ghf = next(f for f in pr.get_files() if f.filename==fp)
        patch = ghf.patch or ''
        for it in sorted(grp, key=lambda x:x['line']):
            ln = it['line']
            ctx = get_patch_context(patch,ln)
            fix = ai_suggest_fix(it['code'],ctx,fp,ln)
            md.append(f'| {ln} | `{it["code"]}` | {it["message"]} |')
            md.append('<details>')
            md.append(f'<summary>AI Suggestions for line {ln}</summary>')
            md.append('')
            md.append(fix)
            md.append('</details>')
            md.append('')

body = '\n'.join(md)
pr.create_issue_comment(body)
repo.get_commit(full_sha).create_status(
    context="brandOptics AI Neural Nexus Code Review",
    state="failure" if issues else "success",
    description="Review completed."
)
print(f"Posted AI review for PR #{pr_number}")