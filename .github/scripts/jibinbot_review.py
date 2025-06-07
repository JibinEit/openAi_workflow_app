#!/usr/bin/env python3
import os
import json
import subprocess
from pathlib import Path
from textwrap import dedent

import openai
from github import Github

# Configuration
defaults = dict(
    OPENAI_API_KEY=os.getenv("OPENAI_API_KEY"),
    GITHUB_TOKEN=os.getenv("GITHUB_TOKEN"),
    REPO_NAME=os.getenv("GITHUB_REPOSITORY"),
    EVENT_PATH=os.getenv("GITHUB_EVENT_PATH"),
    BASE_REF=os.getenv("GITHUB_BASE_REF"),
    DEFAULT_MODEL=os.getenv("OPENAI_MODEL", "gpt-4o")
)
if not all(defaults.values()):
    raise EnvironmentError("Missing required environment variables.")
openai.api_key = defaults['OPENAI_API_KEY']
gh = Github(defaults['GITHUB_TOKEN'])

# Load GitHub event and PR context
def load_event(path):
    with open(path) as f: return json.load(f)

event = load_event(defaults['EVENT_PATH'])
pr = gh.get_repo(defaults['REPO_NAME']).get_pull(event['pull_request']['number'])
sha = event['pull_request']['head']['sha']

# Helpers
def load_json(path):
    try:
        if path.is_file() and path.stat().st_size:
            return json.loads(path.read_text())
    except json.JSONDecodeError:
        print(f"⚠️ JSON parse error: {path}")
    return None

def get_changed_files(pr):
    return [f.filename for f in pr.get_files() if f.patch]

def read_line(file, line):
    try:
        return Path(file).read_text().splitlines()[line-1]
    except:
        return ""

def call_ai(messages, **kwargs):
    resp = openai.chat.completions.create(
        model=defaults['DEFAULT_MODEL'],
        messages=messages,
        **kwargs
    )
    return resp.choices[0].message.content.strip()

def extract_diff(pr, base_ref, sha):
    blocks=[]
    for f in get_changed_files(pr):
        diff = subprocess.run(['git','diff',f'origin/{base_ref}',sha,'--',f],capture_output=True,text=True).stdout
        cur=[]
        for l in diff.splitlines():
            if l.startswith('+') and not l.startswith('+++'):
                cur.append(l[1:])
            elif cur:
                blocks.append({'file':f,'code':'\n'.join(cur)});cur=[]
        if cur: blocks.append({'file':f,'code':'\n'.join(cur)})
    return blocks

# Load linter reports
rdir=Path('.github/linter-reports')
reports={k: load_json(rdir/f'{k}.json') or [] for k in ['eslint','shellcheck']}
reports['flake8']=load_json(rdir/'flake8.json') or {}
reports['dart']=load_json(rdir/'dartanalyzer.json') or {}
reports['dotnet']=load_json(rdir/'dotnet-format.json') or {}

# Collect issues
def gather_issues(pr):
    issues=[]
    changed=set(get_changed_files(pr))
    # ESLint & ShellCheck
    for key in ['eslint','shellcheck']:
        for rpt in reports[key]:
            rel=os.path.relpath(rpt.get('filePath' if key=='eslint' else 'file',''))
            if rel in changed:
                msgs=rpt.get('messages') if key=='eslint' else [rpt]
                for m in msgs:
                    issues.append({'file':rel,'line':m.get('line'),'code':m.get('ruleId',m.get('code',key)),'message':m.get('message')})
    # Flake8
    for path,errs in reports['flake8'].items():
        rel=os.path.relpath(path)
        if rel in changed:
            for e in errs:
                issues.append({'file':rel,'line':e.get('line_number'),'code':e.get('code'),'message':e.get('text')})
    # Dart
    for d in reports['dart'].get('diagnostics',[]):
        loc=d.get('location',{});rel=os.path.relpath(loc.get('file',''))
        if rel in changed:
            issues.append({'file':rel,'line':loc.get('range',{}).get('start',{}).get('line'),'code':d.get('code'),'message':d.get('problemMessage') or d.get('message')})
    # DotNet
    for d in reports['dotnet'].get('Diagnostics',[]):
        rel=os.path.relpath(d.get('Path',''))
        if rel in changed:
            issues.append({'file':rel,'line':d['Region']['StartLine'],'code':'DotNet','message':d.get('Message')})
    return issues

issues=gather_issues(pr)
ref_blocks=extract_diff(pr,defaults['BASE_REF'],sha)

# Build markdown comment
md=[f"## 🚀 brandOptics AI Code Review"]
# Index
md.append("\n### 📑 Index")
if issues:
    files=set(i['file'] for i in issues)
    md.append("- **Issues by File:**")
    for f in sorted(files): md.append(f"  - [{f}](#issue-{f.replace('/','')})")
if ref_blocks:
    files_r=set(b['file'] for b in ref_blocks)
    md.append("- **Refactor Suggestions:**")
    for f in sorted(files_r): md.append(f"  - [{f}](#refactor-{f.replace('/','')})")

# Issue Details
if issues:
    md.append("\n---\n## 🚨 Issues")
    grp={}
    for i in issues: grp.setdefault(i['file'],[]).append(i)
    for f,its in grp.items():
        anchor=f"issue-{f.replace('/','')}"
        md.append(f"<a name=\"{anchor}\"></a>\n### File: `{f}`")
        md.append("| Line | Code | Message | Suggestion |")
        md.append("|:----:|:-----|:--------|:-----------|")
        for i in its:
            orig=read_line(i['file'],i['line'])
            sug=call_ai([
                {'role':'system','content':'You are a Dart/Flutter expert.'},
                {'role':'user','content':dedent(f"""
Fix {i['code']} at {f}:{i['line']}:
```dart
{orig}
```
""" )}
            ],max_tokens=60)
            md.append(f"| {i['line']} | `{i['code']}` | {i['message']} | `{sug}` |")

# Refactor Details
if ref_blocks:
    md.append("\n---\n## 💡 Professional Refactoring")
    for f in sorted(set(b['file'] for b in ref_blocks)):
        anchor=f"refactor-{f.replace('/','')}"
        md.append(f"<a name=\"{anchor}\"></a>\n### File: `{f}`")
        for b in [blk for blk in ref_blocks if blk['file']==f]:
            ref=call_ai([
                {'role':'system','content':'You are a senior software engineer.'},
                {'role':'user','content':dedent(f"""
Refactor this snippet:
```
{b['code']}
```
""" )}
            ],max_tokens=200,temperature=0.2)
            md.append("```dart")
            md.append(ref)
            md.append("```")

# Post
comment="\n".join(md)
pr.create_issue_comment(comment)
pr.get_repo().get_commit(sha).create_status(
    context="brandOptics AI code-review",
    state='failure' if issues else 'success',
    description="Review complete."
)
print(f"Posted PR review #{pr.number}")