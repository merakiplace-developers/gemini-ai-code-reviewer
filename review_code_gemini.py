import fnmatch
import json
import os
import re
import requests
from google import genai
from google.genai.types import GenerateContentConfig, ThinkingConfig
from typing import List, Dict, Any, Optional, Tuple
from unidiff import Hunk

# === Vertex AI init ===
# Get credentials from environment variable and save to temp file
credentials_json_str = os.environ["VERTEXAI_CREDENTIALS_JSON"]
creds_file_path = "/tmp/google-credentials.json"

# Save credentials to a temp file
with open(creds_file_path, "w") as f:
    f.write(credentials_json_str)

# Set environment variable
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_file_path

PROJECT_ID = os.environ["VERTEXAI_PROJECT_ID"]
LOCATION = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")

# Initialize client with Google credentials
client = genai.Client(project=PROJECT_ID, location=LOCATION)

# === GitHub API setup ===
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_API_URL = "https://api.github.com"
GITHUB_HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

LANGUAGE = os.environ.get("LANGUAGE", "English")


class PRDetails:
    def __init__(self, owner: str, repo: str, pull_number: int, title: str, description: str):
        self.owner = owner
        self.repo = repo
        self.pull_number = pull_number
        self.title = title
        self.description = description


def get_pr_details() -> PRDetails:
    """
    Extract PR details from GitHub event data
    """
    with open(os.environ["GITHUB_EVENT_PATH"], "r") as f:
        event_data = json.load(f)

    if "issue" in event_data and "pull_request" in event_data["issue"]:
        pull_number = event_data["issue"]["number"]
        repo_full_name = event_data["repository"]["full_name"]
    else:
        pull_number = event_data["number"]
        repo_full_name = event_data["repository"]["full_name"]

    owner, repo = repo_full_name.split("/")

    # Get PR details
    api_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pull_number}"
    response = requests.get(api_url, headers=GITHUB_HEADERS)

    if response.status_code != 200:
        raise Exception(f"Failed to get PR details: {response.status_code}, {response.text}")

    pr_data = response.json()

    return PRDetails(owner, repo, pull_number, pr_data["title"], pr_data["body"] or "")


def get_diff(owner: str, repo: str, pull_number: int) -> str:
    """
    Get the diff for a specific PR
    """
    repo_name = f"{owner}/{repo}"
    api_url = f"{GITHUB_API_URL}/repos/{repo_name}/pulls/{pull_number}"
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3.diff'
    }
    response = requests.get(f"{api_url}.diff", headers=headers)
    return response.text if response.status_code == 200 else ""


def check_summary_comment_exists(owner: str, repo: str, pull_number: int) -> bool:
    """
    Check if a PR summary comment already exists in the PR review comments or issue comments
    """
    # Get review comments
    review_comments_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pull_number}/comments"
    review_comments_response = requests.get(review_comments_url, headers=GITHUB_HEADERS)

    if review_comments_response.status_code == 200:
        review_comments = review_comments_response.json()
        for comment in review_comments:
            if comment.get("body", "").startswith("### PR Summary"):
                return True

    # Get issue comments
    issue_comments_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues/{pull_number}/comments"
    issue_comments_response = requests.get(issue_comments_url, headers=GITHUB_HEADERS)

    if issue_comments_response.status_code == 200:
        issue_comments = issue_comments_response.json()
        for comment in issue_comments:
            if comment.get("body", "").startswith("### PR Summary"):
                return True

    return False


