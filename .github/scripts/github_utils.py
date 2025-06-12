import os
import json
from github import Github, PullRequest, Repository # Import specific classes for type hinting
from textwrap import dedent

def initialize_github_client(token: str) -> Github:
    """
    Initializes and returns a GitHub client instance using the provided token.
    """
    return Github(token)

def load_pr_data(event_path: str, repo_name: str, gh_client: Github) -> dict:
    """
    Loads and extracts essential Pull Request data from the GitHub event payload.

    Args:
        event_path (str): The path to the GitHub event JSON file (GITHUB_EVENT_PATH).
        repo_name (str): The full name of the repository (GITHUB_REPOSITORY).
        gh_client (Github): An initialized PyGithub client instance.

    Returns:
        dict: A dictionary containing key PR details and PyGithub objects.
    """
    with open(event_path) as f:
        event = json.load(f)

    # Extract core PR and repository objects using PyGithub
    pr_number = event["pull_request"]["number"]
    full_sha  = event["pull_request"]["head"]["sha"]
    repo      = gh_client.get_repo(repo_name)
    pr        = repo.get_pull(pr_number)

    return {
        'pr': pr,  # PyGithub PullRequest object
        'repo': repo, # PyGithub Repository object
        'pr_number': pr_number,
        'full_sha': full_sha,
        'dev_name': event["pull_request"]["user"]["login"],
        'title': event["pull_request"]["title"],
        'body': event["pull_request"]["body"] or "No description provided.", # Handle empty body
        'url': event["pull_request"]["html_url"],
        'source_branch': event["pull_request"]["head"]["ref"],
        'target_branch': event["pull_request"]["base"]["ref"], # This is the base branch the PR is targeting
        'created_at_utc_str': event["pull_request"]["created_at"], # UTC timestamp string
        'commits': event["pull_request"]["commits"],
        'additions': event["pull_request"]["additions"],
        'deletions': event["pull_request"]["deletions"]
    }

def generate_image_url(repo_name: str, default_branch: str, image_path_in_repo: str) -> str:
    """
    Generates the raw GitHubusercontent URL for an image located in the repository.

    Args:
        repo_name (str): The full name of the repository (e.g., 'owner/repo').
        default_branch (str): The default branch of the repository (e.g., 'main' or 'master').
        image_path_in_repo (str): The path to the image *within* the repository (e.g., '.github/assets/logo.png').

    Returns:
        str: The direct URL to the image file on raw.githubusercontent.com.
    """
    # Clean the path to ensure it doesn't start with './' or '../' relative indicators
    clean_path = image_path_in_repo.lstrip('./')
    return (
        f"https://raw.githubusercontent.com/"
        f"{repo_name}/{default_branch}/{clean_path}"
    )

def get_changed_files_in_pr(pr_object: PullRequest.PullRequest) -> list:
    """
    Returns a list of changed file paths in the PR, filtering out files
    within the '.github/' directory as they are usually not relevant for code review.

    Args:
        pr_object (PullRequest.PullRequest): The PyGithub PullRequest object.

    Returns:
        list: A list of string file paths (e.g., ['src/app.js', 'docs/README.md']).
    """
    # Only include files that have a patch (i.e., actual code changes) and are not in .github/
    return [f.filename for f in pr_object.get_files()
            if f.patch and not f.filename.lower().startswith('.github/')]

def get_pr_file_patches(pr_object: PullRequest.PullRequest) -> dict:
    """
    Retrieves the patch content for all files changed in a Pull Request.

    Args:
        pr_object (PullRequest.PullRequest): The PyGithub PullRequest object.

    Returns:
        dict: A dictionary where keys are file paths and values are their Git patch strings.
              Only includes files that actually have patch content.
    """
    # Create a dictionary for quick lookup of patch content by filename
    return {f.filename: f.patch for f in pr_object.get_files() if f.patch}

def post_comment(pr_object: PullRequest.PullRequest, comment_body: str):
    """
    Posts a Markdown comment to the given Pull Request.

    Args:
        pr_object (PullRequest.PullRequest): The PyGithub PullRequest object.
        comment_body (str): The Markdown content of the comment to post.
    """
    try:
        pr_object.create_issue_comment(comment_body)
        print(f"✅ Successfully posted AI review for PR #{pr_object.number}.")
    except Exception as e:
        print(f"❌ Error posting comment to PR #{pr_object.number}: {e}")
        # In case of an error posting to GitHub, print the comment to stdout for debugging
        print("\n--- Failed to Post Comment. Here's the content (for debugging): ---")
        print(comment_body)
        print("------------------------------------------------------------------")

def set_commit_status(repo_object: Repository.Repository, sha: str, state: str, description: str, context: str):
    """
    Sets the commit status for a given SHA in the repository.

    Args:
        repo_object (Repository.Repository): The PyGithub Repository object.
        sha (str): The full SHA of the commit to set the status for.
        state (str): The state of the status ('success', 'failure', 'pending', 'error').
        description (str): A short description of the status.
        context (str): The name of the status check (e.g., 'CI / Build', 'Code Review').
    """
    try:
        repo_object.get_commit(sha).create_status(
            context=context,
            state=state,
            description=description
        )
        print(f"✅ Set commit status for SHA {sha} to '{state}'.")
    except Exception as e:
        print(f"❌ Error setting commit status for SHA {sha}: {e}")