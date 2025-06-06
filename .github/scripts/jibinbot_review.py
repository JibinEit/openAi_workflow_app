#!/usr/bin/env python3
import os
import json
import re
from pathlib import Path

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
full_sha  = event["pull_request"]["head"]["sha"]  # <<< full commit SHA
repo      = gh.get_repo(REPO_NAME)
pr        = repo.get_pull(pr_number)
pr_author = pr.user.login  # to tag in comments


# ── 3) GATHER CHANGED FILES & DIFFS ─────────────────────────────────────
changed_files = []
for f in pr.get_files():
    if f.patch:
        changed_files.append({
            "filename": f.filename,
            "patch":    f.patch
        })

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
    """
    Given a unified diff 'patch' and a 1-based 'target_line' in the new file,
    return the 0-based 'position' in that diff where the new-file line occurs.
    Returns None if not found in the hunk.
    """
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
issues: list[dict] = []  # Each: {"file": str, "line": int, "message": str}

# 6.1) ESLint → array of { filePath, messages:[{line, ruleId, message, severity}] }
if isinstance(eslint_report, list):
    for file_report in eslint_report:
        abs_path = file_report.get("filePath")
        if not abs_path:
            continue
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        for msg in file_report.get("messages", []):
            line     = msg.get("line")
            rule     = msg.get("ruleId") or ""
            text     = msg.get("message") or ""
            severity = msg.get("severity", 0)
            sev_text = "Error" if severity == 2 else "Warning"
            full_msg = f"ESLint ({sev_text}): [{rule}] {text}"
            if line:
                issues.append({
                    "file":    rel_path,
                    "line":    line,
                    "message": full_msg
                })

# 6.2) Flake8 → dict of { abs_path: [ {line_number, code, text}, ... ] }
if isinstance(flake8_report, dict):
    for abs_path, errors in flake8_report.items():
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        for err in errors:
            line = err.get("line_number") or err.get("line") or None
            code = err.get("code") or ""
            text = err.get("text") or ""
            if line:
                full_msg = f"Flake8: [{code}] {text}"
                issues.append({
                    "file":    rel_path,
                    "line":    line,
                    "message": full_msg
                })

# 6.3) ShellCheck → array of { file, line, code, message }
if isinstance(shellcheck_report, list):
    for entry in shellcheck_report:
        abs_path = entry.get("file")
        line     = entry.get("line")
        code     = entry.get("code") or ""
        text     = entry.get("message") or ""
        rel_path = os.path.relpath(abs_path, start=os.getcwd())
        if line:
            issues.append({
                "file":    rel_path,
                "line":    line,
                "message": f"ShellCheck: [{code}] {text}"
            })

# 6.4) Dart Analyzer → { "issues": [ { location:{file, range:{start:{line}}}, message }, ... ] }
if isinstance(dartanalyzer_report, dict):
    for issue in dartanalyzer_report.get("issues", []):
        loc        = issue.get("location", {})
        abs_path   = loc.get("file")
        range_info = loc.get("range", {}).get("start", {})
        line       = range_info.get("line")
        text       = issue.get("message") or ""
        rel_path   = os.path.relpath(abs_path, start=os.getcwd())
        if line:
            issues.append({
                "file":    rel_path,
                "line":    line,
                "message": f"Dart Analyzer: {text}"
            })

# 6.5) .NET Format → { "Diagnostics": [ { Path, Region:{StartLine}, Message }, ... ] }
if isinstance(dotnet_report, dict):
    diags = dotnet_report.get("Diagnostics") or dotnet_report.get("diagnostics")
    if isinstance(diags, list):
        for d in diags:
            abs_path = d.get("Path") or d.get("path") or ""
            region   = d.get("Region") or d.get("region") or {}
            line     = region.get("StartLine") or region.get("startLine") or None
            message  = d.get("Message") or d.get("message") or ""
            if abs_path and line:
                rel_path = os.path.relpath(abs_path, start=os.getcwd())
                issues.append({
                    "file":    rel_path,
                    "line":    line,
                    "message": f".NET Format: {message}"
                })


# ── 7) POST INLINE COMMENTS FOR EACH ISSUE ───────────────────────────────
summary_issues: list[str] = []

