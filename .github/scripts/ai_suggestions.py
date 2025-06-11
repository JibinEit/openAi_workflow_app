import openai
import re
from textwrap import dedent
from utils import detect_language

from pr_data import dev_name, title, issues, file_groups, commits, additions, deletions

def ai_suggest_fix(code: str, patch_ctx: str, file_path: str, line_no: int) -> str:
    lang = detect_language(file_path)
    prompt = dedent(f"""
You are a highly experienced {lang} code reviewer and software architect.

You will carefully analyze the provided code diff to identify **any and all issues** — not just the reported error. 
Check for:
- Syntax errors
- Logic issues
- Naming conventions
- Code style and formatting
- Readability and maintainability
- Code structure and clarity
- Performance optimizations
- Security considerations
- {lang} best practices
- Modern {lang} idioms
- API misuse or potential bugs

Below is the diff around line {line_no} in `{file_path}` (reported error: {code}):
```diff
{patch_ctx}
Provide exactly three labeled sections:

Fix:
  Copy-friendly corrected snippet (include fences if multi-line).
Refactor:
  Higher-level best-practice improvements.
Why:
  Brief rationale.
""")
    system_prompt = (
        f"You are a senior {lang} software architect and code reviewer. "
        "You provide in-depth, actionable feedback, "
        "catching syntax, style, performance, security, naming, and best practices."
    )
    resp = openai.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{'role':'system','content':system_prompt},
                  {'role':'user','content':prompt}],
        temperature=0.0,
        max_tokens=400
    )
    return resp.choices[0].message.content.strip()

def generate_rating():
    rating_prompt = dedent(f"""
You are a senior software reviewer.

Evaluate the pull request submitted by @{dev_name} using the following data:

- PR Title: "{title}"
- Total Issues Detected: {len(issues)}
- Files Affected: {len(file_groups)}
- Total Commits: {commits}
- Lines Added: {additions}
- Lines Deleted: {deletions}

Base your evaluation on code cleanliness, lint adherence, readability, and developer discipline. Consider if the code followed best practices, had minimal issues, and was neatly structured.

Respond with:
- A creative title (e.g., "Code Ninja", "Syntax Sorcerer", etc.)
- A rating out of 5 stars (⭐️) — use only full stars
- A one-liner review summary using light-hearted emojis

Be motivational but fair. If there are many issues, reduce the score accordingly. If it's a clean PR, reward it well.
""")

    rating_resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a playful yet insightful code reviewer."},
            {"role": "user",   "content": rating_prompt}
        ],
        temperature=0.8,
        max_tokens=120
    )
    return rating_resp.choices[0].message.content.strip()