def is_follow_up_request(event_data: Dict[str, Any]) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Check if the current event is a follow-up request to an AI review comment.
    Returns a tuple of (is_follow_up, comment_id, follow_up_question)
    """
    if "comment" not in event_data:
        return False, None, None

    # Extract the comment body
    comment_body = event_data.get("comment", {}).get("body", "")

    # Check if this is replying to another comment
    in_reply_to_id = event_data.get("comment", {}).get("in_reply_to_id")

    if not in_reply_to_id:
        return False, None, None

    # Get the original comment
    repo_full_name = event_data["repository"]["full_name"]
    comment_url = f"{GITHUB_API_URL}/repos/{repo_full_name}/pulls/comments/{in_reply_to_id}"

    try:
        response = requests.get(comment_url, headers=GITHUB_HEADERS)
        if response.status_code == 200:
            original_comment = response.json()

            # Check if the original comment was made by the bot
            if "Vertex AI Code Review" in original_comment.get("body", ""):
                return True, in_reply_to_id, comment_body
    except Exception as e:
        print(f"Error checking if comment is follow-up: {e}")

    return False, None, None


def get_conversation_history(owner: str, repo: str, comment_id: int) -> List[Dict[str, str]]:
    """
    Retrieve the conversation history for a specific comment thread
    """
    conversation = []

    try:
        # Get the original comment
        comment_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/comments/{comment_id}"
        response = requests.get(comment_url, headers=GITHUB_HEADERS)

        if response.status_code == 200:
            original_comment = response.json()
            conversation.append({
                "role": "assistant",
                "content": original_comment.get("body", "")
            })

            # Get replies to this comment - GitHub API doesn't directly support this
            # We need to get all comments in the PR and filter ones that mention this comment
            pull_number = get_pull_number_from_comment(original_comment)
            if pull_number:
                all_comments_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pull_number}/comments"
                all_comments_response = requests.get(all_comments_url, headers=GITHUB_HEADERS)

                if all_comments_response.status_code == 200:
                    all_comments = all_comments_response.json()

                    # Filter replies (based on body content or creation time)
                    for comment in all_comments:
                        # Skip the original comment
                        if comment.get("id") == comment_id:
                            continue

                        # Check if this is a reply (contains reference to original comment or created later)
                        body = comment.get("body", "")
                        if f"#{comment_id}" in body or f"comment {comment_id}" in body:
                            user_type = "assistant" if "github-actions[bot]" in comment.get("user", {}).get("login",
                                                                                                            "") else "user"
                            conversation.append({
                                "role": user_type,
                                "content": body
                            })
    except Exception as e:
        print(f"Error getting conversation history: {e}")

    return conversation


def get_pull_number_from_comment(comment: Dict[str, Any]) -> Optional[int]:
    """
    Extract pull request number from a comment
    """
    try:
        # Pull request URL format: "https://api.github.com/repos/owner/repo/pulls/123"
        if "pull_request_url" in comment:
            pr_url = comment["pull_request_url"]
            return int(pr_url.split("/")[-1])
    except Exception:
        pass
    return None


def create_prompt(file_path: str, hunk: Hunk, pr_details: PRDetails) -> str:
    """
    Create prompt for AI to review code changes, with focus on design principles
    """
    language_instruction = {
        "English": "✍️ Answer must be in English.",
        "Korean": "✍️ 답변은 반드시 한국어로 해주세요.",
        "Japanese": "✍️ 回答は必ず日本語でお願いします。",
        "Chinese": "✍️ 回答必须使用中文。",
        "French": "✍️ Veuillez répondre en français.",
        "German": "✍️ Bitte antworten Sie auf Deutsch.",
        "Spanish": "✍️ Por favor responde en español.",
        "Portuguese": "✍️ Por favor, responda em português.",
        "Russian": "✍️ Пожалуйста, отвечайте на русском.",
        "Italian": "✍️ Si prega di rispondere in italiano.",
        "Dutch": "✍️ Antwoord alstublieft in het Nederlands.",
        "Arabic": "✍️ الرجاء الرد باللغة العربية.",
        "Hindi": "✍️ कृपया हिंदी में उत्तर दें।",
        "Bengali": "✍️ অনুগ্রহ করে বাংলায় উত্তর দিন।",
        "Turkish": "✍️ Lütfen Türkçe cevap verin.",
        "Vietnamese": "✍️ Vui lòng trả lời bằng tiếng Việt.",
        "Thai": "✍️ กรุณาตอบเป็นภาษาไทย",
        "Polish": "✍️ Proszę odpowiedzieć po polsku.",
        "Ukrainian": "✍️ Будь ласка, відповідайте українською.",
        "Czech": "✍️ Prosím odpovězte česky.",
        "Swedish": "✍️ Svara gärna på svenska.",
        "Finnish": "✍️ Vastaa suomeksi.",
        "Norwegian": "✍️ Vennligst svar på norsk.",
        "Danish": "✍️ Svar venligst på dansk.",
        "Romanian": "✍️ Vă rugăm să răspundeți în română.",
        "Hungarian": "✍️ Kérjük, válaszoljon magyarul.",
        "Hebrew": "✍️ אנא השב בעברית.",
        "Greek": "✍️ Παρακαλώ απαντήστε στα ελληνικά.",
        "Malay": "✍️ Sila jawab dalam Bahasa Melayu.",
        "Indonesian": "✍️ Silakan jawab dalam Bahasa Indonesia.",
        "Filipino": "✍️ Mangyaring sumagot sa wikang Filipino.",
        "Persian": "✍️ لطفاً به زبان فارسی پاسخ دهید.",
        "Swahili": "✍️ Tafadhali jibu kwa Kiswahili.",
        "Slovak": "✍️ Prosím, odpovedzte po slovensky.",
        "Serbian": "✍️ Molimo odgovorite na srpskom.",
        "Croatian": "✍️ Molimo odgovorite na hrvatskom.",
        "Bulgarian": "✍️ Моля, отговорете на български.",
        "Slovenian": "✍️ Prosimo, odgovorite v slovenščini.",
        "Lithuanian": "✍️ Prašome atsakyti lietuviškai.",
        "Latvian": "✍️ Lūdzu, atbildiet latviski.",
        "Estonian": "✍️ Palun vastake eesti keeles."
    }

    instruction = language_instruction.get(LANGUAGE, f"✍️ Please answer in {LANGUAGE}.")

    # Extract some file context to help with design principle evaluation
    file_context = ""
    if file_path:
        # Extract file extension to identify language
        file_ext = file_path.split('.')[-1].lower() if '.' in file_path else ''
        file_context = f"File type: {file_ext}\n"

        # Add information about the file's role in the system if identifiable from its path
        if 'controller' in file_path.lower():
            file_context += "This appears to be a controller component.\n"
        elif 'model' in file_path.lower():
            file_context += "This appears to be a model component.\n"
        elif 'view' in file_path.lower():
            file_context += "This appears to be a view component.\n"
        elif 'service' in file_path.lower():
            file_context += "This appears to be a service component.\n"
        elif 'repository' in file_path.lower():
            file_context += "This appears to be a repository/data access component.\n"
        elif 'util' in file_path.lower() or 'helper' in file_path.lower():
            file_context += "This appears to be a utility/helper component.\n"
        elif 'test' in file_path.lower():
            file_context += "This appears to be a test file.\n"

    return f"""{instruction}

