import json
from config import EVENT_PATH, repo

with open(EVENT_PATH) as f:
    event = json.load(f)

pr = repo.get_pull(event["pull_request"]["number"])
pr_number = event["pull_request"]["number"]
full_sha = event["pull_request"]["head"]["sha"]
dev_name = event["pull_request"]["user"]["login"]
title = event["pull_request"]["title"]
body = event["pull_request"]["body"] or "No description provided."
url = event["pull_request"]["html_url"]
source_branch = event["pull_request"]["head"]["ref"]
target_branch = event["pull_request"]["base"]["ref"]
created_at = event["pull_request"]["created_at"]
commits = event["pull_request"]["commits"]
additions = event["pull_request"]["additions"]
deletions = event["pull_request"]["deletions"]
changed_files_count = event["pull_request"]["changed_files"]

# for changed files:
changed_files = [
    f.filename for f in pr.get_files() if f.patch and not f.filename.lower().startswith('.github/')
]

default_branch = repo.default_branch
img_url = (
    f"https://raw.githubusercontent.com/"
    f"{repo.full_name}/{default_branch}/.github/assets/bailogo.png"
)