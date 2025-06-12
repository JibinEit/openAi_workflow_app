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

pr_number     = event["pull_request"]["number"]
repo          = gh.get_repo(REPO_NAME)
pr            = repo.get_pull(pr_number)
dev_name      = event["pull_request"]["user"]["login"]
title         = event["pull_request"]["title"]
body          = event["pull_request"]["body"] or "No description provided."
url           = event["pull_request"]["html_url"]
source_branch = event["pull_request"]["head"]["ref"]
target_branch = event["pull_request"]["base"]["ref"]
created_at    = event["pull_request"]["created_at"]
commits       = event["pull_request"]["commits"]
additions     = event["pull_request"]["additions"]
deletions     = event["pull_request"]["deletions"]
changed_files_list = event["pull_request"]["changed_files"]

# ── Insert logo ────────────────────────────────────────────────────────

default_branch = repo.default_branch
img_url        = f"https://raw.githubusercontent.com/{REPO_NAME}/{default_branch}/.github/assets/bailogo.png"

# ── 3) DETECT CHANGED FILES ────────────────────────────────────────────

changed_files = [f.filename for f in pr.get_files() if f.patch and not f.filename.lower().startswith('.github/')]
if not changed_files:
    pr.create_issue_comment(dedent(f"""
<img src="{img_url}" width="100" height="100" />

# brandOptics AI Neural Nexus

## Review: ✅ No Relevant Changes Detected

No actionable code changes were found in this PR.  
Everything looks quiet on the commit front — nothing to analyze right now. 😌

💡 **Note**  
Make sure your changes include source code updates (excluding config/docs only) to trigger a meaningful review.
"""))
    repo.get_commit(pr.head.sha).create_status(
        context="brandOptics AI Neural Nexus Code Review",
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
                if prefix != '-': file_line += 1
                if abs(file_line - line_no) <= ctx: hunk.append(line)
                if file_line > line_no + ctx: break
    return '\n'.join(hunk)

def detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return {
        '.dart': 'Dart/Flutter', '.ts': 'TypeScript/Angular', '.js': 'JavaScript/React',
        '.jsx': 'JavaScript/React', '.tsx': 'TypeScript/React', '.py': 'Python',
        '.java': 'Java', '.cs': '.NET C#', '.go': 'Go', '.html': 'HTML',
        '.htm': 'HTML', '.css': 'CSS', '.scss': 'SCSS/Sass', '.less': 'Less'
    }.get(ext, 'general programming')

FENCE_BY_LANG = {
    'Dart/Flutter':'dart', 'TypeScript/Angular':'ts', 'JavaScript/React':'js',
    'TypeScript/React':'ts', 'Python':'python', 'Java':'java', '.NET C#':'csharp',
    'Go':'go', 'HTML':'html', 'CSS':'css', 'SCSS/Sass':'scss', 'Less':'less',
    'general programming':''
}

# ── 6) COLLECT ISSUES FROM LINTERS ─────────────────────────────────────

issues = []

# ESLint
if isinstance(eslint_report, list):
    for rep in eslint_report:
        path = os.path.relpath(rep.get('filePath',''))
        if path in changed_files:
            for msg in rep.get('messages', []):
                ln = msg.get('line')
                if ln: issues.append({'file':path,'line':ln,'code':msg.get('ruleId','ESLint'),'message':msg.get('message','')})

# Flake8
if isinstance(flake8_report, dict):
    for ap, errs in flake8_report.items():
        path = os.path.relpath(ap)
        if path in changed_files:
            for e in errs:
                ln = e.get('line_number') or e.get('line')
                if ln: issues.append({'file':path,'line':ln,'code':e.get('code','Flake8'),'message':e.get('text','')})

# ShellCheck
if isinstance(shellcheck_report, list):
    for ent in shellcheck_report:
        path = os.path.relpath(ent.get('file',''))
        ln = ent.get('line')
        if path in changed_files and ln: issues.append({'file':path,'line':ln,'code':ent.get('code','ShellCheck'),'message':ent.get('message','')})

# Dart Analyzer
if isinstance(dartanalyzer_report, dict):
    for diag in dartanalyzer_report.get('diagnostics', []):
        loc = diag.get('location', {})
        path = os.path.relpath(loc.get('file',''))
        ln = loc.get('range',{}).get('start',{}).get('line')
        if path in changed_files and ln: issues.append({'file':path,'line':ln,'code':diag.get('code','DartAnalyzer'),'message':diag.get('problemMessage') or diag.get('message','')})

# .NET Format
if isinstance(dotnet_report, dict):
    diags = dotnet_report.get('Diagnostics') or dotnet_report.get('diagnostics')
    if isinstance(diags, list):
        for d in diags:
            path = os.path.relpath(d.get('Path') or d.get('path',''))
            ln = d.get('Region',{}).get('StartLine')
            if path in changed_files and ln: issues.append({'file':path,'line':ln,'code':'DotNetFormat','message':d.get('Message','')})

# HTMLHint
if isinstance(htmlhint_report, list):
    for ent in htmlhint_report:
        path = os.path.relpath(ent.get('file',''))
        ln   = ent.get('line')
        msg  = ent.get('message','')
        rule = ent.get('rule','HTMLHint')
        if path in changed_files and ln: issues.append({'file':path,'line':ln,'code':rule,'message':msg})

# Stylelint
if isinstance(stylelint_report, list):
    for rep in stylelint_report:
        path = os.path.relpath(rep.get('source',''))
        ln   = rep.get('line')
        msg  = rep.get('text','')
        rule = rep.get('rule','Stylelint')
        if path in changed_files and ln: issues.append({'file':path,'line':ln,'code':rule,'message':msg})

# Group by file
file_groups = {}
for issue in issues:
    file_groups.setdefault(issue['file'], []).append(issue)

# ── 7) AI SUGGESTION FUNCTION ─────────────────────────────────────────

def ai_suggest_fix(code: str, patch_ctx: str, file_path: str, line_no: int) -> str:
    lang = detect_language(file_path)
    prompt = dedent(f"""
You are a highly experienced {lang} code reviewer and software architect.

Analyze the diff around line {line_no} in `{file_path}` (reported: {code}):

```diff
{patch_ctx}
```

Output:

Fix:
- Original block and Suggested block (proper code fences).
- If no fix needed, repeat original code.

Refactor:
- Any improvements on structure, clarity or performance.

Why:
- Explain reasoning.
"""
)
    system_prompt = f"You are a senior {lang} reviewer. Provide actionable feedback."
    resp = openai.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{'role':'system','content':system_prompt},{'role':'user','content':prompt}],
        temperature=0.0,
        max_tokens=400
    )
    return resp.choices[0].message.content.strip()

