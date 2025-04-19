# AI Code Review Action

This GitHub Action automatically reviews pull requests using Google's Vertex AI. It provides intelligent, context-aware code reviews based on software design principles and best practices for various application types.

## Features

- Automatically reviews pull requests when opened or updated
- Responds to follow-up questions on review comments
- Supports multiple programming languages and frameworks
- Detects application type (React/Next.js, React Native, Django, Spring, Celery)
- Customizable code review guidelines
- Multi-language support for review comments

## Supported Application Types

- React/Next.js web applications
- React Native mobile applications
- Django/Python backend applications
- Spring/Kotlin backend applications
- Celery asynchronous tasks
- General purpose (default for any other code)

## Setup

### 1. Create Vertex AI Credentials

1. Set up a Google Cloud Platform account
2. Create a Vertex AI project
3. Create a service account with Vertex AI access
4. Generate a JSON key for the service account

### 2. Add Secrets to Your Repository

Add the following secrets to your GitHub repository:

- `VERTEXAI_CREDENTIALS_JSON`: The entire JSON key content for your service account
- `VERTEXAI_PROJECT_ID`: Your Google Cloud project ID

### 3. Create Custom Guidelines (Optional)

Create one or more markdown files with your team's coding guidelines. For example:

- `docs/CODING_GUIDELINES.md`: General coding practices
- `docs/REACT_GUIDELINES.md`: React/Next.js specific guidelines
- `docs/ARCHITECTURE.md`: Project architecture guidelines

### 4. Add the Workflow File

Create `.github/workflows/code-review.yml` in your repository:

```yaml
name: AI Code Review

on:
  pull_request:
    types: [opened, synchronize]
  issue_comment:
    types: [created]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0

      - name: AI Code Review
        uses: your-org/ai-code-reviewer@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          vertexai_credentials_json: ${{ secrets.VERTEXAI_CREDENTIALS_JSON }}
          vertexai_project_id: ${{ secrets.VERTEXAI_PROJECT_ID }}
          google_cloud_region: "us-central1"
          guidelines_path: "docs/CODING_GUIDELINES.md,docs/REACT_GUIDELINES.md"
          exclude: "*.md,*.txt,package-lock.json,yarn.lock"
          language: "English"
```

## Inputs

| Input | Description | Required | Default |
| ----- | ----------- | -------- | ------- |
| `github_token` | GitHub token for API access | Yes | `${{ github.token }}` |
| `vertexai_credentials_json` | Vertex AI service account credentials JSON | Yes | N/A |
| `vertexai_project_id` | Vertex AI project ID | Yes | N/A |
| `google_cloud_region` | Google Cloud region for Vertex AI | No | `us-central1` |
| `guidelines_path` | Comma-separated list of paths to coding guideline files | No | `""` |
| `exclude` | Comma-separated list of glob patterns for files to exclude | No | `*.md,*.txt,package-lock.json,yarn.lock,*.lock` |
| `language` | Language for AI responses | No | `English` |

## Supported Languages

- English (default)
- Korean (한국어) 
- Japanese (日本語)
- Chinese (中文)
- And many more (see code for full list)

## Customizing Guidelines

For best results, structure your guideline files with clear headers and bullet points. The AI will automatically extract rules and principles from these files and prioritize them during code review.

Example format:

```markdown
# Code Organization

- Keep files under 300 lines of code
- Follow the single responsibility principle
- Use meaningful names for variables and functions

# Error Handling

- Always handle errors explicitly
- Provide clear error messages
- Use try/catch blocks for async operations
```

## Follow-up Questions

Developers can ask follow-up questions by replying to review comments. The AI will provide additional context and explanations based on the code being reviewed and the custom guidelines.

## License

MIT