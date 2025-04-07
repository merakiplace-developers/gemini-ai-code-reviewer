import json
import os
from typing import List, Dict, Any
from github import Github
import requests
import fnmatch
from unidiff import Hunk
from google.oauth2 import service_account
import vertexai
from vertexai.generative_models import GenerativeModel

# === Vertex AI 초기화 ===
credentials_dict = json.loads(os.environ["VERTEXAI_CREDENTIALS_JSON"])
credentials = service_account.Credentials.from_service_account_info(credentials_dict)

vertexai.init(
    project=os.environ["VERTEXAI_PROJECT_ID"],
    location="us-central1",
    credentials=credentials
)

# === GitHub Client 초기화 ===
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
gh = Github(GITHUB_TOKEN)

class PRDetails:
    def __init__(self, owner: str, repo: str, pull_number: int, title: str, description: str):
        self.owner = owner
        self.repo = repo
        self.pull_number = pull_number
        self.title = title
        self.description = description

def get_pr_details() -> PRDetails:
    with open(os.environ["GITHUB_EVENT_PATH"], "r") as f:
        event_data = json.load(f)

    if "issue" in event_data and "pull_request" in event_data["issue"]:
        pull_number = event_data["issue"]["number"]
        repo_full_name = event_data["repository"]["full_name"]
    else:
        pull_number = event_data["number"]
        repo_full_name = event_data["repository"]["full_name"]

    owner, repo = repo_full_name.split("/")
    repo = gh.get_repo(repo_full_name)
    pr = repo.get_pull(pull_number)

    return PRDetails(owner, repo.name, pull_number, pr.title, pr.body)

def get_diff(owner: str, repo: str, pull_number: int) -> str:
    repo_name = f"{owner}/{repo}"
    api_url = f"https://api.github.com/repos/{repo_name}/pulls/{pull_number}"
    headers = {
        'Authorization': f'Bearer {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3.diff'
    }
    response = requests.get(f"{api_url}.diff", headers=headers)
    return response.text if response.status_code == 200 else ""

def create_prompt(file_path: str, hunk: Hunk, pr_details: PRDetails) -> str:
    return f"""Your task is reviewing pull requests. Instructions:
    - Provide the response in following JSON format:  {{"reviews": [{{"lineNumber":  <line_number>, "reviewComment": "<review comment>"}}]}}
    - Provide comments and suggestions ONLY if there is something to improve, otherwise "reviews" should be an empty array.
    - Use GitHub Markdown in comments
    - Focus on bugs, security issues, and performance problems
    - IMPORTANT: NEVER suggest adding comments to the code

Review the following code diff in the file "{file_path}" and take the pull request title and description into account when writing the response.

Pull request title: {pr_details.title}
Pull request description:
---
{pr_details.description or 'No description provided'}
---
Git diff to review:
```diff
{hunk.content}
```"""

def get_ai_response(prompt: str) -> List[Dict[str, str]]:
    model = GenerativeModel("gemini-1.5-pro-preview")
    response = model.generate_content(prompt, generation_config={
        "max_output_tokens": 8192,
        "temperature": 0.8,
        "top_p": 0.95
    })
    try:
        text = response.text.strip()
        if text.startswith('```json'):
            text = text[7:]
        if text.endswith('```'):
            text = text[:-3]
        return json.loads(text).get("reviews", [])
    except Exception as e:
        print("AI response parse error:", e)
        return []

def create_comment(file_path: str, hunk: Hunk, ai_responses: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    comments = []
    for res in ai_responses:
        try:
            line_number = int(res["lineNumber"])
            if 1 <= line_number <= hunk.source_length:
                comments.append({
                    "body": res["reviewComment"],
                    "path": file_path,
                    "position": line_number
                })
        except Exception as e:
            print("Comment creation error:", e)
    return comments

def create_review_comment(owner: str, repo: str, pull_number: int, comments: List[Dict[str, Any]]):
    repo = gh.get_repo(f"{owner}/{repo}")
    pr = repo.get_pull(pull_number)
    pr.create_review(body="Vertex AI Code Review", comments=comments, event="COMMENT")

def parse_diff(diff_str: str) -> List[Dict[str, Any]]:
    files, current_file, current_hunk = [], None, None
    for line in diff_str.splitlines():
        if line.startswith('diff --git'):
            if current_file:
                files.append(current_file)
            current_file = {'path': '', 'hunks': []}
        elif line.startswith('--- a/') or line.startswith('+++ b/'):
            if current_file:
                current_file['path'] = line[6:]
        elif line.startswith('@@'):
            if current_file:
                current_hunk = {'header': line, 'lines': []}
                current_file['hunks'].append(current_hunk)
        elif current_hunk:
            current_hunk['lines'].append(line)
    if current_file:
        files.append(current_file)
    return files

def analyze_code(parsed_diff: List[Dict[str, Any]], pr_details: PRDetails) -> List[Dict[str, Any]]:
    comments = []
    for file_data in parsed_diff:
        file_path = file_data.get('path', '')
        hunks = file_data.get('hunks', [])
        for hunk_data in hunks:
            hunk = Hunk()
            hunk.source_start = 1
            hunk.source_length = len(hunk_data.get('lines', []))
            hunk.target_start = 1
            hunk.target_length = len(hunk_data.get('lines', []))
            hunk.content = '\n'.join(hunk_data.get('lines', []))
            prompt = create_prompt(file_path, hunk, pr_details)
            ai_responses = get_ai_response(prompt)
            comments.extend(create_comment(file_path, hunk, ai_responses))
    return comments

def main():
    pr_details = get_pr_details()
    event_name = os.environ.get("GITHUB_EVENT_NAME")
    if event_name != "issue_comment":
        print("Unsupported event:", event_name)
        return
    diff = get_diff(pr_details.owner, pr_details.repo, pr_details.pull_number)
    if not diff:
        print("No diff found")
        return
    parsed_diff = parse_diff(diff)
    exclude_patterns = [p.strip() for p in os.environ.get("INPUT_EXCLUDE", "").split(",") if p.strip()]
    filtered_diff = [f for f in parsed_diff if not any(fnmatch.fnmatch(f.get('path', ''), p) for p in exclude_patterns)]
    comments = analyze_code(filtered_diff, pr_details)
    if comments:
        create_review_comment(pr_details.owner, pr_details.repo, pr_details.pull_number, comments)

if __name__ == "__main__":
    main()