# ── 8) DEVELOPER RATING & TROLL PROMPTS ────────────────────────────────

rating_prompt = dedent(f"""
You are a senior software reviewer.

Evaluate the pull request submitted by @{dev_name} using the following data:

- PR Title: "{title}"  
- Total Issues Detected: {len(issues)}  
- Files Affected: {len(file_groups)}  
- Total Commits: {commits}  
- Lines Added: {additions}  
- Lines Deleted: {deletions}

Respond with:
- A creative title (e.g., "Code Ninja", "Syntax Sorcerer").
- A rating out of 5 stars (⭐️) — use only full stars.
- A one-liner review summary using light-hearted emojis.
"""
)
rating_resp = openai.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role":"system","content":"You are a playful yet insightful code reviewer."},{"role":"user","content":rating_prompt}],
    temperature=0.8,
    max_tokens=120
)
rating = rating_resp.choices[0].message.content.strip()

# Troll Prompt
troll_prompt = dedent("""
Invent a completely new, funny, over-the-top **office prank or office troll** that could happen at a software company.
Requirements:
- Make it DIFFERENT each time you write it
- It can involve Developers, QA, Management, or any other team
- Keep it SHORT (max 5 lines)
- Use plenty of fun emojis

Generate ONE such funny prank now:
"""
)
troll_resp = openai.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role":"system","content":"You are a playful office troll."},{"role":"user","content":troll_prompt}],
    temperature=0.7,
    max_tokens=200
)
troll = troll_resp.choices[0].message.content.strip()

# ── 9) BUILD FINAL MARKDOWN ────────────────────────────────────────────

md = []
md.append(f'<img src="{img_url}" width="100" height="100" />\n')
md.append('# brandOptics AI Neural Nexus\n')
md.append('## 📌 Recommendations & Review Summary\n')
md.append(f"**Summary:** {len(issues)} issue(s) across {len(file_groups)} file(s).\n")
md.append(f"> 🧑‍💻 **Developer Rating for @{dev_name}**\n")
for line in rating.splitlines():
    md.append(f"> {line}\n")
md.append("---\n")
md.append("### Pull Request Metadata\n")
md.append(f"- **Title:** {title}\n")
md.append(f"- **PR Link:** [#{pr_number}]({url})\n")
md.append(f"- **Author:** @{dev_name}\n")
md.append(f"- **Branch:** `{source_branch}` → `{target_branch}`\n")
md.append(f"- **Opened On:** {created_at}\n\n")
md.append("### Change Statistics\n")
md.append(f"- **Commits:** {commits}\n")
md.append(f"- **Lines Added:** {additions}\n")
md.append(f"- **Lines Removed:** {deletions}\n")
md.append(f"- **Files Changed:** {changed_files}\n")
md.append("---\n")
md.append(dedent(f"""
Thanks for your contribution! A few tweaks are needed before we can merge.

🔍 **Key Findings**
1. **Errors & Warnings:** Address any compilation errors or lint violations.
2. **Consistency:** Update naming and formatting to match project conventions.
3. **Clarity:** Simplify complex blocks, remove unused code, and add concise comments.
4. **Performance & Security:** Optimize frequently executed code blocks and ensure all inputs are validated.
5. **Tests & Docs:** Add or update tests for new logic and refresh any related documentation.

💡 **Pro Tip**  
Think in small, focused changes—break large functions into single-purpose units for easier review and maintenance.

Once these tweaks are applied and you push a new commit, I’ll happily re-review and merge! 🚀
"""))
md.append('\n> 🎭 _Prank War Dispatch:_\n')
for line in troll.splitlines():
    md.append(f"> {line}\n")