Your task is reviewing this code fragment as part of a pull request, with particular attention to both functionality and design principles (SOLID, etc.).

{file_context}
Please analyze the following code diff in the file "{file_path}" and consider the pull request context.

Pull request title: {pr_details.title}
Pull request description:
---
{pr_details.description or 'No description provided'}
---
Git diff to review:
```diff
{hunk.content}
```

When evaluating this code, consider:
1. Does it follow Single Responsibility Principle? Are classes/functions focused on a single task?
2. Does it follow Open/Closed Principle? Can it be extended without modification?
3. Are method signatures, parameters, and return types well-designed?
4. Are dependencies appropriately managed?
5. Is the code extensible and maintainable?"""


def create_followup_prompt(question: str, conversation_history: List[Dict[str, str]], file_path: str,
                           hunk_content: str = None, pr_details: PRDetails = None) -> str:
    """
    Create a prompt for follow-up responses to developer questions
    """
    language_instruction = {
        "English": "✍️ Answer must be in English.",
        "Korean": "✍️ 답변은 반드시 한국어로 해주세요.",
        # Other languages...
    }

    instruction = language_instruction.get(LANGUAGE, f"✍️ Please answer in {LANGUAGE}.")

    context = ""
    if hunk_content:
        context += f"""
The code being discussed is in file "{file_path}":
```diff
{hunk_content}
```
"""

    if pr_details:
        context += f"""
Pull request title: {pr_details.title}
Pull request description:
---
{pr_details.description or 'No description provided'}
---
"""

    # Add design context based on file path
    design_context = ""
    if file_path:
        if 'controller' in file_path.lower():
            design_context += "This file appears to be a controller component, which typically handles incoming requests and delegates business logic.\n"
        elif 'model' in file_path.lower():
            design_context += "This file appears to be a model component, which typically represents data structures and business entities.\n"
        elif 'service' in file_path.lower():
            design_context += "This file appears to be a service component, which typically encapsulates business logic and operations.\n"
        elif 'repository' in file_path.lower():
            design_context += "This file appears to be a repository/data access component, which typically handles data access operations.\n"

    if design_context:
        context += f"\nDesign context:\n{design_context}"

    conversation = "\n\n".join([
        f"{'AI' if msg['role'] == 'assistant' else 'Developer'}: {msg['content']}"
        for msg in conversation_history
    ])

    return f"""{instruction}

