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

# Load PR context
def load_event(path):
    with open(path) as f:
        return json.load(f)

event = load_event(defaults['EVENT_PATH'])
repo = gh.get_repo(defaults['REPO_NAME'])
pr = repo.get_pull(event['pull_request']['number'])
sha = event['pull_request']['head']['sha']

# Helpers
def load_json(path):
    try:
        if path.is_file() and path.stat().st_size:
            return json.loads(path.read_text())
    except json.JSONDecodeError:
        print(f"⚠️ JSON parse error: {path}")
    return None

def changed_files(pr):
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

def extract_diff(pr, base, sha):
    blocks=[]
    for f in changed_files(pr):
        diff = subprocess.run(['git','diff',f'origin/{base}',sha,'--',f],capture_output=True,text=True).stdout
        cur=[]
        for l in diff.splitlines():
            if l.startswith('+') and not l.startswith('+++'):
                cur.append(l[1:])
            elif cur:
                blocks.append({'file':f,'code':'\n'.join(cur)});
                cur=[]
        if cur:
            blocks.append({'file':f,'code':'\n'.join(cur)})
    return blocks

# Load linter data
rdir=Path('.github/linter-reports')
reports={
    'eslint': load_json(rdir/'eslint.json') or [],
    'flake8': load_json(rdir/'flake8.json') or {},
    'shellcheck': load_json(rdir/'shellcheck.json') or [],
    'dart': load_json(rdir/'dartanalyzer.json') or {},
    'dotnet': load_json(rdir/'dotnet-format.json') or {}
}

# Gather issues
def gather_issues(pr):
    issues=[]
    changed=set(changed_files(pr))
    for rpt in reports['eslint']:
        rel=os.path.relpath(rpt.get('filePath',''))
        if rel in changed:
            for m in rpt.get('messages',[]):
                issues.append({'file':rel,'line':m.get('line'),'code':m.get('ruleId','ESLint'),'message':m.get('message')})
    for path, errs in reports['flake8'].items():
        rel=os.path.relpath(path)
        if rel in changed:
            for e in errs:
                issues.append({'file':rel,'line':e.get('line_number'),'code':e.get('code'),'message':e.get('text')})
    for e in reports['shellcheck']:
        rel=os.path.relpath(e.get('file',''))
        if rel in changed:
            issues.append({'file':rel,'line':e.get('line'),'code':e.get('code'),'message':e.get('message')})
    for d in reports['dart'].get('diagnostics',[]):
        loc=d.get('location',{})
        rel=os.path.relpath(loc.get('file',''))
        if rel in changed:
            issues.append({'file':rel,'line':loc.get('range',{}).get('start',{}).get('line'),'code':d.get('code'),'message':d.get('problemMessage') or d.get('message')})
    for d in reports['dotnet'].get('Diagnostics',[]):
        rel=os.path.relpath(d.get('Path',''))
        if rel in changed:
            issues.append({'file':rel,'line':d['Region']['StartLine'],'code':'DotNet','message':d.get('Message')})
    return issues

issues=gather_issues(pr)
ref_blocks=extract_diff(pr,defaults['BASE_REF'],sha)

# Build comment with index and tables
md=[]
md.append("## 🚀 brandOptics AI Code Review")
md.append("\n### 📑 Index of Contents")
if issues:
    md.append("- [Issues Summary](#issues)")
if ref_blocks:
    md.append("- [Refactoring Suggestions](#refactoring)")

# Issues Table
if issues:
    md.append("\n---\n<a name='issues'></a>\n## 🚨 Issues Summary")
    md.append("| File | Line | Code | Message | Suggestion |")
    md.append("|:-----|:----:|:-----|:--------|:-----------|")
    for i in issues:
        orig=read_line(i['file'],i['line'])
        sug=call_ai([
            {'role':'system','content':'You are a Dart/Flutter expert.'},
            {'role':'user','content':dedent(f"""
Fix {i['code']} at {i['file']}:{i['line']}:
```dart
{orig}
```
""" )}
        ],max_tokens=60)
        md.append(f"| {i['file']} | {i['line']} | `{i['code']}` | {i['message']} | `{sug}` |")
else:
    md.append("\n---\n🎉 **No lint or analysis issues detected!**")

# Refactoring Table
if ref_blocks:
    md.append("\n---\n<a name='refactoring'></a>\n## 💡 Professional Refactoring Suggestions")
    md.append("| File | Original Snippet | Refactored Snippet |")
    md.append("|:-----|:----------------|:-------------------|")
    for b in ref_blocks:
        ref=call_ai([
            {'role':'system','content':'You are a senior software engineer.'},
            {'role':'user','content':dedent(f"""
Refactor this snippet in `{b['file']}`:
```
{b['code']}
```
""" )}
        ],max_tokens=200,temperature=0.2)
        snippet=b['code'].replace('|','\|')
        md.append(f"| {b['file']} | `{snippet}` | `{ref.replace('`','\`')}` |")

# Post comment and status
comment="\n".join(md)
pr.create_issue_comment(comment)
repo.get_commit(sha).create_status(
    context="brandOptics AI code-review",
    state='failure' if issues else 'success',
    description="Review complete."
)
print(f"Posted PR review #{pr.number}")