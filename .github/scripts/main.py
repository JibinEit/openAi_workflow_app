#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from textwrap import dedent

# Add the directory containing this script to sys.path
# This is crucial for allowing 'main.py' to import other modules (e.g., github_utils)
# that are located in the same '.github/scripts/' directory.
script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(script_dir))

# Import core Python modules
import json # Used for parsing GitHub event payload

# Import functions from your custom modules
import github_utils    # For GitHub API interactions
import linter_parsers  # For loading and parsing linter reports
import ai_services     # For OpenAI API calls
import formatters      # For Markdown formatting and data extraction
import time_utils      # For time zone conversions

# --- 1) SETUP & INITIALIZATION ────────────────────────────────────────────────
# Retrieve essential environment variables provided by GitHub Actions or secrets.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
REPO_NAME      = os.getenv("GITHUB_REPOSITORY") # Format: 'owner/repo'
EVENT_PATH     = os.getenv("GITHUB_EVENT_PATH") # Path to the JSON payload of the GitHub event
# Target timezone: Read from environment variable, default to 'Asia/Kolkata' if not set.
TARGET_TIMEZONE_NAME = os.getenv("TARGET_TIMEZONE", "Asia/Kolkata")

# Validate that required environment variables are present.
if not OPENAI_API_KEY or not GITHUB_TOKEN:
    print("⛔️ Missing OpenAI API key or GitHub token.")
    print("Please ensure OPENAI_API_KEY secret and GITHUB_TOKEN are set in your workflow.")
    sys.exit(1) # Exit with a non-zero code to indicate failure

# Initialize GitHub and OpenAI clients using their respective utility functions.
gh = github_utils.initialize_github_client(GITHUB_TOKEN)
ai_services.set_openai_api_key(OPENAI_API_KEY)

# --- 2) LOAD PULL REQUEST DATA ────────────────────────────────────────────────
print("🔍 Loading Pull Request data...")
pr_data = github_utils.load_pr_data(EVENT_PATH, REPO_NAME, gh)

# Unpack the dictionary of PR data for easier access.
pr = pr_data['pr']
repo = pr_data['repo']
pr_number = pr_data['pr_number']
full_sha = pr_data['full_sha']
dev_name = pr_data['dev_name']
title = pr_data['title']
body = pr_data['body']
url = pr_data['url']
source_branch = pr_data['source_branch']
target_branch = pr_data['target_branch']
created_at_utc_str = pr_data['created_at_utc_str']
commits = pr_data['commits']
additions = pr_data['additions']
deletions = pr_data['deletions']

# Convert the UTC PR creation time to the specified local timezone.
formatted_created_at = time_utils.format_local_time(created_at_utc_str, TARGET_TIMEZONE_NAME)

# Generate the public URL for your logo asset in the repository.
# Assumes the logo is at '.github/assets/bailogo.png' relative to the repo root.
img_url = github_utils.generate_image_url(REPO_NAME, repo.default_branch, ".github/assets/bailogo.png")

# --- 3) DETECT CHANGED FILES (excluding .github/ changes) ─────────────────────
print("🔄 Detecting changed files...")
# Get a list of files that were changed in the PR, excluding any within the .github/ directory.
changed_files_list = github_utils.get_changed_files_in_pr(pr)

# If no relevant code changes are detected, post a specific comment and exit early.
if not changed_files_list:
    comment_body = dedent(f"""
    <img src="{img_url}" width="100" height="100" />

    # brandOptics AI Neural Nexus

    ## Review: ✅ No Relevant Changes Detected

    No actionable code changes were found in this PR.
    Everything looks quiet on the commit front — nothing to analyze right now. 😌

    💡 **Note**
    Make sure your changes include source code updates (excluding config/docs only) to trigger a meaningful review.
    """)
    github_utils.post_comment(pr, comment_body)
    github_utils.set_commit_status(repo, full_sha, "success", "No relevant code changes detected.", "brandOptics AI Neural Nexus Code Review")
    sys.exit(0) # Exit successfully as no code review is needed

# --- 4) LOAD LINTER REPORTS AND COLLECT ISSUES ────────────────────────────────
print("📚 Loading and parsing linter reports...")
# Define the path to where linter JSON reports are expected, relative to the repo root.
reports_dir = Path('.github/linter-reports')
all_reports = linter_parsers.load_all_linter_reports(reports_dir)
# Collect and standardize issues, filtering to only include those from changed files.
issues = linter_parsers.collect_all_issues(all_reports, changed_files_list)

