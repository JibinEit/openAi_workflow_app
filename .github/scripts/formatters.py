import re

def get_patch_context(patch: str, line_no: int, ctx: int = 3) -> str:
    """
    Extracts a contextual code snippet from a Git patch around a specific line number.
    This helps the AI understand the code in its surrounding context.

    Args:
        patch (str): The full Git patch string for a file.
        line_no (int): The 1-indexed line number in the *new* file where the issue is.
        ctx (int): The number of lines of context to include before and after the `line_no`.

    Returns:
        str: A multi-line string representing the relevant part of the patch,
             including hunk headers and contextual lines.
    """
    file_line = None # Tracks the current line number in the new file within the patch
    final_context_lines = [] # Stores lines that form the context

    for line in patch.splitlines():
        # Process hunk headers (e.g., '@@ -1,5 +1,5 @@')
        if line.startswith('@@ '):
            final_context_lines.append(line) # Include hunk header in the context
            match = re.match(r'@@ -\d+,\d+ \+(\d+),\d+ @@', line)
            if match:
                # The line number immediately after a hunk header corresponds to the start
                # of the *new* file section in that hunk.
                file_line = int(match.group(1))
            else:
                file_line = None # If parsing fails, reset line tracking
            continue

        if file_line is not None:
            prefix = line[0] # Get the diff prefix ('+', '-', ' ')

            # Check if the current line (in the new file context) is within the desired window
            # We include context lines (' '), additions ('+'), and deletions ('-') if they fall
            # within `ctx` lines of the `line_no`.
            if (prefix in (' ', '+') and abs(file_line - line_no) <= ctx) or \
               (prefix == '-' and (file_line >= line_no - ctx and file_line <= line_no + ctx)):
                final_context_lines.append(line)

            # Increment `file_line` only for lines that exist in the *new* file (context or additions).
            # Deletions ('-') are lines removed, so they don't increment the new file's line count.
            if prefix in (' ', '+'):
                file_line += 1

            # Optimization: If we've processed lines well past our target `line_no`
            # and are no longer in an addition or deletion block related to our context, we can stop.
            if file_line is not None and file_line > line_no + ctx and prefix not in ('-', '+'):
                break

    return '\n'.join(final_context_lines)

def format_pr_metadata(title: str, pr_number: int, url: str, dev_name: str,
                       source_branch: str, target_branch: str, formatted_created_at: str) -> list:
    """
    Returns a list of Markdown lines for the Pull Request metadata table.

    Args:
        title (str): The PR title.
        pr_number (int): The PR number.
        url (str): The PR URL.
        dev_name (str): The developer's GitHub username.
        source_branch (str): The head branch of the PR.
        target_branch (str): The base branch the PR is targeting.
        formatted_created_at (str): The PR creation time formatted as a local string.

    Returns:
        list: A list of strings, each representing a line of Markdown for the table.
    """
    md = []
    md.append("---") # Horizontal rule for separation
    md.append("### 📝 Pull Request Overview")
    md.append("")
    md.append("| Detail               | Value                                                 |")
    md.append("|:---------------------|:------------------------------------------------------|")
    md.append(f"| **Title** | {title}                                               |")
    md.append(f"| **PR Link** | [#{pr_number}]({url})                                  |")
    md.append(f"| **Author** | @{dev_name}                                           |")
    md.append(f"| **Branches** | `{source_branch}` &#8594; `{target_branch}`             |") # Using Unicode arrow for clarity
    md.append(f"| **Opened On** | {formatted_created_at}                                 |")
    return md