for issue in issues:
    file_path = issue["file"]
    line_num  = issue["line"]
    msg       = issue["message"]

    # Only attempt inline if the file was changed in this PR
    matching = [c for c in changed_files if c["filename"] == file_path]
    if not matching:
        summary_issues.append(f"- `{file_path}`:{line_num} → {msg}")
        continue

    patch    = matching[0]["patch"]
    position = compute_diff_position(patch, line_num)
    if position is None:
        summary_issues.append(f"- `{file_path}`:{line_num} → {msg}")
        continue

    body = f"@{pr_author} ⚠️ {msg}"
    try:
        # Positional arguments: (body, commit_id, path, position)
        pr.create_review_comment(body, full_sha, file_path, position)
    except Exception as e:
        summary_issues.append(f"- `{file_path}`:{line_num} → {msg} (failed inline: {e})")


# ── 8) IF ANY ISSUES REMAIN, POST A SUMMARY COMMENT ──────────────────────
if summary_issues:
    combined = (
        "**🔎 JibinBot found issues that couldn’t be placed inline:**\n\n"
        + "\n".join(summary_issues)
    )
    pr.create_issue_comment(combined)


# ── 9) DISABLE MERGE IF SERIOUS ISSUES ──────────────────────────────────
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


# ── 10) RUN AI‐DRIVEN CODE REVIEW & SUGGESTIONS ──────────────────────────
def build_review_prompt(changed_files, linter_reports):
    """
    Now we ask GPT to review each file, point out bad patterns,
    and suggest coding‐standard improvements (no specific line numbers).
    """
    instructions = (
        "You are **JibinBot**, an expert code reviewer.\n\n"
        "For each changed file below, do the following:\n"
        "  1. Point out major code‐quality issues or design flaws.\n"
        "  2. Suggest specific coding‐standard improvements (naming, spacing, best practices).\n"
        "  3. Give examples of how to refactor small snippets if applicable.\n\n"
        "Do NOT reference exact line numbers—just speak in terms of the file and code contexts.\n\n"
        "Format your response as Markdown with headings:\n"
        "  ### File: path/to/file.ext\n"
        "- <Your code‐review bullet points>\n\n"
    )

    prompt = instructions

    # Append each diff
    for c in changed_files:
        prompt += (
            f"\n\n---\n**Diff for file:** `{c['filename']}`\n"
            f"```\n{c['patch']}\n```\n"
        )

    # Append raw JSON under each heading
    prompt += "\n\n---\n**Linter outputs (raw JSON):**\n"
    for name, report in [
        ("ESLINT",        eslint_report),
        ("FLAKE8",        flake8_report),
        ("SHELLCHECK",    shellcheck_report),
        ("DARTANALYZER",  dartanalyzer_report),
        (".NET_FORMAT",   dotnet_report),
    ]:
        if report:
            snippet = json.dumps(report, indent=2)
            prompt += f"\n**{name}**:\n```\n{snippet}\n```\n"
        else:
            prompt += f"\n**{name}**: _No issues or not applicable_\n"

    return prompt


full_prompt = build_review_prompt(
    changed_files,
    {
        "eslint":        eslint_report,
        "flake8":        flake8_report,
        "shellcheck":    shellcheck_report,
        "dartanalyzer":  dartanalyzer_report,
        "dotnet_format": dotnet_report,
    }
)


def call_openai_review(prompt: str) -> str:
    try:
        response = openai.chat.completions.create(
            model       = "gpt-4o-mini",
            messages    = [
                {"role": "system", "content": "You are JibinBot, an expert code reviewer."},
                {"role": "user",   "content": prompt},
            ],
            temperature = 0.2,
            max_tokens  = 1200
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        err = str(e)
        if "quota" in err or "insufficient_quota" in err:
            return "❌ **OpenAI quota exceeded.** Please top up your credits."
        return f"❌ **JibinBot encountered an OpenAI error:** {e}"


review_text = call_openai_review(full_prompt)
pr.create_issue_comment(
    f"## 🤖 JibinBot – File‐Level Code Review & Suggestions\n\n{review_text}"
)

print(f"✅ JibinBot posted inline comments, status, and detailed review on PR #{pr_number}.")