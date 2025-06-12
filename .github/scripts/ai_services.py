import openai
from textwrap import dedent
import re
from pathlib import Path # Required for _detect_language helper

# Global variable to hold the OpenAI API key, set once at startup
_OPENAI_API_KEY = None

def set_openai_api_key(key: str):
    """
    Sets the OpenAI API key for the openai module.
    This function must be called once at the start of your program.
    """
    global _OPENAI_API_KEY
    _OPENAI_API_KEY = key
    openai.api_key = key

def _get_openai_client():
    """
    Returns the OpenAI client instance.
    Raises a ValueError if the API key has not been set.
    """
    if _OPENAI_API_KEY is None:
        raise ValueError("OpenAI API key not set. Call set_openai_api_key() first.")
    return openai

# --- Language Detection and Fences (helpers for AI prompt generation) ---
# Maps detected language to a code fence identifier for Markdown
_FENCE_BY_LANG = {
    'Dart/Flutter':     'dart',
    'TypeScript/Angular':'ts',
    'JavaScript/React': 'js',
    'TypeScript/React': 'ts',
    'Python':           'python',
    'Java':             'java',
    '.NET C#':          'csharp',
    'Go':               'go',
    'HTML':             'html',
    'CSS':              'css',
    'SCSS/Sass':        'scss',
    'Less':             'less',
    'Shell':            'sh',
    'JSON':             'json', # Added JSON
    'YAML':             'yaml', # Added YAML
    'XML':              'xml',  # Added XML
    'Markdown':         'md',   # Added Markdown
    'Text':             'text', # Added Text
    'general programming': ''    # Default if language is unknown, results in generic code block
}

def _detect_language(file_path: str) -> str:
    """
    Detects the programming language based on the file extension.
    This helps the AI provide more relevant context and suggestions.
    """
    ext = Path(file_path).suffix.lower()
    return {
        '.dart':       'Dart/Flutter',
        '.ts':         'TypeScript/Angular',
        '.js':         'JavaScript/React',
        '.jsx':        'JavaScript/React',
        '.tsx':        'TypeScript/React',
        '.py':         'Python',
        '.java':       'Java',
        '.cs':         '.NET C#',
        '.go':         'Go',
        '.html':       'HTML',
        '.htm':        'HTML',
        '.css':        'CSS',
        '.scss':       'SCSS/Sass',
        '.less':       'Less',
        '.sh':         'Shell',
        '.json':       'JSON',
        '.yaml':       'YAML',
        '.yml':        'YAML',
        '.xml':        'XML',
        '.md':         'Markdown',
        '.txt':        'Text',
    }.get(ext, 'general programming')


def ai_suggest_fix(code: str, patch_ctx: str, file_path: str, line_no: int, issue_message: str) -> str:
    """
    Uses OpenAI's GPT model to generate a detailed fix suggestion for a given code issue.

    Args:
        code (str): The linter's specific issue code (e.g., 'ESLint:no-unused-vars').
        patch_ctx (str): A diff snippet representing the code context around the issue.
        file_path (str): The path to the file containing the issue.
        line_no (int): The line number where the issue was reported.
        issue_message (str): The detailed message from the linter.

    Returns:
        str: A Markdown string containing AI's analysis, suggested fix (with code block), and rationale.
    """
    client = _get_openai_client()
    lang = _detect_language(file_path)
    fence = _FENCE_BY_LANG.get(lang, '') # Get the appropriate markdown fence for the language

    prompt = dedent(f"""
    You are a highly experienced {lang} code reviewer and software architect.
    Your task is to analyze the provided code context and a reported issue, then provide a detailed, actionable suggestion for improvement.

    Reported issue:
    - **File:** `{file_path}`
    - **Line:** `{line_no}`
    - **Issue Code:** `{code}`
    - **Message:** `{issue_message}`

    Here's the relevant code context (a diff snippet around the reported line):
    ```diff
    {patch_ctx}
    ```

    Please provide your analysis and suggestions in exactly three labeled sections.
    **Crucially, ensure the 'Suggested Fix' section includes a code block formatted with triple backticks and the correct language identifier immediately after the opening backticks (e.g., ```{fence}\\n...code...\\n```).**
    If showing original and corrected code, keep it within a single code block.

    **Analysis:**
    Provide a concise explanation of the root cause of the issue, and elaborate on any other potential issues you identify within the provided code context (e.g., performance, security, maintainability, naming conventions, adherence to {lang} best practices).

    **Suggested Fix:**
    Provide a copy-friendly code snippet for the corrected code. This snippet should include the lines that need to be changed, and if applicable, a few lines of surrounding context for clarity.
    **Remember to use the correct language fence like `{fence}` immediately after the opening triple backticks, e.g., ```{fence}**.
    Example format:
    ```{fence}
    // Original:
    // old code line 1
    // old code line 2
    // Corrected:
    new code line 1
    new code line 2
    ```

    **Rationale:**
    Briefly explain *why* your suggested fix is better, covering aspects like readability, performance, adherence to best practices, or security improvements.
    """)

    # System prompt provides context for the AI's persona
    system_prompt = (
        f"You are a senior {lang} software architect and code reviewer. "
        "You provide in-depth, actionable feedback, "
        "catching syntax, style, performance, security, naming, and {lang} best practices. "
        "Always focus on clarity, maintainability, and robust solutions."
    )
    try:
        resp = client.chat.completions.create(
            model='gpt-4o-mini', # Using gpt-4o-mini for cost-effectiveness and speed
            messages=[{'role':'system','content':system_prompt},
                      {'role':'user','content':prompt}],
            temperature=0.1, # Low temperature for more deterministic and accurate fixes
            max_tokens=700   # Sufficient tokens for detailed responses
        )
        return resp.choices[0].message.content.strip()
    except openai.APIError as e:
        print(f"❌ OpenAI API Error during fix suggestion: {e}")
        return "AI fix suggestion failed due to an API error."
    except Exception as e:
        print(f"❌ An unexpected error occurred during fix suggestion: {e}")
        return "AI fix suggestion failed due to an unexpected error."