def format_change_statistics(commits: int, additions: int, deletions: int, changed_files_list: list) -> list:
    """
    Returns a list of Markdown lines for the change statistics table.

    Args:
        commits (int): Number of commits in the PR.
        additions (int): Total lines added.
        deletions (int): Total lines deleted.
        changed_files_list (list): A list of file paths that were changed.

    Returns:
        list: A list of strings, each representing a line of Markdown for the table.
    """
    md = []
    # Continuing the previous table or starting a new one, depending on how `main.py` uses this.
    # Assuming it extends the previous table's format if it's called immediately after `format_pr_metadata`.
    md.append(f"| **Commits** | {commits}                                             |")
    md.append(f"| **Lines Added** | <span style='color:green;'>+{additions}</span>         |") # Added inline styling for visual emphasis
    md.append(f"| **Lines Removed** | <span style='color:red;'>-{deletions}</span>           |") # Added inline styling
    # Join changed files with backticks for code-like formatting, limit to 5 for brevity in summary
    files_display = [f"`{Path(f).name}`" for f in changed_files_list[:5]]
    if len(changed_files_list) > 5:
        files_display.append(f"... (+{len(changed_files_list) - 5} more)")
    md.append(f"| **Files Changed** | {len(changed_files_list)} ({', '.join(files_display)}) |")
    return md

def parse_ai_suggestion_output(ai_output: str) -> tuple[str, str, str]:
    """
    Parses the AI's structured suggestion output into Analysis, Suggested Fix, and Rationale sections.
    It expects specific markdown headings from the AI response.

    Args:
        ai_output (str): The raw text output from the AI model containing structured sections.

    Returns:
        tuple[str, str, str]: A tuple containing (analysis_content, full_fix_content, rationale_content).
                              Defaults to "No ... provided." if a section is not found.
    """
    analysis_content = "No specific analysis provided."
    full_fix_content = "No suggested fix snippet provided."
    rationale_content = "No rationale provided."

    # Use (?s) for dotall mode to match across multiple lines
    # Use non-greedy quantifiers (.*?) to stop at the next heading
    # Regex lookahead ensures we stop before the start of the next section
    analysis_match = re.search(r'(?s)^\*\*Analysis:\*\*\s*\n(.*?)(?=^\*\*Suggested Fix:\*\*|$)', ai_output, re.MULTILINE)
    if analysis_match:
        analysis_content = analysis_match.group(1).strip()

    suggested_fix_match = re.search(r'(?s)^\*\*Suggested Fix:\*\*\s*\n(.*?)(?=^\*\*Rationale:\*\*|$)', ai_output, re.MULTILINE)
    if suggested_fix_match:
        full_fix_content = suggested_fix_match.group(1).strip()

    rationale_match = re.search(r'(?s)^\*\*Rationale:\*\*\s*\n(.*)$', ai_output, re.MULTILINE)
    if rationale_match:
        rationale_content = rationale_match.group(1).strip()

    return analysis_content, full_fix_content, rationale_content

def get_summary_for_table(full_fix_content: str) -> str:
    """
    Extracts a concise summary from the full suggested fix content for display
    in the detailed issues table. Prioritizes code snippets.

    Args:
        full_fix_content (str): The full 'Suggested Fix' section from the AI output.

    Returns:
        str: A short, single-line summary suitable for a Markdown table cell.
    """
    summary_text_for_table = ""

    # Try to extract the first code block content
    summary_code_match = re.search(r'```(?:\w*\n)?([\s\S]*?)```', full_fix_content)
    if summary_code_match:
        # If a code block is found, take its content
        summary_text_for_table = summary_code_match.group(1).strip()
        # Take the first non-empty line of the code block
        summary_lines = [line.strip() for line in summary_text_for_table.splitlines() if line.strip()]
        if summary_lines:
            summary_text_for_table = summary_lines[0]
        else:
            summary_text_for_table = "Code snippet provided."
    else:
        # Otherwise, take the first line of the general text (if no code block)
        summary_text_for_table = full_fix_content.splitlines()[0] if full_fix_content else "See details for suggested fix."

    # Remove any leading "//", "#", or other common code comment prefixes for cleaner display
    summary_text_for_table = re.sub(r'^\s*(//|#|--|\*)\s*', '', summary_text_for_table).strip()

    # Limit summary length for table conciseness
    if len(summary_text_for_table) > 70: # Arbitrary character limit for table cell
        summary = summary_text_for_table[:67] + '...'
    else:
        summary = summary_text_for_table

    # Escape pipe characters for markdown table integrity
    summary = summary.replace('|', '\\|')

    # Fallback if summary is still empty
    if not summary.strip():
        summary = "See details for suggested fix."
    return summary