You are an AI code reviewer continuing a conversation with a developer about code changes in a pull request. Focus on both functional correctness and software design principles (SOLID, DRY, YAGNI, etc.).

{context}

Below is the conversation history:
---
{conversation}
---

New question from developer:
{question}

Please provide a helpful, direct response to the developer's question. Maintain your role as a code reviewer, but be conversational and address their specific question or concern. When discussing design principles, be clear about which principle you're referencing and why it matters in this context.
"""


def get_ai_response(prompt: str, include_summary: bool = True) -> Dict[str, Any]:
    """
    Get code review response from AI model
    """
    config = GenerateContentConfig(
        temperature=0.8,
        top_p=0.95,
        system_instruction="""
    You are an experienced Senior Software Engineer reviewing code for quality, correctness, and adherence to software design principles.

    # Response structure
    First, provide a brief summary of the PR's purpose based on the title, description, and code changes.
    Then, provide detailed code review comments as specified below.

    # Objectives
    - Identify bugs, security vulnerabilities, and performance issues
    - Suggest clear and specific improvements with rationale
    - Evaluate code maintainability and readability
    - Assess adherence to software design principles

    # Focus areas
    ## Functional aspects
    - Logic errors and edge cases
    - Security risks (e.g., injection vulnerabilities, authentication issues)
    - Performance bottlenecks (e.g., inefficient algorithms, resource leaks)
    - Error handling and resilience

    ## Design principles
    - Single Responsibility Principle (SRP): Does each class/function have only one reason to change?
    - Open/Closed Principle (OCP): Is the code open for extension but closed for modification?
    - Liskov Substitution Principle (LSP): Can derived classes be substituted for their base classes?
    - Interface Segregation Principle (ISP): Are interfaces properly segregated?
    - Dependency Inversion Principle (DIP): Does the code depend on abstractions rather than concretions?

    ## Architecture & Structure
    - Class and function interface design (method signatures, parameter choices, return types)
    - Appropriate dependency relationships between components
    - Extensibility and maintainability of the overall design
    - Proper separation of concerns and layer boundaries
    - Consistency with existing architecture patterns

    # Response guidelines
    - Be direct, constructive, and professional
    - Support criticisms with clear reasoning
    - Suggest specific solutions when identifying problems
    - Use GitHub-flavored Markdown for formatting
    - Be concise but thorough
    - For design issues, explain which design principle is affected and why it matters

    # Response format
    - Provide the response in following JSON format: 
      {
        "summary": "Brief summary of the PR's purpose and changes",
        "reviews": [
          {"lineNumber": <line_number>, "reviewComment": "<review comment>"}
        ]
      }
    - Provide comments ONLY if there is something to improve, otherwise "reviews" should be an empty array
    - When commenting on design principles, clearly indicate which principle (e.g., "[SRP]", "[OCP]") 
      is affected at the beginning of your comment
    - Never suggest adding comments to the code unless they significantly improve understanding
    - Do not focus on stylistic choices unless they impact functionality or maintainability

    Thoroughly analyze the code before responding, and ensure all feedback is actionable and valuable.
    """,
        thinking_config=ThinkingConfig(thinking_budget=1024),
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-04-17",
            contents=prompt,
            config=config,
        )
        text = response.text.strip()
        if text.startswith('```json'):
            text = text[7:]
        if text.endswith('```'):
            text = text[:-3]

        try:
            result = json.loads(text)

            # If summary should not be included, remove it from the response
            if not include_summary and "summary" in result:
                del result["summary"]

            return result
        except json.JSONDecodeError:
            # If not valid JSON, it might be a followup response
            return {"response": text}

    except Exception as e:
        print(f"AI response parse error: {e}")
        return {"reviews": []}


def get_ai_followup_response(prompt: str) -> str:
    """
    Get a conversational followup response from the AI for discussions about code
    """
    config = GenerateContentConfig(
        temperature=0.8,
        top_p=0.95,
        system_instruction="""
    You are an experienced Senior Software Engineer engaging in a code review conversation.

    # Guidelines for follow-up responses:
    - Be helpful, direct, and conversational
    - Answer the developer's specific questions clearly
    - Provide additional context or explanations when needed
    - Suggest concrete solutions or alternatives if appropriate
    - Use GitHub-flavored Markdown for formatting and code snippets
    - Be respectful and collaborative in tone
    - If relevant, explain the reasoning behind your coding suggestions

    # When discussing software design principles:
    - Clearly explain how the code aligns or conflicts with design principles (SOLID, DRY, YAGNI, etc.)
    - When referencing design principles, briefly explain what they are and why they matter
    - For Single Responsibility Principle (SRP): Focus on whether classes/functions have only one reason to change
    - For Open/Closed Principle (OCP): Assess if code is open for extension but closed for modification
    - For Liskov Substitution Principle (LSP): Evaluate if derived classes can be substituted for base classes
    - For Interface Segregation Principle (ISP): Check if interfaces are appropriately segregated
    - For Dependency Inversion Principle (DIP): Analyze if code depends on abstractions rather than concretions
    - Comment on method signatures, parameter choices, and return types when relevant
    - Discuss dependency relationships and potential improvements
    - Address extensibility concerns with concrete examples

    Your responses should be actionable, educational and maintain a professional, collaborative tone.
    """,
        thinking_config=ThinkingConfig(thinking_budget=1024),
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-04-17",
            contents=prompt,
            config=config,
        )
        return response.text.strip()
    except Exception as e:
        print(f"AI followup response error: {e}")
        return "I apologize, but I encountered an error processing your question. Could you please rephrase or simplify your question?"


def create_comment(file_path: str, hunk: Hunk, ai_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Create comment objects from AI response for GitHub API
    """
    comments = []
    diff_lines = hunk.content.splitlines()
    added_line_indices = [i for i, line in enumerate(diff_lines) if line.startswith("+") and not line.startswith("+++")]

    # Add PR summary as the first comment if available
    if ai_response.get("summary"):
        comments.append({
            "body": f"### PR Summary\n{ai_response.get('summary')}",
            "path": file_path,
            "position": 1  # Position at the beginning of the diff
        })

    # Add individual line comments
    for res in ai_response.get("reviews", []):
        try:
            line_number = int(res["lineNumber"]) - 1
            if 0 <= line_number < len(added_line_indices):
                position = added_line_indices[line_number] + 1
                comments.append({
                    "body": res["reviewComment"],
                    "path": file_path,
                    "position": position
                })
        except Exception as e:
            print(f"Comment creation error: {e}")
    return comments


