#!/usr/bin/env python3
import os, json, re
from pathlib import Path
from textwrap import dedent

import openai
from github import Github

# ── CONFIG & SETUP ─────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
REPO_NAME      = os.getenv("GITHUB_REPOSITORY")
EVENT_PATH     = os.getenv("GITHUB_EVENT_PATH")

if not OPENAI_API_KEY or not GITHUB_TOKEN:
    print("⛔️ Missing OPENAI_API_KEY or GITHUB_TOKEN.")
    exit(1)

openai.api_key = OPENAI_API_KEY
gh             = Github(GITHUB_TOKEN)
with open(EVENT_PATH) as f:
    event       = json.load(f)

pr_number      = event["pull_request"]["number"]
full_sha       = event["pull_request"]["head"]["sha"]
repo           = gh.get_repo(REPO_NAME)
pr             = repo.get_pull(pr_number)

# ── COLLECT CHANGED FILES ────────────────────────────────────────────────
changed_files = [f.filename for f in pr.get_files() if f.patch]
if not changed_files:
    pr.create_issue_comment(
        "👀 **brandOptics AI** found no code changes to review."
    )
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI/code-review",
        state="success",
        description="Nothing to review"
    )
    exit(0)

# ── LOAD LINTER REPORTS ─────────────────────────────────────────────────
def load_json(path):
    if path.exists() and path.read_text().strip():
        try: return json.loads(path.read_text())
        except: return None
    return None

reports_dir          = Path(".github/linter-reports")
eslint_report        = load_json(reports_dir / "eslint.json")
flake8_report        = load_json(reports_dir / "flake8.json")
shellcheck_report    = load_json(reports_dir / "shellcheck.json")
dartanalyzer_report  = load_json(reports_dir / "dartanalyzer.json")
dotnet_report        = load_json(reports_dir / "dotnet-format.json")

# ── GATHER ISSUES ────────────────────────────────────────────────────────
issues = []  # {file, line, severity, code, message}

def add_issue(fp, ln, sev, code, msg):
    if not fp.startswith(".github/"):
        issues.append({"file": fp, "line": ln, "sev": sev, "code": code, "msg": msg})

# ESLint
if isinstance(eslint_report, list):
    for fr in eslint_report:
        rp = os.path.relpath(fr.get("filePath",""), os.getcwd())
        if rp in changed_files:
            for m in fr.get("messages",[]):
                sev = "Error" if m.get("severity")==2 else "Warning"
                add_issue(rp, m["line"], sev, m.get("ruleId","ESLint"), m["message"])

# Flake8
if isinstance(flake8_report, dict):
    for ap, errs in flake8_report.items():
        rp = os.path.relpath(ap, os.getcwd())
        if rp in changed_files:
            for e in errs:
                add_issue(rp, e["line_number"], "Warning", e["code"], e["text"])

# ShellCheck
if isinstance(shellcheck_report, list):
    for e in shellcheck_report:
        rp = os.path.relpath(e.get("file",""), os.getcwd())
        if rp in changed_files:
            add_issue(rp, e["line"], "Warning", e.get("code","SC"), e["message"])

# Dart Analyzer
if isinstance(dartanalyzer_report, dict):
    for d in dartanalyzer_report.get("diagnostics",[]):
        loc = d.get("location",{})
        rp  = os.path.relpath(loc.get("file",""), os.getcwd())
        if rp in changed_files:
            ln  = loc.get("range",{}).get("start",{}).get("line")
            sev = d.get("severity","Info").title()
            add_issue(rp, ln, sev, d.get("code","Dart"), d.get("problemMessage",""))

# .NET
if isinstance(dotnet_report, dict):
    for d in dotnet_report.get("Diagnostics",[]) or dotnet_report.get("diagnostics",[]):
        rp = os.path.relpath(d.get("Path",d.get("path","")), os.getcwd())
        ln = (d.get("Region") or d.get("region") or {}).get("StartLine")
        if rp in changed_files and ln:
            add_issue(rp, ln, "Warning", "DotNet", d.get("Message",d.get("message","")))

# ── UTILITY: READ LINE, CALL AI ────────────────────────────────────────
def fetch_line(fp, ln):
    try:
        lines = Path(fp).read_text().splitlines()
        return lines[ln-1] if 1<=ln<=len(lines) else ""
    except: return ""

def ai_fix(code, original, fp, ln):
    prompt = dedent(f"""
      You are a Dart/Flutter expert. Fix line {ln} in `{fp}` to satisfy `{code}`:

      ```dart
      {original}
      ```

      Output only the corrected snippet.
    """).strip()
    try:
        r = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
              {"role":"system","content":"You are a precision coding assistant."},
              {"role":"user","content":prompt}
            ],
            temperature=0,
            max_tokens=60
        )
        out = r.choices[0].message.content.strip()
        return re.sub(r"^```.*?```","", out).strip()
    except Exception as e:
        return f"// AI error: {e}"

# ── BUILD COMMENT ──────────────────────────────────────────────────────
md = ["## 🤖 brandOptics AI — Code Review Report\n"]

# 1) Cheat-Sheet summary
counts = {"Error":0,"Warning":0,"Info":0}
for i in issues: counts[i["sev"]]+=1
md.append(f"**Summary:** {counts['Error']} Errors • {counts['Warning']} Warnings • {counts['Info']} Infos\n")

# 2) Critical Errors first
for sev in ("Error","Warning"):
    block = [i for i in issues if i["sev"]==sev]
    if not block: continue
    md.append(f"### {sev}s\n")
    for i in sorted(block, key=lambda x:(x["file"],x["line"])):
        orig = fetch_line(i["file"],i["line"]).strip()
        fix  = ai_fix(i["code"],orig,i["file"],i["line"])
        md.append(f"- **{i['file']}:{i['line']}** `{i['code']}` • {i['msg']}\n")
        md.append(f"  ```dart\n  {orig}\n  -> {fix}\n  ```\n")
    md.append("")

# 3) Cosmetic tidy (Infos)
infos = [i for i in issues if i["sev"]=="Info"]
if infos:
    md.append("### Cosmetic Tidy 🧹\n> These are low-priority style tips you may batch-apply\n")
    for i in infos:
        md.append(f"- `{i['code']}` in `{i['file']}:{i['line']}` • {i['msg']}")
    md.append("")

if not issues:
    md.append("✅ **No issues detected.** Great work keeping things spotless!\n")

body = "\n".join(md)

pr.create_issue_comment(body)
repo.get_commit(full_sha).create_status(
    context="brandOptics AI/code-review",
    state="failure" if counts["Error"] else "success",
    description=(
      "❌ Fix errors before merging" if counts["Error"]
      else "✅ All checks passed"
    )
)

if counts["Error"]:
    pr.create_review(
        event="REQUEST_CHANGES",
        body=dedent(f"""
          ⚠️ **{counts['Error']} Errors detected!**  
          Please address the errors above before merging.
        """).strip()
    )

print(f"✅ brandOptics AI report posted on PR #{pr_number}")