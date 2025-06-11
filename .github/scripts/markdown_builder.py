import re
import openai
from ai_suggestions import ai_suggest_fix, generate_rating
from prank_generator import generate_prank
from joke_generator import generate_clean_pr_joke
from utils import get_patch_context, detect_language, FENCE_BY_LANG
from config import repo
from pr_data import pr, issues, file_groups, img_url, dev_name, pr_number, url, title, source_branch, target_branch, created_at, commits, additions, deletions

def build_markdown():
    md = []

    md.append(f'<img src="{img_url}" width="100" height="100" />')
    md.append('# brandOptics AI Neural Nexus')
    md.append('')

    if not issues:
        md.append('**No issues found—your code passes all lint checks, follows best practices, and is performance-optimized. 🚀 Great job, developer! Ready to merge!**')
        md.append('')

        # PR Metadata
        md.append("### Pull Request Metadata")
        md.append(f"- **Title:** {title}")
        md.append(f"- **PR Link:** [#{pr_number}]({url})")
        md.append(f"- **Author:** @{dev_name}")
        md.append(f"- **Branch:** `{source_branch}` → `{target_branch}`")
        md.append(f"- **Opened On:** {created_at}")
        md.append("")

        # Changes
        md.append("### Change Statistics")
        md.append(f"- **Commits:** {commits}")
        md.append(f"- **Lines Added:** {additions}")
        md.append(f"- **Lines Removed:** {deletions}")
        md.append('---')

        md.append('**🏅 Developer Performance Rating**')
        md.append(f'- 👤 **Developer:** @{dev_name}')
        md.append('- 🏷️ **Title:** Code Maestro')
        md.append('- ⭐⭐⭐⭐⭐')
        md.append('- ✨ **Summary:** Clean, efficient, and merge-ready! Keep up the solid work! 💪🔥')
        md.append('')

        # Add joke
        joke = generate_clean_pr_joke()
        md.append('---')
        md.append(f'💬 Joke for you: {joke}')
        return '\n'.join(md)

    # If issues exist, normal flow:

    md.append("## 📌 Recommendations & Review Summary")
    md.append(f"**Summary:** {len(issues)} issue(s) across {len(file_groups)} file(s).")
    md.append('')

    rating = generate_rating()
    md.append(f"> 🧑‍💻 **Developer Rating for @{dev_name}**")
    for line in rating.splitlines():
        md.append(f"> {line}")
    md.append("---")

    md.append("### Pull Request Metadata")
    md.append(f"- **Title:** {title}")
    md.append(f"- **PR Link:** [#{pr_number}]({url})")
    md.append(f"- **Author:** @{dev_name}")
    md.append(f"- **Branch:** `{source_branch}` → `{target_branch}`")
    md.append(f"- **Opened On:** {created_at}")
    md.append("")

    md.append("### Change Statistics")
    md.append(f"- **Commits:** {commits}")
    md.append(f"- **Lines Added:** {additions}")
    md.append(f"- **Lines Removed:** {deletions}")
    md.append("---")

    md.append("Thanks for your contribution! A few tweaks are needed before we can merge.")
    md.append('')

    prank = generate_prank()
    md.append("> 🎭 _Prank War Dispatch:_")
    for line in prank.splitlines():
        md.append(f"> {line}")

    md.append('## 📂 File-wise Issue Breakdown & AI Suggestions')

    for file_path, file_issues in sorted(file_groups.items()):
        md.append(f"**File =>** `{file_path}`")
        md.append('| Line No. | Lint Rule / Error Message | Suggested Fix (Summary) |')
        md.append('|:--------:|:-------------------------------|:---------------------------------|')
        gh_file = next(f for f in pr.get_files() if f.filename == file_path)
        patch = gh_file.patch or ''

        for it in sorted(file_issues, key=lambda x: x['line']):
            ln = it['line']
            issue_md = f"`{it['code']}` {it['message']}"
            ctx = get_patch_context(patch, ln)
            ai_out = ai_suggest_fix(it['code'], ctx, file_path, ln)

            lang = detect_language(file_path)
            fence = FENCE_BY_LANG.get(lang, '')

            fence_re = fence or r'\w*'
            m = re.search(rf'Fix:\s*```{fence_re}\n([\s\S]*?)```', ai_out)
            full_fix = m.group(1).strip() if m else ai_out.splitlines()[0].strip()

            lines = full_fix.splitlines()
            summary = ' '.join(lines[:3]).replace('|','\\|')
            md.append(f"| {ln} | {issue_md} | `{summary}` |")

    return '\n'.join(md)