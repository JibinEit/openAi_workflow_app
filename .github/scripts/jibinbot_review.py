#!/usr/bin/env python3
import os
import json
import subprocess
from pathlib import Path
from textwrap import dedent

import openai
from github import Github

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
REPO_NAME      = os.getenv("GITHUB_REPOSITORY")
EVENT_PATH     = os.getenv("GITHUB_EVENT_PATH")
BASE_REF       = os.getenv("GITHUB_BASE_REF")  # e.g., 'main'
DEFAULT_MODEL  = os.getenv("OPENAI_MODEL", "gpt-4o")

# ─────────────────────────────────────────────────────────────────────────────
# Initialization
# ─────────────────────────────────────────────────────────────────────────────
if not all([OPENAI_API_KEY, GITHUB_TOKEN, REPO_NAME, EVENT_PATH, BASE_REF]):
    raise EnvironmentError(
        "Required env vars: OPENAI_API_KEY, GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_EVENT_PATH, GITHUB_BASE_REF"
    )

openai.api_key = OPENAI_API_KEY
gh = Github(GITHUB_TOKEN)

# ─────────────────────────────────────────────────────────────────────────────
# Load GitHub event
# ─────────────────────────────────────────────────────────────────────────────
def load_event():
    with open(EVENT_PATH, 'r') as f:
        return json.load(f)

event     = load_event()
pr_number = event['pull_request']['number']
sha        = event['pull_request']['head']['sha']
repo       = gh.get_repo(REPO_NAME)
pr         = repo.get_pull(pr_number)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def load_json(path: Path):
    if path.is_file() and path.stat().st_size:
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            print(f"⚠️ Could not parse JSON at {path}")
    return None


def get_changed_files():
    return [f.filename for f in pr.get_files() if f.patch]


def read_line(filepath: str, lineno: int) -> str:
    try:
        return Path(filepath).read_text().splitlines()[lineno - 1]
    except Exception:
        return ""


def call_openai(messages, max_tokens=200, temperature=0.0):
    return openai.ChatCompletion.create(
        model=DEFAULT_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature
    ).choices[0].message.content.strip()


def extract_diff_blocks(files, base_ref, head_sha):
    blocks = []
    for file in files:
        diff = subprocess.run(
            ['git', 'diff', f'origin/{base_ref}', head_sha, '--', file],
            capture_output=True, text=True
        ).stdout
        current = []
        for line in diff.splitlines():
            if line.startswith('+') and not line.startswith('+++'):
                current.append(line[1:])
            else:
                if current:
                    blocks.append({'file': file, 'code': '\n'.join(current)})
                    current = []
        if current:
            blocks.append({'file': file, 'code': '\n'.join(current)})
    return blocks

# ─────────────────────────────────────────────────────────────────────────────
# Load linter reports
# ─────────────────────────────────────────────────────────────────────────────
reports_dir = Path('.github/linter-reports')
reports = {
    'eslint':     load_json(reports_dir / 'eslint.json') or [],
    'flake8':     load_json(reports_dir / 'flake8.json') or {},
    'shellcheck': load_json(reports_dir / 'shellcheck.json') or [],
    'dart':       load_json(reports_dir / 'dartanalyzer.json') or {},
    'dotnet':     load_json(reports_dir / 'dotnet-format.json') or {}
}

# ─────────────────────────────────────────────────────────────────────────────
# Collect issues
# ─────────────────────────────────────────────────────────────────────────────
issues = []
changed_files = set(get_changed_files())

# ESLint
for rpt in reports['eslint']:
    abs_path = rpt.get('filePath', '')
    rel_path = os.path.relpath(abs_path, start=os.getcwd())
    if rel_path in changed_files:
        for msg in rpt.get('messages', []):
            issues.append({
                'file': rel_path,
                'line': msg.get('line'),
                'code': msg.get('ruleId') or 'ESLint',
                'message': msg.get('message')
            })

# Flake8
for path, errs in reports['flake8'].items():
    rel_path = os.path.relpath(path, start=os.getcwd())
    if rel_path in changed_files:
        for e in errs:
            issues.append({
                'file': rel_path,
                'line': e.get('line_number') or e.get('line'),
                'code': e.get('code'),
                'message': e.get('text')
            })

# ShellCheck
for entry in reports['shellcheck']:
    abs_path = entry.get('file')
    rel_path = os.path.relpath(abs_path, start=os.getcwd())
    if rel_path in changed_files:
        issues.append({
            'file': rel_path,
            'line': entry.get('line'),
            'code': entry.get('code'),
            'message': entry.get('message')
        })

# Dart Analyzer
for d in reports['dart'].get('diagnostics', []):
    loc = d.get('location', {})
    abs_path = loc.get('file', '')
    rel_path = os.path.relpath(abs_path, start=os.getcwd())
    if rel_path in changed_files:
        issues.append({
            'file': rel_path,
            'line': loc.get('range', {}).get('start', {}).get('line'),
            'code': d.get('code') or 'DartAnalyzer',
            'message': d.get('problemMessage') or d.get('message')
        })

# .NET Format
for d in reports['dotnet'].get('Diagnostics', []):
    abs_path = d.get('Path', '')
    rel_path = os.path.relpath(abs_path, start=os.getcwd())
    if rel_path in changed_files:
        issues.append({
            'file': rel_path,
            'line': d['Region']['StartLine'],
            'code': 'DotNet',
            'message': d.get('Message')
        })

# ─────────────────────────────────────────────────────────────────────────────
# Build review comment
# ─────────────────────────────────────────────────────────────────────────────
comment_lines = ["## 🚀 brandOptics AI Code Review"]
if issues:
    comment_lines.append(
        f"Found **{len(issues)}** issue(s) in **{len({i['file'] for i in issues})}** files:"
    )
    for i in issues:
        orig_code = read_line(i['file'], i['line'])
        suggestion = call_openai([
            {'role': 'system', 'content': 'You are a Dart/Flutter expert.'},
            {'role': 'user', 'content': dedent(f"""
                Fix {i['code']} in `{i['file']}:{i['line']}`:
                ```dart
                {orig_code}
                ```
            """
            )}
        ], max_tokens=60)
        comment_lines.append(
            f"- `{i['file']}:{i['line']}` **{i['code']}**: {i['message']}\n  ➜ Suggestion: `{suggestion}`"
        )
else:
    comment_lines.append("🎉 No lint or analysis issues detected!")

# Refactor new code blocks
new_blocks = extract_diff_blocks(list(changed_files), BASE_REF, sha)
if new_blocks:
    comment_lines.append("\n## 💡 Refactoring Suggestions")
    for blk in new_blocks:
        refactored = call_openai([
            {'role': 'system', 'content': 'You are a senior software engineer.'},
            {'role': 'user', 'content': dedent(f"""
                Refactor this snippet in `{blk['file']}`:
                ```
                {blk['code']}
                ```
            """
            )}
        ], max_tokens=200, temperature=0.2)
        comment_lines.append(
            f"""### {blk['file']}
```dart
{refactored}
```"""
        )

comment = "\n".join(comment_lines)
pr.create_issue_comment(comment)

# ─────────────────────────────────────────────────────────────────────────────
# Set GitHub status
# ─────────────────────────────────────────────────────────────────────────────
status = 'failure' if issues else 'success'
repo.get_commit(sha).create_status(
    context="brandOptics AI code-review",
    state=status,
    description="Review complete. Check suggestions above."
)

print(f"Posted review for PR #{pr_number} 📌")