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
    runs-on: ubuntu-latest
    if: |
      github.event.issue.pull_request &&
      contains(github.event.comment.body, '/gemini-review')
    steps:
      - name: PR Info
        run: |
          echo "Comment: ${{ github.event.comment.body }}"
          echo "Issue Number: ${{ github.event.issue.number }}"
          echo "Repository: ${{ github.repository }}"

      - name: Checkout Repo
        uses: actions/checkout@v3
        with:
          fetch-depth: 0

      - name: Get PR Details
        id: pr
        run: |
          PR_JSON=$(gh api repos/${{ github.repository }}/pulls/${{ github.event.issue.number }})
          echo "head_sha=$(echo $PR_JSON | jq -r .head.sha)" >> $GITHUB_OUTPUT
          echo "base_sha=$(echo $PR_JSON | jq -r .base.sha)" >> $GITHUB_OUTPUT
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - uses: merakiplace-developers/gemini-ai-code-reviewer@main
        with:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          VERTEXAI_CREDENTIALS_JSON: ${{ secrets.VERTEXAI_CREDENTIALS_JSON }}
          VERTEXAI_PROJECT_ID: ${{ secrets.VERTEXAI_PROJECT_ID }}
          EXCLUDE: "*.md,*.txt,package-lock.json,*.yml,*.yaml"
          LANGUAGE: "Korean"
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



---

### 🗣️ Multilingual Support

You can customize the language of the AI review comments using the `LANGUAGE` input.

#### ✅ Supported Languages
> Just set the `LANGUAGE` input (e.g. `"Korean"`, `"Japanese"`) in your workflow, and the reviewer will respond accordingly!

```json
{
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
```

> 🧠 The instruction will be automatically prepended to the prompt sent to Gemini!

## 📦 Models Supported

| Model Name                  | Description                                  |
|----------------------------|----------------------------------------------|
| `gemini-2.0-flash`         | Powerful, better reasoning                   |

Set your desired model in the Python code (`GenerativeModel("...")`).

---

## 🙏 Credits

- Based on [`truongnh1992/gemini-ai-code-reviewer`](https://github.com/truongnh1992/gemini-ai-code-reviewer)
- Vertex AI version customized for GCP users by [@merakiplace-developers](https://github.com/merakiplace-developers)

---

## 📄 License

MIT License – See [LICENSE](./LICENSE)
