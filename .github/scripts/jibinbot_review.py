#!/usr/bin/env python3
import os, json, re
from pathlib import Path
from textwrap import dedent

import openai
from github import Github

# ── 1) ENVIRONMENT & CLIENT SETUP ───────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
REPO_NAME      = os.getenv("GITHUB_REPOSITORY")
EVENT_PATH     = os.getenv("GITHUB_EVENT_PATH")

if not OPENAI_API_KEY or not GITHUB_TOKEN or not EVENT_PATH or not REPO_NAME:
    print("⛔️ Missing required environment variables.")
    exit(1)

openai.api_key = OPENAI_API_KEY
gh   = Github(GITHUB_TOKEN)
repo = gh.get_repo(REPO_NAME)

# ── 2) READ PR PAYLOAD ────────────────────────────────────────────────
with open(EVENT_PATH) as f:
    event = json.load(f)
pr_number = event["pull_request"]["number"]
full_sha  = event["pull_request"]["head"]["sha"]
pr        = repo.get_pull(pr_number)

# ── 3) COLLECT CHANGED FILES ───────────────────────────────────────────
changed = [f.filename for f in pr.get_files() if f.patch]

if not changed:
    pr.create_issue_comment("👀 brandOptics AI: Nothing changed—no review needed.")
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI/code-review",
        state="success",
        description="No changes to review"
    )
    exit(0)

# ── 4) LOAD LINTER/ANALYZER REPORTS ───────────────────────────────────
def load_json(p: Path):
    try:
        return json.loads(p.read_text())
    except:
        return None

reports = Path(".github/linter-reports")
eslint  = load_json(reports/"eslint.json")
flake8  = load_json(reports/"flake8.json")
shell  = load_json(reports/"shellcheck.json")
dart   = load_json(reports/"dartanalyzer.json")
dotnet = load_json(reports/"dotnet-format.json")

# ── 5) LINE-READER ─────────────────────────────────────────────────────
def get_original_line(path, ln):
    try:
        lines = Path(path).read_text().splitlines()
        return lines[ln-1]
    except:
        return ""

# ── 6) AI FIXER ────────────────────────────────────────────────────────
def ai_suggest_fix(code, original, file_path, line_no):
    prompt = dedent(f"""
        You are a Dart/Flutter expert.  
        In `{file_path}` line {line_no}, this code triggers `{code}`:

        ```dart
        {original}
        ```

        Rewrite only that line (or minimal snippet) so it no longer triggers the error.
        Output only the corrected code—no extra text.
    """).strip()
    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":"You are a helpful Dart/Flutter assistant."},
                {"role":"user","content":prompt}
            ],
            temperature=0.0,
            max_tokens=60
        )
        suggestion = resp.choices[0].message.content.strip()
        return re.sub(r"^```dart\s*|\s*```$", "", suggestion).strip()
    except Exception as e:
        return f"# AI failed: {e}\n{original}"

# ── 7) GATHER ISSUES ───────────────────────────────────────────────────
issues = []

def add(file, line, code, msg):
    if not file or file.startswith(".github/") or file not in changed:
        return
    issues.append({"file":file,"line":line,"code":code,"message":msg})

# ESLint
if isinstance(eslint, list):
    for r in eslint:
        f = os.path.relpath(r.get("filePath",""))
        for m in r.get("messages",[]):
            add(f,m.get("line"),m.get("ruleId") or "ESLint",m.get("message",""))

# Flake8
if isinstance(flake8, dict):
    for fp, errs in flake8.items():
        f = os.path.relpath(fp)
        for e in errs:
            ln = e.get("line_number") or e.get("line")
            add(f,ln,e.get("code"),e.get("text"))

# ShellCheck
if isinstance(shell, list):
    for e in shell:
        f = os.path.relpath(e.get("file",""))
        add(f,e.get("line"),e.get("code"),e.get("message"))

# Dart Analyzer
if isinstance(dart, dict):
    for d in dart.get("diagnostics",[]):
        loc = d.get("location",{})
        f   = os.path.relpath(loc.get("file",""))
        ln  = loc.get("range",{}).get("start",{}).get("line")
        add(f,ln,d.get("code","DartAnalyzer"),d.get("problemMessage") or d.get("message",""))

# .NET Format
if isinstance(dotnet, dict):
    for d in (dotnet.get("Diagnostics") or dotnet.get("diagnostics") or []):
        f  = os.path.relpath(d.get("Path") or "")
        ln = (d.get("Region") or {}).get("StartLine")
        add(f,ln,"DotNetFormat",d.get("Message") or d.get("message",""))

# ── 8) BUILD CINEMATIC COMMENT ─────────────────────────────────────────
if issues:
    errs  = [i for i in issues if "Error" in i["message"]]
    warns = [i for i in issues if "Warning" in i["message"]]
    infos = len(issues)-len(errs)-len(warns)

    header = f"""
🤖 **brandOptics Neural Intelligence Report**  
*Deep-dive automated analysis at your fingertips.*

---

### 🚨 Summary  
**{len(errs)} Errors • {len(warns)} Warnings • {infos} Infos**

---
"""
    parts = [header]

    parts.append("## ❌ Errors\n")
    for idx, it in enumerate(errs,1):
        orig  = get_original_line(it["file"], it["line"])
        fix   = ai_suggest_fix(it["code"], orig, it["file"], it["line"])
        parts.append(dedent(f"""
        **{idx}.**  
        • **`{it['code']}`** in `{it['file']}` (Line {it['line']})  
          ↳ _Issue:_ {it['message']}  
          ↳ _AI-Suggested Fix:_  
          ```dart
          {fix}
          ```
        """).rstrip())

    if warns:
        parts.append("\n## ⚠️ Warnings\n")
        for it in warns:
            parts.append(f"- `{it['code']}` in `{it['file']}` (Line {it['line']}): {it['message']}")

    parts.append("\n## 🧹 Cosmetic Tidy\n")
    parts.append("> You may batch-apply these low-priority style tweaks later:\n")
    parts.append("- _e.g. prefer `const` constructors for immutables_\n")

    footer = dedent("""
    ---
    ✨ **Next Steps:**  
    1. Apply the AI-suggested fixes above.  
    2. Commit & push; this check will turn green when clean.  
    3. Reply for deeper insights or custom guidance.

*Powered by brandOptics Neural Intelligence — your AI code coach.* 🚀
    """).strip()
    parts.append(footer)

    comment = "\n".join(parts)

    pr.create_issue_comment(comment)
    pr.create_review(
        body="🔧 brandOptics AI found critical code issues—please address before merging.",
        event="REQUEST_CHANGES"
    )
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI/code-review", state="failure",
        description="❌ Critical issues found"
    )

else:
    comment = dedent("""
    🤖 **brandOptics Neural Intelligence Report**  
    *All clear on the neural network front!*

    🎉 **No errors or warnings detected.**  
    Excellent work—your code has passed the brandOptics neural analysis with flying colors.

    *— brandOptics Neural Intelligence Engine* 🚀
    """).strip()

    pr.create_issue_comment(comment)
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI/code-review", state="success",
        description="✅ No code issues detected"
    )

print(f"✅ brandOptics review done on PR #{pr_number}.")