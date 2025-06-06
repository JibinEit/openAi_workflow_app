#!/usr/bin/env python3
import os
import json
from pathlib import Path

import openai
from github import Github

# ── 1) ENVIRONMENT & CLIENT SETUP ───────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
REPO_NAME      = os.getenv("GITHUB_REPOSITORY")   # e.g. "username/repo"
EVENT_PATH     = os.getenv("GITHUB_EVENT_PATH")   # path to the PR event JSON

if not OPENAI_API_KEY:
    print("⛔️ OpenAI API key not found in environment variable OPENAI_API_KEY.")
    exit(1)

openai.api_key = OPENAI_API_KEY
gh = Github(GITHUB_TOKEN)

# ── 2) READ THE PULL REQUEST PAYLOAD ────────────────────────────────────
with open(EVENT_PATH, "r") as f:
    event = json.load(f)

pr_number = event["pull_request"]["number"]
repo = gh.get_repo(REPO_NAME)
pr   = repo.get_pull(pr_number)

# ── 3) GATHER CHANGED FILES & DIFFS ─────────────────────────────────────
changed_files = []
for f in pr.get_files():
    if f.patch:
        changed_files.append({
            "filename": f.filename,
            "patch": f.patch
        })

if not changed_files:
    pr.create_issue_comment(
        "👀 JibinBot has nothing to review (no text diffs detected)."
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
        else:
            return None
    return None

linter_reports = {}
reports_dir = Path(".github/linter-reports")

linter_reports["eslint"]         = load_json_if_exists(reports_dir / "eslint.json")
linter_reports["flake8"]         = load_json_if_exists(reports_dir / "flake8.json")
linter_reports["shellcheck"]     = load_json_if_exists(reports_dir / "shellcheck.json")
linter_reports["dartanalyzer"]   = load_json_if_exists(reports_dir / "dartanalyzer.json")
linter_reports["dotnet_format"]  = load_json_if_exists(reports_dir / "dotnet-format.json")

# ── 5) BUILD THE GPT PROMPT ──────────────────────────────────────────────
def build_prompt(changed_files, linter_reports):
    instructions = (
        "You are **JibinBot**, an automated code-review assistant. "
        "Your job is to provide detailed feedback on coding best practices, style consistency, "
        "potential bugs, and any lint errors. "
        "Below you will see:\n\n"
        "  • A list of changed files with unified diffs\n"
        "  • JSON outputs from linters: ESLint, Flake8, ShellCheck, Dart Analyzer, and .NET Format\n\n"
        "For each changed file:\n"
        "  1. Summarize any lint errors (if present).\n"
        "  2. Offer suggestions for code‐style improvements or best practices.\n"
        "  3. Point out any potential logical issues or security concerns.\n"
        "  4. Provide line‐level comments in a concise bullet list (if possible).\n\n"
        "Format your response in Markdown. Use headings like:\n"
        "  ### File: path/to/file.ext\n"
        "Then list issues or suggestions.\n\n"
    )

    prompt = instructions

    # 5.1) Append diffs
    for c in changed_files:
        prompt += f"\n\n---\n**Diff for file:** `{c['filename']}`\n```\n{c['patch']}\n```\n"

    # 5.2) Append linter JSON (if available)
    prompt += "\n\n---\n**Lint Reports (raw JSON):**\n"
    for tool, data in linter_reports.items():
        if data:
            snippet = json.dumps(data, indent=2)
            prompt += f"\n**{tool.upper()}**:\n```\n{snippet}\n```\n"
        else:
            prompt += f"\n**{tool.upper()}**: _No issues detected or no files applicable_\n"

    return prompt

full_prompt = build_prompt(changed_files, linter_reports)

# ── 6) CALL OPENAI TO GET REVIEWER FEEDBACK ──────────────────────────────
def call_openai_review(prompt: str) -> str:
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are JibinBot, an expert code reviewer."},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ **JibinBot encountered an error calling OpenAI:** {e}"

review_text = call_openai_review(full_prompt)

# ── 7) POST THE REVIEW AS A PR COMMENT ───────────────────────────────────
comment_body = f"## 🤖 JibinBot – Automated Code Review\n\n{review_text}"
pr.create_issue_comment(comment_body)

print(f"✅ JibinBot posted a review comment on PR #{pr_number}.")