md.append('\n## 📂 File-wise Issue Breakdown & AI Suggestions\n')

for file_path, file_issues in sorted(file_groups.items()):
    md.append(f"**File:** `{file_path}`\n")
    md.append('| Line No. | Lint Rule / Error Message | Suggested Fix (Summary) |\n')
    md.append('|:--------:|:--------------------------|:------------------------|\n')

    gh_file = next(f for f in pr.get_files() if f.filename == file_path)
    patch = gh_file.patch or ''
    details = []

    for it in sorted(file_issues, key=lambda x: x['line']):
        ln = it['line']
        issue_md = f"`{it['code']}` {it['message']}"
        ctx = get_patch_context(patch, ln)
        ai_out = ai_suggest_fix(it['code'], ctx, file_path, ln)

        lang = detect_language(file_path)
        fence = FENCE_BY_LANG.get(lang, '')
        m = re.search(rf'Fix:\s*```{fence}\n([\s\S]*?)```', ai_out)
        full_fix = m.group(1).strip() if m else ai_out.splitlines()[0].strip()
        summary = ' '.join(full_fix.splitlines()[:3]).replace('|','\\|')
        md.append(f"| {ln} | {issue_md} | `{summary}` |\n")
        details.append((ln, full_fix, ai_out, fence))

    for ln, full_fix, ai_out, fence in details:
        md.append(f"<details>\n<summary><strong>📎 Line {ln} – AI Suggestions & Code Insights</strong></summary>\n\n")
        md.append("**Fix:**\n\n")
        md.append(f"```{fence}\n{full_fix}\n```\n")
        ref = re.search(r'Refactor:\s*([\s\S]*?)(?=\nWhy:|$)', ai_out)
        if ref:
            md.append("**Refactor:**\n")
            md.append(f"{ref.group(1).strip()}\n")
        why = re.search(r'Why:\s*([\s\S]*?)(?=$)', ai_out)
        if why:
            md.append("**Why:**\n")
            md.append(f"{why.group(1).strip()}\n")
        md.append("</details>\n")

if not issues:
    md.clear()
    md.append(f'<img src="{img_url}" width="100" height="100" />\n')
    md.append('# brandOptics Neural AI Review:\n')
    md.append('**No issues found—your code passes all lint checks, follows best practices, and is performance-optimized. 🚀 Great job, developer! Ready to merge!**\n')
    md.append("### Pull Request Metadata\n")
    md.append(f"- **Title:** {title}\n")
    md.append(f"- **PR Link:** [#{pr_number}]({url})\n")
    md.append(f"- **Author:** @{dev_name}\n")
    md.append(f"- **Branch:** `{source_branch}` → `{target_branch}`\n")
    md.append(f"- **Opened On:** {created_at}\n\n")
    md.append("### Change Statistics\n")
    md.append(f"- **Commits:** {commits}\n")
    md.append(f"- **Lines Added:** {additions}\n")
    md.append(f"- **Lines Removed:** {deletions}\n")
    md.append(f"- **Files Changed:** {changed_files}\n")
    md.append('---\n')
    md.append('**🏅 Developer Performance Rating**\n')
    md.append(f'- 👤 **Developer:** @{dev_name}\n')
    md.append('- 🏷️ **Title:** Code Maestro\n')
    md.append('- ⭐⭐⭐⭐⭐\n')
    md.append('- ✨ **Summary:** Clean, efficient, and merge-ready! Keep up the solid work! 💪🔥\n')
    joke_resp = openai.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{"role":"system","content":"You are a witty developer assistant."},{"role":"user","content":"Tell me a short, fun programming joke about clean code reviews."}],
        temperature=0.8,
        max_tokens=40
    )
    joke = joke_resp.choices[0].message.content.strip()
    md.append('---\n')
    md.append(f'💬 Joke for you: {joke}')

# ── 10) POST COMMENT & STATUS ───────────────────────────────────────────

body = '\n'.join(md)
pr.create_issue_comment(body)
repo.get_commit(pr.head.sha).create_status(
    context="brandOptics AI Neural Nexus Code Review",
    state="failure" if issues else "success",
    description=("Issues detected — please refine your code." if issues else "No code issues detected.")
)

print(f"Posted AI review for PR #{pr_number}")