# --- 5) GROUP ISSUES BY FILE ──────────────────────────────────────────────────
print(" organizing issues by file...")
# Organize the flat list of issues into a dictionary grouped by file path.
file_groups = {}
for issue in issues:
    file_groups.setdefault(issue['file'], []).append(issue)

# --- 6) GENERATE AI CONTENT (Rating, Jokes) ───────────────────────────────────
print("🤖 Generating AI content (developer rating, jokes)...")
# Get an AI-driven rating for the developer's performance in this PR.
rating = ai_services.get_developer_rating(dev_name, title, len(issues), len(file_groups), commits, additions, deletions)
# Get fun AI-generated jokes.
troll_joke = ai_services.get_troll_joke()
dev_humor_joke = ai_services.get_dev_humor_joke()

# --- 7) BUILD FINAL PULL REQUEST COMMENT MARKDOWN ─────────────────────────────
print("📝 Building PR comment markdown...")
md = [] # Initialize a list to accumulate all Markdown lines for the comment.

# Add the brand logo and main review title.
md.append(f'<img src="{img_url}" width="100" height="100" />')
md.append('')
md.append('# brandOptics AI Neural Nexus Review')
md.append('')

# Add review summary and general recommendations.
md.append("## 📊 Review Summary & Recommendations")
md.append("")
md.append(f"Detected **{len(issues)} issue(s)** across **{len(file_groups)} file(s)** in this Pull Request.")
md.append("")

# Add the AI-generated developer performance rating.
md.append("---")
md.append("### 🏅 Developer Performance Rating")
md.append("")
md.append(">") # Start a Markdown blockquote for the rating
rating_lines = rating.splitlines()
if rating_lines:
    # Clean the title from any markdown formatting the AI might have added.
    cleaned_title = ai_services.clean_rating_title(rating_lines[0])
    md.append(f"> **{cleaned_title}**")
    # Add subsequent lines of the rating to the blockquote.
    for i in range(1, len(rating_lines)):
        md.append(f"> {rating_lines[i]}")
md.append("") # End the blockquote

# Add PR metadata and change statistics formatted as tables.
md.extend(formatters.format_pr_metadata(title, pr_number, url, dev_name,
                                        source_branch, target_branch, formatted_created_at))
md.extend(formatters.format_change_statistics(commits, additions, deletions, changed_files_list))

# Add a standard section of general advice for refining code.
md.append(dedent("""
Thank you for your contribution! A few adjustments are recommended before this Pull Request can be merged.

🔍 **Key Areas for Refinement:**
1.  **Errors & Warnings:** Please address any compilation errors or linting violations identified.
2.  **Code Consistency:** Ensure naming conventions, formatting, and coding styles align with project standards.
3.  **Clarity & Readability:** Simplify complex logic, remove redundant code, and add concise comments where necessary.
4.  **Performance & Security:** Optimize critical code paths and validate all inputs to prevent vulnerabilities.
5.  **Tests & Documentation:** Update existing tests or add new ones for changes in logic, and refresh any relevant documentation.

💡 **Best Practice Tip:**
Consider breaking down large functions or complex changes into smaller, single-purpose units. This improves readability, simplifies testing, and makes future maintenance more manageable.

Once these suggestions are addressed and you push a new commit, I will automatically re-review and provide an updated assessment. 🚀
"""))
md.append('')

# Add the AI-generated "Troll Joke" section.
md.append("> 🎭 _Prank War Dispatch:_")
for line in troll_joke.splitlines():
    md.append(f"> {line}")
md.append('')

# Detailed Issue Breakdown & AI Suggestions section.
md.append('## 📂 Detailed Issue Breakdown & AI Suggestions')
md.append('')

# Get code patches for all files in the PR for AI context.
pr_files_patches = github_utils.get_pr_file_patches(pr)

