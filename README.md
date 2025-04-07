⸻

✨ Vertex AI 기반 Gemini PR Reviewer

A GitHub Action that automatically reviews pull requests using Google’s Gemini AI via Vertex AI.
Built as a custom fork of truongnh1992/gemini-ai-code-reviewer, this version uses Google Cloud’s secure Vertex AI credentials instead of Gemini API keys.

⸻

🎯 What’s Different?

This version is designed for teams or enterprises that use Google Cloud credits and want:
	•	Better control via service account and IAM
	•	Higher quotas and rate limits
	•	No need to manage Gemini API keys manually

⸻

⚙️ Features
	•	💬 Automatic code review comments on pull requests
	•	🧠 Powered by gemini-1.5-pro or gemini-1.5-flash
	•	🔐 Uses Google Cloud’s Vertex AI (no API key required)
	•	✂️ Exclude files with glob patterns (e.g. *.md,*.lock)

⸻

🚀 How to Use
	1.	Create a service account in Google Cloud
	•	Give it the Vertex AI User role
	•	Create a JSON key and save it
	2.	Add the following GitHub Secrets to your target repo:
	•	VERTEXAI_CREDENTIALS_JSON – content of your service account JSON
	•	VERTEXAI_PROJECT_ID – your GCP project ID
	3.	In your target repo, create a workflow file like .github/workflows/use-reviewer.yaml:

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

	4.	Trigger code review
Just comment /gemini-review in a pull request. The bot will fetch the diff, analyze it, and leave review comments automatically!

⸻

🧠 Powered by Vertex AI

This action uses vertexai.generative_models.GenerativeModel under the hood.
You can easily switch between models like:
	•	gemini-1.5-pro-preview
	•	gemini-1.5-flash
	•	or even gemini-1.0-pro if needed

⸻

🙏 Credits

Based on the original open-source project: truongnh1992/gemini-ai-code-reviewer
This version was adapted for Vertex AI users under the #VertexAISprint program, supported by Google ☁️

⸻

📄 License

MIT License – See LICENSE

⸻