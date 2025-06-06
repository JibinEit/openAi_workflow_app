#!/usr/bin/env python3
import os
import json
import re
from pathlib import Path
from textwrap import wrap

import openai
from github import Github

# ── 1) ENVIRONMENT & CLIENT SETUP ───────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BOT_TOKEN      = os.getenv("GITHUB_TOKEN")     # Your machine‐user PAT
REPO_NAME      = os.getenv("GITHUB_REPOSITORY") # e.g. "username/repo"
EVENT_PATH     = os.getenv("GITHUB_EVENT_PATH") # path to the PR event JSON

if not OPENAI_API_KEY or not BOT_TOKEN:
    print("⛔️ Missing either OPENAI_API_KEY or GITHUB_TOKEN.")
    exit(1)

openai.api_key = OPENAI_API_KEY
gh = Github(BOT_TOKEN)


# ── 2) READ THE PULL REQUEST PAYLOAD ────────────────────────────────────
with open(EVENT_PATH, "r") as f:
    event = json.load(f)

pr_number = event["pull_request"]["number"]
full_sha  = event["pull_request"]["head"]["sha"]  # Full commit SHA
repo      = gh.get_repo(REPO_NAME)
pr        = repo.get_pull(pr_number)


# ── 3) GATHER CHANGED FILES & DIFFS ─────────────────────────────────────
changed_files = [f.filename for f in pr.get_files() if f.patch]

if not changed_files:
    pr.create_issue_comment(
        "👀 JibinBot: No textual changes detected—nothing to review."
    )
    repo.get_commit(full_sha).create_status(
        context     = "JibinBot/code-review",
        state       = "success",
        description = "No issues detected"
    )
    exit(0)


# ── 4) READ LINTER OUTPUTS ──────────────────────────────────────────────
def load_json_if_exists(path: Path):
    if path.exists():
        text = path.read_text().strip()
        if text:
            try:
                return json.loads(text)
            except Exception as e:
                print(f"⚠️ Failed to parse JSON from {path}: {e}")
                return None
        return None
    return None


reports_dir = Path(".github/linter-reports")
eslint_report       = load_json_if_exists(reports_dir / "eslint.json")
flake8_report       = load_json_if_exists(reports_dir / "flake8.json")
shellcheck_report   = load_json_if_exists(reports_dir / "shellcheck.json")
dartanalyzer_report = load_json_if_exists(reports_dir / "dartanalyzer.json")
dotnet_report       = load_json_if_exists(reports_dir / "dotnet-format.json")


# ── 5) HELPER: COMPUTE DIFF POSITION FOR INLINE COMMENT ─────────────────
def compute_diff_position(patch: str, target_line: int) -> int | None:
    position = 0
    new_line = None
    for row in patch.splitlines():
        if row.startswith("@@"):
            m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", row)
            if m:
                new_line = int(m.group(1)) - 1
            continue
        if new_line is None:
            continue
        if row.startswith("+") or row.startswith(" "):
            new_line += 1
            if new_line == target_line:
                return position
            position += 1
    return None


# ── 6) EXTRACT ALL ISSUES FROM LINTER OUTPUTS ───────────────────────────
issues: list[dict] = []  # Each: {"file": str, "line": int, "code": str, "message": str}

# ESLint
if isinstance(eslint_report, list):
    for file_report in eslint_report:
        abs_path = file_report.get("filePath")
        if not abs_path:
            continue
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path not in changed_files:
            continue
        for msg in file_report.get("messages", []):
            line     = msg.get("line")
            code     = msg.get("ruleId") or ""
            text     = msg.get("message") or ""
            severity = msg.get("severity", 0)
            sev_text = "Error" if severity == 2 else "Warning"
            full_msg = f"{sev_text}: [{code}] {text}"
            if line:
                issues.append({
                    "file":    rel_path,
                    "line":    line,
                    "code":    code or "ESLint",
                    "message": full_msg
                })

# Flake8
if isinstance(flake8_report, dict):
    for abs_path, errors in flake8_report.items():
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path not in changed_files:
            continue
        for err in errors:
            line = err.get("line_number") or err.get("line") or None
            code = err.get("code") or ""
            text = err.get("text") or ""
            if line:
                issues.append({
                    "file":    rel_path,
                    "line":    line,
                    "code":    code,
                    "message": f"Warning: [{code}] {text}"
                })

# ShellCheck
if isinstance(shellcheck_report, list):
    for entry in shellcheck_report:
        abs_path = entry.get("file")
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path not in changed_files:
            continue
        line = entry.get("line")
        code = entry.get("code") or ""
        text = entry.get("message") or ""
        if line:
            issues.append({
                "file":    rel_path,
                "line":    line,
                "code":    code,
                "message": f"Warning: [{code}] {text}"
            })