def get_developer_rating(dev_name: str, title: str, issues_count: int, files_affected: int,
                         commits: int, additions: int, deletions: int) -> str:
    """
    Uses OpenAI's GPT model to generate a developer performance rating based on PR metrics.

    Args:
        dev_name (str): The GitHub username of the developer.
        title (str): The title of the Pull Request.
        issues_count (int): Total number of issues detected.
        files_affected (int): Number of unique files with issues.
        commits (int): Number of commits in the PR.
        additions (int): Total lines added.
        deletions (int): Total lines deleted.

    Returns:
        str: A Markdown string containing the developer rating, stars, and summary.
    """
    client = _get_openai_client()
    rating_prompt = dedent(f"""
    You are a senior software reviewer, known for your fair and motivational feedback.

    Evaluate the pull request submitted by @{dev_name} using the following data:

    - PR Title: "{title}"
    - Total Issues Detected: {issues_count}
    - Files Affected: {files_affected}
    - Total Commits: {commits}
    - Lines Added: {additions}
    - Lines Deleted: {deletions}

    Base your evaluation on code cleanliness, lint adherence, readability, and developer discipline. Consider if the code followed best practices, had minimal issues, and was neatly structured.

    Respond with:
    - A creative title (e.g., "Code Ninja", "Syntax Sorcerer", etc.)
    - A rating out of 5 stars (⭐️) — use only full stars
    - A one-liner review summary using professional yet light-hearted emojis.

    Be motivational but fair. If there are many issues, reduce the score accordingly. If it's a clean PR, reward it well. Aim for constructive and encouraging language.
    """)
    try:
        rating_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional, playful yet insightful code reviewer."},
                {"role": "user",   "content": rating_prompt}
            ],
            temperature=0.0, # Low temperature for consistent ratings
            max_tokens=120
        )
        return rating_resp.choices[0].message.content.strip()
    except openai.APIError as e:
        print(f"❌ OpenAI API Error during rating generation: {e}")
        return "AI rating failed due to an API error."
    except Exception as e:
        print(f"❌ An unexpected error occurred during rating generation: {e}")
        return "AI rating failed due to an unexpected error."


def clean_rating_title(raw_title_line: str) -> str:
    """
    Cleans the AI-generated rating title by removing markdown hashes and 'Title: ' prefix.
    This helps in proper Markdown rendering of the rating.
    """
    return re.sub(r'^\s*#+\s*Title:\s*', '', raw_title_line, flags=re.IGNORECASE).strip()


def get_troll_joke() -> str:
    """
    Uses OpenAI's GPT model to generate a short, funny office prank/troll joke.
    """
    client = _get_openai_client()
    troll_prompt = dedent("""
    Invent a completely new, funny, over-the-top **office prank or office troll** that could happen at a software company.
    Requirements:
    - Make it DIFFERENT each time you write it
    - It can involve Developers, QA, Management, or any other team
    - Keep it SHORT (max 5 lines)
    - Use plenty of fun emojis
    - Do NOT always repeat the same joke style — be creative!
    Generate ONE such funny prank now:
    """)
    try:
        troll_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a playful office troll, known for harmless but hilarious pranks."},
                {"role": "user",   "content": troll_prompt}
            ],
            temperature=0.9, # Higher temperature for more creative pranks
            max_tokens=100
        )
        return troll_resp.choices[0].message.content.strip()
    except openai.APIError as e:
        print(f"❌ OpenAI API Error during troll joke generation: {e}")
        return "AI joke failed due to an API error."
    except Exception as e:
        print(f"❌ An unexpected error occurred during troll joke generation: {e}")
        return "AI joke failed due to an unexpected error."


def get_dev_humor_joke() -> str:
    """
    Uses OpenAI's GPT model to generate a short, fun programming joke.
    """
    client = _get_openai_client()
    try:
        joke_resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                { "role": "system", "content": "You are a witty developer assistant. Always provide a short, fun programming joke." },
                { "role": "user",   "content": "Tell me a short, fun programming joke about clean code reviews or developers." }
            ],
            temperature=0.8,
            max_tokens=60
        )
        return joke_resp.choices[0].message.content.strip()
    except openai.APIError as e:
        print(f"❌ OpenAI API Error during dev joke generation: {e}")
        return "AI joke failed due to an API error."
    except Exception as e:
        print(f"❌ An unexpected error occurred during dev joke generation: {e}")
        return "AI joke failed due to an unexpected error."