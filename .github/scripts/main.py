from config import repo
from pr_data import pr, changed_files, issues, file_groups, full_sha
from issue_collector import collect_issues
from markdown_builder import build_markdown

# Collect issues
issues = collect_issues(changed_files)

# Group issues by file
file_groups = {}
for issue in issues:
    file_groups.setdefault(issue['file'], []).append(issue)

# If no files changed
if not changed_files:
    pr.create_issue_comment("✅ No relevant code changes detected.")
    repo.get_commit(full_sha).create_status(
        context="brandOptics AI Neural Nexus Code Review",
        state="success",
        description="No relevant code changes detected."
    )
    exit(0)

# Build final markdown comment
body = build_markdown()
pr.create_issue_comment(body)

repo.get_commit(full_sha).create_status(
    context="brandOptics AI Neural Nexus Code Review",
    state="failure" if issues else "success",
    description=("Issues detected — please refine your code." if issues else "No code issues detected.")
)

print(f"Posted AI review for PR #{pr.number}")