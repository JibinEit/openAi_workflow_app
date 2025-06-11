import os
from github import Github

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("GITHUB_REPOSITORY")
EVENT_PATH = os.getenv("GITHUB_EVENT_PATH")

if not OPENAI_API_KEY or not GITHUB_TOKEN:
    print("⛔️ Missing OpenAI or GitHub token.")
    exit(1)

import openai
openai.api_key = OPENAI_API_KEY
gh = Github(GITHUB_TOKEN)
repo = gh.get_repo(REPO_NAME)