# Dart Analyzer
if isinstance(dartanalyzer_report, dict):
    for issue in dartanalyzer_report.get("issues", []):
        loc        = issue.get("location", {})
        abs_path   = loc.get("file")
        rel_path   = os.path.relpath(abs_path, start=os.getcwd())
        if rel_path not in changed_files:
            continue
        range_info = loc.get("range", {}).get("start", {})
        line       = range_info.get("line")
        text       = issue.get("message") or ""
        if line:
            issues.append({
                "file":    rel_path,
                "line":    line,
                "code":    "DartAnalyzer",
                "message": f"Warning: {text}"
            })

# .NET Format (SARIF‐like)
if isinstance(dotnet_report, dict):
    diags = dotnet_report.get("Diagnostics") or dotnet_report.get("diagnostics")
    if isinstance(diags, list):
        for d in diags:
            abs_path = d.get("Path") or d.get("path") or ""
            rel_path = os.path.relpath(abs_path, start=os.getcwd())
            if rel_path not in changed_files:
                continue
            region  = d.get("Region") or d.get("region") or {}
            line    = region.get("StartLine") or region.get("startLine") or None
            message = d.get("Message") or d.get("message") or ""
            if line:
                issues.append({
                    "file":    rel_path,
                    "line":    line,
                    "code":    "DotNetFormat",
                    "message": f"Warning: {message}"
                })


# ── 7) BUILD SUMMARY WITH SUGGESTIONS ───────────────────────────────────
def get_original_line(path: str, line_no: int) -> str:
    try:
        with open(path, "r") as f:
            lines = f.readlines()
            # 1-based line_no; ensure within bounds
            if 1 <= line_no <= len(lines):
                return lines[line_no - 1].rstrip("\n")
    except Exception:
        pass
    return ""


def auto_suggest_fix(code: str, original: str) -> str:
    """
    Provide a basic suggestion based on common lint codes:
      - E221/E251/E261: collapse multiple spaces to single space
      - E501: wrap long lines at 79 chars
      - unused imports/vars: comment out or remove
      - print in production: replace with logger
    If no rule matches, return a generic placeholder.
    """
    if code.startswith("E221") or code.startswith("E251") or code.startswith("E261"):
        # collapse multiple spaces
        return re.sub(r" {2,}", " ", original)
    if code.startswith("E501"):
        # wrap long line
        wrapped = wrap(original, width=79)
        return "\n".join(wrapped)
    if code in ("unused-import", "F401", "unused-variable"):
        return f"# Remove the unused code:\n# {original}"
    if "print" in original and code.lower().startswith("avoid_print"):
        return original.replace("print", "logger.info")
    # Generic placeholder
    return f"# Suggestion: {original}"


# Organize by file → list of issues
file_to_issues: dict[str, list[dict]] = {}
for issue in issues:
    file_to_issues.setdefault(issue["file"], []).append(issue)

# Build summary comment in Markdown
md = ["## 🤖 JibinBot – Code Review Suggestions\n"]

for file_path, file_issues in file_to_issues.items():
    md.append(f"### File: `{file_path}`\n")
    for issue in sorted(file_issues, key=lambda x: x["line"]):
        ln = issue["line"]
        code = issue["code"]
        msg = issue["message"]
        original = get_original_line(file_path, ln)
        suggested = auto_suggest_fix(code, original)

        md.append(f"- **Line {ln}**: {msg}\n")
        if original:
            md.append("  ```python\n")
            md.append(f"  {original}\n")
            md.append("  ```\n")
        if suggested:
            md.append("  **Suggested:**\n")
            md.append("  ```python\n")
            # Indent multi-line suggestions by two spaces
            for s_line in suggested.split("\n"):
                md.append(f"  {s_line}\n")
            md.append("  ```\n")
    md.append("\n")

if not issues:
    md.append("No lint or analyzer issues found.\n")

summary_body = "\n".join(md)

# Post the summary
pr.create_issue_comment(summary_body)

# ── 8) DISABLE MERGE IF SERIOUS ISSUES ──────────────────────────────────
if issues:
    repo.get_commit(full_sha).create_status(
        context     = "JibinBot/code-review",
        state       = "failure",
        description = "Serious code issues detected"
    )
else:
    repo.get_commit(full_sha).create_status(
        context     = "JibinBot/code-review",
        state       = "success",
        description = "No code issues detected"
    )

print(f"✅ JibinBot posted summary suggestions on PR #{pr_number}.")