## ✨ Vertex AI 기반 Gemini PR Reviewer

A GitHub Action that **automatically reviews pull requests using Google’s Gemini AI via Vertex AI**.  
Built as a **custom fork** of [`truongnh1992/gemini-ai-code-reviewer`](https://github.com/truongnh1992/gemini-ai-code-reviewer), this version uses **Google Cloud’s secure Vertex AI credentials** instead of Gemini API keys.

---

## 🎯 What’s Different?

This version is designed for teams or enterprises that use **Google Cloud credits** and want:
- **Better security** via service accounts & IAM
- **No manual API key management**
- **Higher quotas, more flexibility**
- **Supports gemini-2.0-flash / Flash models on Vertex AI**

---

## ⚙️ Features

- ✅ Automatic code review comments on pull requests
- 🧠 Powered by Vertex AI (Gemini)
- 🛡️ Secure: Uses GCP service account & IAM, not plain API key
- ✂️ File exclusions supported (e.g., `*.md,*.lock`)

---

## 🚀 How to Use

### 1. Google Cloud Setup
- Create a **service account** in Google Cloud Console
- Grant it the `Vertex AI User` role
- (Optional) Add `Storage Object Viewer` if needed
- Create and download a **JSON key**

### 2. GitHub Secrets (in your target repo)
| Secret Name                  | Description                        |
|-----------------------------|------------------------------------|
| `VERTEXAI_CREDENTIALS_JSON` | Paste the full content of the key |
| `VERTEXAI_PROJECT_ID`       | Your GCP project ID               |

---

### 3. Create Workflow File

`.github/workflows/use-reviewer.yaml`

```yaml
name: Use Vertex AI PR Reviewer

on:
  issue_comment:
    types: [created]

permissions: write-all

jobs:
  call-reviewer:
    uses: merakiplace-developers/gemini-ai-code-reviewer/.github/workflows/code-reviewer-action.yaml@main
    with:
      EXCLUDE: '*.md,*.lock'
    secrets:
      VERTEXAI_CREDENTIALS_JSON: ${{ secrets.VERTEXAI_CREDENTIALS_JSON }}
      VERTEXAI_PROJECT_ID: ${{ secrets.VERTEXAI_PROJECT_ID }}
```

---

### 4. Trigger Review

1. Create or update a pull request
2. Leave a comment: `/gemini-review`
3. Done! The bot will automatically analyze and leave comments on your code 👀✨

---

## 🤖 How It Works

1. Gets the PR diff from GitHub API
2. Sends code hunks to Gemini (via Vertex AI)
3. Parses AI response
4. Posts review comments back on the PR

---

## 📦 Models Supported

| Model Name                  | Description                                  |
|----------------------------|----------------------------------------------|
| `gemini-2.0-flash`         | Powerful, better reasoning                   |

Set your desired model in the Python code (`GenerativeModel("...")`).

---

## 🙏 Credits

- Based on [`truongnh1992/gemini-ai-code-reviewer`](https://github.com/truongnh1992/gemini-ai-code-reviewer)
- Vertex AI version customized for GCP users by [@merakiplace-developers](https://github.com/merakiplace-developers)
- Supported by Google Cloud under the `#VertexAISprint` program ☁️

---

## 📄 License

MIT License – See [LICENSE](./LICENSE)