# Iterate through each file that had issues, sorted by file path.
for file_path, file_issues in sorted(file_groups.items()):
    md.append(f"### File: `{file_path}`")
    md.append('')
    # Create the header for the issues table.
    md.append('| Line No. | Lint Rule / Error Message      | Suggested Fix (Summary)          |')
    md.append('|:--------:|:-------------------------------|:---------------------------------|')

    # Get the specific patch content for the current file.
    patch_for_file = pr_files_patches.get(file_path, '')
    details_for_file = [] # Collects details for collapsible sections for this specific file.

    if file_issues:
        # Iterate through issues within the file, sorted by line number.
        for issue_entry in sorted(file_issues, key=lambda x: x['line']):
            line_num = issue_entry['line']
            issue_markdown = f"`{issue_entry['code']}`: {issue_entry['message']}"
            # Extract relevant code context from the patch for AI analysis.
            context_code = formatters.get_patch_context(patch_for_file, line_num)

            # Call AI service to get a fix suggestion.
            ai_output_raw = ai_services.ai_suggest_fix(
                issue_entry['code'], context_code, file_path, line_num, issue_entry['message']
            )

            # Parse the AI's structured output into its distinct sections.
            analysis, suggested_fix, rationale = formatters.parse_ai_suggestion_output(ai_output_raw)
            # Get a concise summary of the suggested fix for the table.
            summary_for_table = formatters.get_summary_for_table(suggested_fix)

            # Add a row to the issues overview table.
            md.append(f"| {line_num} | {issue_markdown} | `{summary_for_table}` |")
            # Store full details for the collapsible section.
            details_for_file.append({
                'line': line_num,
                'analysis': analysis,
                'full_fix': suggested_fix,
                'rationale': rationale,
            })
    md.append('') # Blank line after the table for this file.

    # Append detailed collapsible sections for each issue in this file.
    if details_for_file:
        for detail in details_for_file:
            md.append('<details>')
            md.append(f'<summary><strong>⚙️ Line {detail["line"]} – Detailed AI Insights ---------------------------------</strong> (click to expand)</summary>')
            md.append('')
            md.append(f'**Analysis:**\n{detail["analysis"]}')
            md.append('')
            md.append(f'**Suggested Fix:**\n{detail["full_fix"]}')
            md.append('')
            md.append(f'**Rationale:**\n{detail["rationale"]}')
            md.append('')
            md.append('</details>')
            md.append('') # Blank line after each detail section.
    md.append('---') # Horizontal rule separator between files.

# Handle the "All Clear" case: if relevant files were changed, but no issues were found.
if not issues and changed_files_list: # Check if issues list is empty, but changed_files_list is NOT empty
    md.clear() # Clear any existing content if we're generating an "All Clear" message.
    md.append(f'<img src="{img_url}" width="100" height="100" />')
    md.append('')
    md.append('# brandOptics AI Neural Nexus Review: All Clear! ✨')
    md.append('')
    md.append(f'Congratulations, @{dev_name}! Your Pull Request has successfully passed all automated code quality checks. Your code is clean, adheres to best practices, and is optimized for performance. 🚀')
    md.append('')
    # Re-add PR Overview and Developer Performance Rating for the "All Clear" case too.
    md.append("---")
    md.extend(formatters.format_pr_metadata(title, pr_number, url, dev_name,
                                            source_branch, target_branch, formatted_created_at))
    md.extend(formatters.format_change_statistics(commits, additions, deletions, changed_files_list))
    md.append("---")
    md.append("### 🏅 Developer Performance Rating")
    md.append("")
    md.append(">") # Start blockquote
    rating_lines = rating.splitlines()
    if rating_lines:
        cleaned_title = ai_services.clean_rating_title(rating_lines[0])
        md.append(f"> **{cleaned_title}**")
        for i in range(1, len(rating_lines)):
            md.append(f"> {rating_lines[i]}")
    md.append("") # End blockquote


# Add Developer Humor Break (for both issue-found and no-issue cases).
md.append('---')
md.append(f'💬 **Developer Humor Break:** {dev_humor_joke}')
md.append('')

# --- 8) POST COMMENT & SET COMMIT STATUS ──────────────────────────────────────
final_comment_body = '\n'.join(md) # Join all Markdown lines into a single string.
github_utils.post_comment(pr, final_comment_body)

# Set the commit status on GitHub based on whether any issues were found.
total_issues = len(issues)
github_utils.set_commit_status(
    repo,
    full_sha,
    'failure' if issues else 'success', # State is 'failure' if issues exist, 'success' otherwise.
    ('Issues detected—please refine your code and push updates.' if issues else 'No code issues detected. Ready for merge!'),
    'brandOptics AI Neural Nexus Code Review' # The name of the status check that appears on GitHub.
)