def create_review_comment(owner: str, repo: str, pull_number: int, comments: List[Dict[str, Any]]):
    """
    Create a review with multiple comments using direct GitHub API call
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pull_number}/reviews"
    payload = {
        "body": "Vertex AI Code Review",
        "event": "COMMENT",
        "comments": comments
    }

    response = requests.post(url, headers=GITHUB_HEADERS, json=payload)

    if response.status_code >= 400:
        print(f"Error creating review comment: {response.status_code}, {response.text}")
    else:
        print(f"Successfully created review with {len(comments)} comments")


def reply_to_comment(owner: str, repo: str, comment_id: int, reply_text: str):
    """
    Add a reply to an existing comment thread using direct GitHub API
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/comments/{comment_id}/replies"
    payload = {"body": reply_text}

    response = requests.post(url, headers=GITHUB_HEADERS, json=payload)

    if response.status_code >= 400:
        print(f"Error replying to comment: {response.status_code}, {response.text}")

        # Fallback: Find PR number from the comment
        comment_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/comments/{comment_id}"
        comment_response = requests.get(comment_url, headers=GITHUB_HEADERS)

        if comment_response.status_code == 200:
            comment_data = comment_response.json()
            pull_number = get_pull_number_from_comment(comment_data)

            if pull_number:
                # Create issue comment as fallback
                issue_comment_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues/{pull_number}/comments"
                issue_payload = {"body": f"**In reply to [comment](#{comment_id}):**\n\n{reply_text}"}

                issue_response = requests.post(issue_comment_url, headers=GITHUB_HEADERS, json=issue_payload)

                if issue_response.status_code == 201:
                    print(f"Created fallback reply as issue comment")
                else:
                    print(f"Failed to create fallback comment: {issue_response.status_code}, {issue_response.text}")
    else:
        print(f"Successfully replied to comment {comment_id}")


def parse_diff(diff_str: str) -> List[Dict[str, Any]]:
    """
    Parse the git diff into a structured format
    """
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


def get_file_and_hunk_for_comment(owner: str, repo: str, pull_number: int, comment_id: int) -> Tuple[
    Optional[str], Optional[str]]:
    """
    Get the file path and hunk content related to a specific comment
    """
    try:
        # Get the review comment
        comment_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/comments/{comment_id}"
        comment_response = requests.get(comment_url, headers=GITHUB_HEADERS)

        if comment_response.status_code == 200:
            comment_data = comment_response.json()
            file_path = comment_data.get("path")

            if file_path:
                # Get the diff for the file
                diff = get_diff(owner, repo, pull_number)
                parsed_diff = parse_diff(diff)

                for file_data in parsed_diff:
                    if file_data.get('path') == file_path:
                        # Return the file path and the content of all hunks combined
                        hunk_content = '\n'.join([
                            '\n'.join(hunk.get('lines', []))
                            for hunk in file_data.get('hunks', [])
                        ])
                        return file_path, hunk_content

                # If we found the file but not the exact hunk, return the file path only
                return file_path, None
    except Exception as e:
        print(f"Error finding file and hunk for comment: {e}")

    return None, None


def analyze_code(parsed_diff: List[Dict[str, Any]], pr_details: PRDetails) -> List[Dict[str, Any]]:
    """
    Analyze code changes and generate review comments
    """
    all_comments = []

    # Check if summary comment already exists in PR
    summary_exists = check_summary_comment_exists(pr_details.owner, pr_details.repo, pr_details.pull_number)

    for file_data in parsed_diff:
        file_path = file_data.get('path', '')
        hunks = file_data.get('hunks', [])

        for i, hunk_data in enumerate(hunks):
            hunk = Hunk()
            hunk.source_start = 1
            hunk.source_length = len(hunk_data.get('lines', []))
            hunk.target_start = 1
            hunk.target_length = len(hunk_data.get('lines', []))
            hunk.content = '\n'.join(hunk_data.get('lines', []))
            prompt = create_prompt(file_path, hunk, pr_details)

            # Only include summary in the first hunk of the first file if no summary exists yet
            include_summary = (i == 0 and file_data == parsed_diff[0] and not summary_exists)
            ai_response = get_ai_response(prompt, include_summary=include_summary)

            file_comments = create_comment(file_path, hunk, ai_response)
            all_comments.extend(file_comments)

    return all_comments


def handle_followup_question(event_data: Dict[str, Any], pr_details: PRDetails) -> None:
    """
    Handle a follow-up question from a developer to an AI review comment
    """
    is_followup, comment_id, question = is_follow_up_request(event_data)

    if not is_followup or not comment_id or not question:
        print("Not a valid follow-up question")
        return

    print(f"Handling follow-up question for comment {comment_id}: {question}")

    # Get conversation history
    conversation_history = get_conversation_history(pr_details.owner, pr_details.repo, comment_id)

    # Get the file path and hunk content related to the comment
    file_path, hunk_content = get_file_and_hunk_for_comment(
        pr_details.owner, pr_details.repo, pr_details.pull_number, comment_id
    )

    # Create prompt for follow-up
    prompt = create_followup_prompt(
        question,
        conversation_history,
        file_path,
        hunk_content,
        pr_details
    )

    # Get AI response
    ai_response = get_ai_followup_response(prompt)

    # Reply to the comment
    reply_to_comment(pr_details.owner, pr_details.repo, comment_id, ai_response)


def main():
    """
    Main function to handle PR review workflow
    """
    pr_details = get_pr_details()

    # Load the GitHub event data
    with open(os.environ["GITHUB_EVENT_PATH"], "r") as f:
        event_data = json.load(f)

    event_name = os.environ.get("GITHUB_EVENT_NAME")

    # Check if this is a follow-up question
    is_followup, comment_id, _ = is_follow_up_request(event_data)

    if event_name == "issue_comment" and is_followup:
        # Handle the follow-up question
        handle_followup_question(event_data, pr_details)
        return

    # Otherwise, proceed with standard code review
    if event_name != "issue_comment":
        print(f"Unsupported event: {event_name}")
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
