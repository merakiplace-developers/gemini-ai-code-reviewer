import fnmatch
import json
import os
import re
import yaml
from github import Github
from google import genai
from google.genai.types import GenerateContentConfig, ThinkingConfig
from typing import List, Dict, Any, Optional, Tuple, Set
from unidiff import Hunk

# === Prompt Templates and System Instructions ===
# Default prompt templates
DEFAULT_PROMPT_TEMPLATES = {
    "default": {
        "description": "Default prompt template for general code review",
        "design_principles": [
            "Single Responsibility Principle",
            "Open/Closed Principle",
            "Liskov Substitution Principle",
            "Interface Segregation Principle",
            "Dependency Inversion Principle"
        ],
        "focus_areas": [
            "Bug detection",
            "Security vulnerabilities",
            "Performance issues",
            "Error handling",
            "Code maintainability",
            "Function interfaces"
        ],
        "prompt_template": """
Your task is reviewing this code fragment as part of a pull request, with particular attention to both functionality and design principles (SOLID, etc.).

{file_context}
Please analyze the following code diff in the file "{file_path}" and consider the pull request context.

Pull request title: {pr_title}
Pull request description:
---
{pr_description}
---
Git diff to review:
```diff
{diff_content}
```

When evaluating this code, consider:
1. Does it follow Single Responsibility Principle? Are classes/functions focused on a single task?
2. Does it follow Open/Closed Principle? Can it be extended without modification?
3. Are method signatures, parameters, and return types well-designed?
4. Are dependencies appropriately managed?
5. Is the code extensible and maintainable?
"""
    },
    "react_nextjs": {
        "description": "Prompt template for React/Next.js web applications",
        "design_principles": [
            "Component composition",
            "Unidirectional data flow",
            "Proper state management",
            "Server-side vs client-side rendering",
            "Static site generation",
            "Incremental static regeneration"
        ],
        "focus_areas": [
            "UI/UX consistency",
            "Performance optimizations",
            "React hooks usage",
            "Next.js routing",
            "Data fetching patterns",
            "Server components vs client components",
            "SEO optimization",
            "Accessibility"
        ],
        "prompt_template": """
Your task is reviewing this React/Next.js code fragment with attention to React and Next.js best practices.

{file_context}
Please analyze the following code diff in the file "{file_path}" and consider the pull request context.

Pull request title: {pr_title}
Pull request description:
---
{pr_description}
---
Git diff to review:
```diff
{diff_content}
```

When evaluating this React/Next.js code, consider:
1. Component Structure: Is the component properly structured? Does it have a clear purpose?
2. React Hooks: Are hooks used correctly (dependencies array, rules of hooks)?
3. Performance: Are there unnecessary re-renders? Is useMemo/useCallback used appropriately?
4. State Management: Is state managed efficiently? Is context/Redux used appropriately?
5. Next.js Patterns: Are Next.js features (routing, data fetching, SSR/SSG/ISR) used correctly?
6. Accessibility: Does the code follow accessibility best practices (semantic HTML, ARIA roles)?
7. SEO: Are metadata, structured data, and page optimizations properly implemented?
8. Error Boundaries: Is error handling implemented appropriately?
9. Code Splitting: Is code splitting used effectively to optimize bundle size?
10. Styling Approach: Is the styling consistent and maintainable (CSS Modules, Styled Components, Tailwind)?
"""
    },
    # Other templates (react_native, django, spring, celery) would be included here
}

# System prompts for AI model
DEFAULT_SYSTEM_INSTRUCTIONS = {
    "default": """
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
    "react_nextjs": """
You are an experienced React and Next.js developer reviewing web application code for quality, correctness, and adherence to React and Next.js best practices.

# Response structure
First, provide a brief summary of the PR's purpose based on the title, description, and code changes.
Then, provide detailed code review comments as specified below.

# Objectives
- Identify bugs, UI/UX issues, and performance problems
- Suggest clear and specific improvements with rationale
- Evaluate code maintainability and readability
- Assess adherence to React and Next.js best practices

# Focus areas
## React and Next.js specific aspects
- Component lifecycle and hooks usage
- State management and data flow
- Performance optimization (memoization, rendering)
- Next.js routing and data fetching (getStaticProps, getServerSideProps, etc.)
- Server Components vs Client Components (in Next.js App Router)
- SEO and metadata optimization
- Accessibility implementation
- Code splitting and bundle optimization

## Design principles
- Component composition and reusability
- Unidirectional data flow
- Separation of UI and business logic
- Proper state management (local vs global)
- Prop drilling avoidance
- SSR, SSG, and ISR patterns

## Architecture & Structure
- Component organization and hierarchy
- Styling approach and consistency
- Folder and file structure
- API integration patterns
- Testing strategies
- Build and deployment optimization

# Response format
- Provide the response in following JSON format: 
  {
    "summary": "Brief summary of the PR's purpose and changes",
    "reviews": [
      {"lineNumber": <line_number>, "reviewComment": "<review comment>"}
    ]
  }
- Provide comments ONLY if there is something to improve, otherwise "reviews" should be an empty array
- When commenting on React or Next.js principles, clearly indicate the pattern or concept at the beginning of your comment
- Focus on React and Next.js specific issues and optimizations

Thoroughly analyze the code before responding, and ensure all feedback is actionable and valuable for a React/Next.js developer.
""",
    # Other system instructions (react_native, django, spring, celery) would be included here
}


# === Configuration and Environment Setup ===
def setup_environment():
    """Initialize environment and clients"""
    # Save credentials to a temp file
    credentials_json_str = os.environ["VERTEXAI_CREDENTIALS_JSON"]
    creds_file_path = "/tmp/google-credentials.json"
    with open(creds_file_path, "w") as f:
        f.write(credentials_json_str)

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_file_path

    # Setup constants
    global PROJECT_ID, LOCATION, GITHUB_TOKEN, LANGUAGE, CUSTOM_GUIDELINES_PATHS
    PROJECT_ID = os.environ["VERTEXAI_PROJECT_ID"]
    LOCATION = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")
    GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
    LANGUAGE = os.environ.get("LANGUAGE", "English")
    CUSTOM_GUIDELINES_PATHS = [
        path.strip()
        for path in os.environ.get("INPUT_GUIDELINES_PATH", "").split(",")
        if path.strip()
    ]

    global VERTEXAI_MODEL_NAME, VERTEXAI_MODEL_TEMPERATURE, VERTEXAI_MODEL_TOP_P, VERTEXAI_MODEL_THINKING_BUDGET
    VERTEXAI_MODEL_NAME = os.environ.get("VERTEXAI_MODEL_NAME", "gemini-2.5-flash-preview-04-17")
    VERTEXAI_MODEL_TEMPERATURE = float(os.environ.get("VERTEXAI_MODEL_TEMPERATURE", 0.8))
    VERTEXAI_MODEL_TOP_P = float(os.environ.get("VERTEXAI_MODEL_TOP_P", 0.95))
    VERTEXAI_MODEL_THINKING_BUDGET = int(os.environ.get("VERTEXAI_MODEL_THINKING_BUDGET", 0))


    # Initialize clients
    global gh, client
    gh = Github(GITHUB_TOKEN)
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)


# Data classes
class PRDetails:
    """Simple class to hold PR details"""

    def __init__(self, owner: str, repo: str, pull_number: int, title: str, description: str):
        self.owner = owner
        self.repo = repo
        self.pull_number = pull_number
        self.title = title
        self.description = description


# === App Type Detection ===
def detect_app_type(repo, file_path: str) -> str:
    """Detect the application type based on file path and content"""
    extension = file_path.split('.')[-1].lower() if '.' in file_path else ''

    # React/Next.js detection
    if extension in ('jsx', 'tsx', 'js', 'ts'):
        try:
            package_files = [f for f in repo.get_contents("") if f.path == 'package.json']
            if package_files:
                package_json = repo.get_contents("package.json")
                content = json.loads(package_json.decoded_content.decode())
                dependencies = content.get('dependencies', {})

                if 'next' in dependencies:
                    return 'react_nextjs'
                if 'react-native' in dependencies or 'expo' in dependencies:
                    return 'react_native'
                if 'react' in dependencies and 'react-dom' in dependencies:
                    return 'react_nextjs'
        except Exception as e:
            print(f"Error checking package.json: {e}")

    # Next.js specific detection
    if 'pages' in file_path or 'app' in file_path:
        if any(f.path.endswith('next.config.js') or f.path.endswith('next.config.mjs')
               for f in repo.get_contents("")):
            return 'react_nextjs'

    # Django detection
    if extension == 'py':
        if any(file.path.endswith('settings.py') or file.path.endswith('urls.py')
               for file in repo.get_contents("")):
            return 'django'
        if 'celery' in file_path.lower() or 'tasks.py' in file_path.lower():
            return 'celery'

    # Spring detection
    if extension in ('kt', 'java'):
        if any(file.path.endswith('application.properties') or
               file.path.endswith('application.yml') or
               'SpringBootApplication' in file.path
               for file in repo.get_contents("")):
            return 'spring'

    return 'default'


# === Guidelines and Prompt Management ===
def load_custom_guidelines(repo) -> Dict[str, Any]:
    """Load and process custom guidelines from specified paths"""
    guidelines = {"content": "", "rules": [], "paths": []}

    if not CUSTOM_GUIDELINES_PATHS:
        return guidelines

    combined_content = []
    all_rules = []
    loaded_paths = []

    for guideline_path in CUSTOM_GUIDELINES_PATHS:
        try:
            guideline_file = repo.get_contents(guideline_path)
            content = guideline_file.decoded_content.decode('utf-8')
            loaded_paths.append(guideline_path)

            combined_content.append(f"## Guidelines from: {guideline_path}")
            combined_content.append(content)

            # Extract rules from content
            rules = extract_rules_from_content(content, guideline_path)
            all_rules.extend(rules)
            print(f"Loaded {len(rules)} guidelines from {guideline_path}")

        except Exception as e:
            print(f"Error loading custom guidelines from {guideline_path}: {e}")

    guidelines["content"] = "\n\n".join(combined_content)
    guidelines["rules"] = all_rules
    guidelines["paths"] = loaded_paths

    if loaded_paths:
        print(f"Successfully loaded guidelines from {len(loaded_paths)} files")

    return guidelines


def extract_rules_from_content(content: str, source_path: str) -> List[Dict[str, str]]:
    """Extract rules from guideline content"""
    rules = []
    lines = content.split('\n')
    current_rule = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for headers as rule titles
        if line.startswith('#'):
            if current_rule:
                rules.append(current_rule)
            current_rule = {"title": line.lstrip('#').strip(), "description": "", "source": source_path}

        # Check for list items
        elif re.match(r'^[0-9]+\.|\*|\-', line):
            rule_text = re.sub(r'^[0-9]+\.|\*|\-', '', line).strip()
            if rule_text:
                rules.append({"title": rule_text, "description": "", "source": source_path})

        # Add to current rule description
        elif current_rule:
            if current_rule["description"]:
                current_rule["description"] += " "
            current_rule["description"] += line

    # Add the last rule if exists
    if current_rule:
        rules.append(current_rule)

    return rules


def load_custom_prompts(repo, pr_details: PRDetails) -> Dict[str, Any]:
    """Load custom prompt templates and system instructions"""
    custom_prompts = DEFAULT_PROMPT_TEMPLATES.copy()
    custom_system_instructions = DEFAULT_SYSTEM_INSTRUCTIONS.copy()
    custom_guidelines = load_custom_guidelines(repo)

    try:
        # Check for custom prompts in .github/prompts directory
        contents = repo.get_contents(".github/prompts")

        for content_file in contents:
            if content_file.name.endswith(('.yml', '.yaml')):
                try:
                    file_content = content_file.decoded_content.decode('utf-8')
                    prompt_config = yaml.safe_load(file_content)

                    app_type = content_file.name.split('.')[0].lower()

                    if 'prompt_template' in prompt_config:
                        custom_prompts[app_type] = prompt_config

                    if 'system_instruction' in prompt_config:
                        custom_system_instructions[app_type] = prompt_config['system_instruction']

                    print(f"Loaded custom prompt for {app_type}")
                except Exception as e:
                    print(f"Error loading custom prompt from {content_file.name}: {e}")
    except Exception as e:
        print(f"Could not load custom prompts: {e}")

    return {
        "prompt_templates": custom_prompts,
        "system_instructions": custom_system_instructions,
        "custom_guidelines": custom_guidelines
    }


def create_file_context(file_path: str) -> str:
    """Create context information about the file based on its path"""
    file_ext = file_path.split('.')[-1].lower() if '.' in file_path else ''
    context = f"File type: {file_ext}\n"

    context_patterns = {
        'controller': "This appears to be a controller component.",
        'model': "This appears to be a model component.",
        'view': "This appears to be a view component.",
        'service': "This appears to be a service component.",
        'repository': "This appears to be a repository/data access component.",
        'util': "This appears to be a utility/helper component.",
        'helper': "This appears to be a utility/helper component.",
        'test': "This appears to be a test file.",
        'component': "This appears to be a UI component.",
        'hook': "This appears to be a React hook.",
        'middleware': "This appears to be a middleware component.",
        'task': "This appears to be an async task.",
        'pages': "This appears to be a Next.js page component.",
        'layout': "This appears to be a Next.js layout component.",
        'api': "This appears to be a Next.js API route."
    }

    # Check for special Next.js app router pages
    if 'app' in file_path.lower() and ('page.tsx' in file_path.lower() or 'page.jsx' in file_path.lower()):
        context += "This appears to be a Next.js App Router page.\n"
    else:
        # Check for other patterns
        for pattern, description in context_patterns.items():
            if pattern in file_path.lower():
                context += f"{description}\n"
                break

    return context


def create_prompt(file_path: str, hunk: Hunk, pr_details: PRDetails, app_type: str,
                  prompt_templates: Dict[str, Any], custom_guidelines: Dict[str, Any] = None) -> str:
    """Create customized prompt for code review"""
    language_map = {
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
    instruction = language_map.get(LANGUAGE, f"✍️ Please answer in {LANGUAGE}.")

    # Create file context and get template
    file_context = create_file_context(file_path)
    template = prompt_templates.get(app_type, prompt_templates['default'])['prompt_template']

    # Add guidelines if available
    guidelines_section = ""
    if custom_guidelines and custom_guidelines.get("content"):
        paths_str = ", ".join(custom_guidelines.get("paths", []))
        guidelines_section = f"""
## Project-Specific Guidelines
The following are project-specific coding guidelines that MUST be prioritized during this review.
Please check if the code complies with these guidelines, and provide specific feedback if it doesn't.
Source files: {paths_str}

{custom_guidelines.get("content")}
"""

    # Format prompt with PR details and code diff
    formatted_prompt = template.format(
        file_context=file_context,
        file_path=file_path,
        pr_title=pr_details.title,
        pr_description=pr_details.description or 'No description provided',
        diff_content=hunk.content
    )

    # Add guidelines after diff content
    if guidelines_section:
        formatted_prompt += guidelines_section

    return f"{instruction}\n\n{formatted_prompt}"


def create_followup_prompt(question: str, conversation_history: List[Dict[str, str]],
                           file_path: str, hunk_content: str = None,
                           pr_details: PRDetails = None, app_type: str = 'default',
                           custom_guidelines: Dict[str, Any] = None) -> str:
    """Create prompt for follow-up responses"""
    language_map = {
        "English": "✍️ Answer must be in English.",
        "Korean": "✍️ 답변은 반드시 한국어로 해주세요.",
        # Other languages would be included here
    }
    instruction = language_map.get(LANGUAGE, f"✍️ Please answer in {LANGUAGE}.")

    # Build context sections
    context_parts = []

    # Add code context
    if hunk_content:
        context_parts.append(f"""
The code being discussed is in file "{file_path}":
```diff
{hunk_content}
```
""")

    # Add PR details
    if pr_details:
        context_parts.append(f"""
Pull request title: {pr_details.title}
Pull request description:
---
{pr_details.description or 'No description provided'}
---
""")

    # Add file type context
    design_context = get_file_design_context(file_path, app_type)
    if design_context:
        context_parts.append(f"\nDesign context:\n{design_context}")

    # Add app-type context
    app_contexts = {
        'react_nextjs': "\nThis is a React/Next.js application, so React and Next.js best practices apply.\n",
        'react_native': "\nThis is a React Native application, so React and mobile development best practices apply.\n",
        'django': "\nThis is a Django application, so Python and Django best practices apply.\n",
        'spring': "\nThis is a Spring/Kotlin application, so Spring Framework and Kotlin best practices apply.\n",
        'celery': "\nThis is a Celery task, so asynchronous processing best practices apply.\n"
    }
    if app_type in app_contexts:
        context_parts.append(app_contexts[app_type])

    # Add custom guidelines
    if custom_guidelines and custom_guidelines.get("content"):
        context_parts.append(f"""
\nProject-specific guidelines to prioritize:
{custom_guidelines.get("content")}
""")

    # Format conversation history
    conversation = "\n\n".join([
        f"{'AI' if msg['role'] == 'assistant' else 'Developer'}: {msg['content']}"
        for msg in conversation_history
    ])

    return f"""{instruction}

You are an AI code reviewer continuing a conversation with a developer about code changes in a pull request. Focus on both functional correctness and software design principles relevant to this type of application.

{' '.join(context_parts)}

Below is the conversation history:
---
{conversation}
---

New question from developer:
{question}

Please provide a helpful, direct response to the developer's question. Maintain your role as a code reviewer, but be conversational and address their specific question or concern. When discussing design principles, be clear about which principle you're referencing and why it matters in this context.
"""


def get_file_design_context(file_path: str, app_type: str) -> str:
    """Get design context based on file path and app type"""
    if not file_path:
        return ""

    context = ""

    # App-specific file contexts
    context_patterns = {
        'react_nextjs': {
            'pages': "This file appears to be a Next.js page using the Pages Router.",
            'app/page': "This file appears to be a Next.js page using the App Router.",
            'component': "This file appears to be a React component, which should follow component best practices.",
            'hook': "This file appears to be a React hook, which should follow the rules of hooks.",
            'api': "This file appears to be a Next.js API route.",
            'layout': "This file appears to be a Next.js layout component."
        },
        'react_native': {
            'component': "This file appears to be a React Native component, which should follow component best practices.",
            'hook': "This file appears to be a React hook, which should follow the rules of hooks.",
            'navigation': "This file appears to be related to navigation in the app."
        },
        'django': {
            'views': "This file appears to be a Django view, which handles HTTP requests and returns responses.",
            'models': "This file appears to be a Django model, which defines database structure.",
            'serializer': "This file appears to be a Django REST framework serializer."
        },
        'spring': {
            'controller': "This file appears to be a Spring controller, which handles HTTP requests.",
            'service': "This file appears to be a Spring service, which contains business logic.",
            'repository': "This file appears to be a Spring repository for data access."
        },
        'celery': {
            'task': "This file appears to be a Celery task definition.",
            'worker': "This file appears to be related to Celery worker configuration."
        }
    }

    # Get patterns for the detected app type
    patterns = context_patterns.get(app_type, {})

    # Special case for Next.js App Router pages
    if app_type == 'react_nextjs' and 'app' in file_path.lower() and (
            'page.tsx' in file_path.lower() or 'page.jsx' in file_path.lower()):
        return patterns.get('app/page', "")

    # Check other patterns
    for pattern, description in patterns.items():
        if pattern in file_path.lower():
            context = description
            break

    return context


# === AI Interaction ===
def get_ai_response(prompt: str, include_summary: bool = True, app_type: str = 'default',
                    system_instructions: Dict[str, str] = DEFAULT_SYSTEM_INSTRUCTIONS,
                    custom_guidelines: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get code review response from AI model"""
    # Get system instruction
    system_instruction = system_instructions.get(app_type, system_instructions['default'])

    # Add custom guidelines to system instruction
    if custom_guidelines and custom_guidelines.get("rules"):
        guidelines_text = "\n\n# Project-specific guidelines to prioritize\n"
        guidelines_text += "The following guidelines must be prioritized during your review. Check if the code complies with these guidelines:\n\n"

        for i, rule in enumerate(custom_guidelines.get("rules", [])):
            title = rule.get("title", f"Rule {i + 1}")
            description = rule.get("description", "")
            source = rule.get("source", "")

            guidelines_text += f"- {title}"
            if description:
                guidelines_text += f": {description}"
            if source:
                guidelines_text += f" [From: {source}]"
            guidelines_text += "\n"

        system_instruction = system_instruction + guidelines_text

    try:
        # Get AI response
        text = generate_ai_content(
            prompt=prompt,
            system_instruction=system_instruction
        )

        # Clean up JSON formatting if present
        if text.startswith('```json'):
            text = text[7:]
        if text.endswith('```'):
            text = text[:-3]

        try:
            # Parse JSON response
            result = json.loads(text)

            # Remove summary if not requested
            if not include_summary and "summary" in result:
                del result["summary"]

            return result
        except json.JSONDecodeError:
            # Handle non-JSON responses
            return {"response": text}

    except Exception as e:
        print(f"AI response parse error: {e}")
        return {"reviews": []}


def get_ai_followup_response(prompt: str, app_type: str = 'default') -> str:
    """Get a conversational followup response from the AI"""
    # Base system instruction
    system_instruction = """
    You are an experienced Software Engineer engaging in a code review conversation.

    # Guidelines for follow-up responses:
    - Be helpful, direct, and conversational
    - Answer the developer's specific questions clearly
    - Provide additional context or explanations when needed
    - Suggest concrete solutions or alternatives if appropriate
    - Use GitHub-flavored Markdown for formatting and code snippets
    - Be respectful and collaborative in tone
    - If relevant, explain the reasoning behind your coding suggestions
    """

    # Add app-specific guidelines
    app_instructions = {
        'react_nextjs': """
        # When discussing React/Next.js development:
        - Focus on React and Next.js specific patterns and best practices
        - Consider SEO and performance implications of choices
        - Address client vs server components when relevant (for App Router)
        - Distinguish between SSR, SSG, and ISR patterns when applicable
        - Reference official React and Next.js documentation when appropriate
        - Consider accessibility and responsive design best practices
        """,
        'react_native': """
        # When discussing React Native development:
        - Focus on React and React Native specific patterns and best practices
        - Consider mobile UI/UX principles when discussing component design
        - Address performance considerations specific to mobile devices
        - Reference official React Native documentation when appropriate
        - Consider cross-platform compatibility issues
        """,
        'django': """
        # When discussing Django development:
        - Focus on Django patterns and best practices
        - Consider database optimization and query performance
        - Address Django-specific security considerations
        - Reference official Django documentation when appropriate
        - Consider RESTful API design principles when applicable
        """,
        'spring': """
        # When discussing Spring/Kotlin development:
        - Focus on Spring Framework patterns and best practices
        - Consider Kotlin language features and idioms
        - Address dependency injection and Spring components
        - Reference official Spring documentation when appropriate
        - Consider enterprise application architecture principles
        """,
        'celery': """
        # When discussing Celery tasks:
        - Focus on asynchronous processing patterns and best practices
        - Consider task idempotency and reliability
        - Address error handling and retry strategies
        - Reference official Celery documentation when appropriate
        - Consider distributed system principles and challenges
        """
    }

    if app_type in app_instructions:
        system_instruction += app_instructions[app_type]

    # Add general software design principles
    system_instruction += """

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
    """

    try:
        # Get AI response
        return generate_ai_content(
            prompt=prompt,
            system_instruction=system_instruction
        )
    except Exception as e:
        print(f"AI followup response error: {e}")
        return "I apologize, but I encountered an error processing your question. Could you please rephrase or simplify your question?"


def generate_ai_content(prompt: str, system_instruction: str):
    # Configure AI request
    config = GenerateContentConfig(
        temperature=VERTEXAI_MODEL_TEMPERATURE,
        top_p=VERTEXAI_MODEL_TOP_P,
        system_instruction=system_instruction,
        thinking_config=ThinkingConfig(thinking_budget=VERTEXAI_MODEL_THINKING_BUDGET),
    )
    response = client.models.generate_content(
        model=VERTEXAI_MODEL_NAME,
        contents=prompt,
        config=config,
    )
    return response.text.strip()


# === GitHub Interaction ===
def get_pr_details() -> PRDetails:
    """Extract PR details from GitHub event data"""
    with open(os.environ["GITHUB_EVENT_PATH"], "r") as f:
        event_data = json.load(f)

    # Determine PR info location in event data
    if "issue" in event_data and "pull_request" in event_data["issue"]:
        pull_number = event_data["issue"]["number"]
        repo_full_name = event_data["repository"]["full_name"]
    else:
        pull_number = event_data["number"]
        repo_full_name = event_data["repository"]["full_name"]

    # Get PR info
    owner, repo_name = repo_full_name.split("/")
    repo = gh.get_repo(repo_full_name)
    pr = repo.get_pull(pull_number)

    return PRDetails(owner, repo_name, pull_number, pr.title, pr.body or "")


def get_diff(pr) -> str:
    """
    Get the diff for a specific PR using direct GitHub API call.
    This bypasses PyGithub's get_diff method which might not be reliable.
    """
    import requests

    # Extract PR details
    repo_name = pr.base.repo.full_name
    pr_number = pr.number

    # Construct API URL for the PR diff
    url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}"

    # Set up headers with authentication
    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "Authorization": f"token {GITHUB_TOKEN}"
    }

    try:
        # Make the API request
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise exception for HTTP errors

        return response.text
    except Exception as e:
        print(f"Error fetching diff from GitHub API: {e}")
        # Return empty string on error to avoid breaking the workflow
        return ""


def check_summary_comment_exists(repo, pr) -> bool:
    """Check if a PR summary comment already exists"""
    for comment in pr.get_review_comments():
        if comment.body.startswith("### PR Summary"):
            return True

    for comment in pr.get_issue_comments():
        if comment.body.startswith("### PR Summary"):
            return True

    return False


def is_follow_up_request(event_data: Dict[str, Any], repo) -> Tuple[bool, Optional[int], Optional[str]]:
    """Check if the current event is a follow-up request to an AI review comment"""
    if "comment" not in event_data:
        return False, None, None

    # Get comment details
    comment_body = event_data.get("comment", {}).get("body", "")
    in_reply_to_id = event_data.get("comment", {}).get("in_reply_to_id")

    if not in_reply_to_id:
        return False, None, None

    try:
        # Find the original comment
        for pr in repo.get_pulls():
            for comment in pr.get_review_comments():
                if comment.id == in_reply_to_id and "Vertex AI Code Review" in comment.body:
                    return True, in_reply_to_id, comment_body
    except Exception as e:
        print(f"Error checking if comment is follow-up: {e}")

    return False, None, None


def get_conversation_history(repo, comment_id: int) -> List[Dict[str, str]]:
    """Retrieve the conversation history for a comment thread"""
    conversation = []

    try:
        # Find the original comment and PR
        original_comment = None
        original_pr = None

        for pr in repo.get_pulls():
            for comment in pr.get_review_comments():
                if comment.id == comment_id:
                    original_comment = comment
                    original_pr = pr
                    break
            if original_comment:
                break

        if original_comment:
            # Add original comment to conversation
            conversation.append({
                "role": "assistant",
                "content": original_comment.body
            })

            # Add related comments
            if original_pr:
                for comment in original_pr.get_review_comments():
                    if comment.id == comment_id:
                        continue

                    if f"#{comment_id}" in comment.body or f"comment {comment_id}" in comment.body:
                        user_type = "assistant" if "github-actions[bot]" in comment.user.login else "user"
                        conversation.append({
                            "role": user_type,
                            "content": comment.body
                        })
    except Exception as e:
        print(f"Error getting conversation history: {e}")

    return conversation


def create_comment(file_path: str, hunk: Hunk, ai_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create comment objects for GitHub review API"""
    comments = []
    diff_lines = hunk.content.splitlines()
    added_line_indices = [i for i, line in enumerate(diff_lines) if line.startswith("+") and not line.startswith("+++")]

    # Add summary comment if available
    if ai_response.get("summary"):
        comments.append({
            "body": f"### PR Summary\n{ai_response.get('summary')}",
            "path": file_path,
            "position": 1  # Position at beginning of diff
        })

    # Add line-specific comments
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


def parse_diff(diff_str: str) -> List[Dict[str, Any]]:
    """Parse git diff into structured format"""
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


def get_file_and_hunk_for_comment(repo, pr, comment_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Get file path and diff content related to a comment"""
    try:
        # Find the comment
        target_comment = None
        for comment in pr.get_review_comments():
            if comment.id == comment_id:
                target_comment = comment
                break

        if target_comment:
            file_path = target_comment.path
            diff = pr.get_diff()
            parsed_diff = parse_diff(diff)

            # Find the file in the diff
            for file_data in parsed_diff:
                if file_data.get('path') == file_path:
                    # Combine all hunks for this file
                    hunk_content = '\n'.join([
                        '\n'.join(hunk.get('lines', []))
                        for hunk in file_data.get('hunks', [])
                    ])
                    return file_path, hunk_content

            # Return just file path if hunks not found
            return file_path, None
    except Exception as e:
        print(f"Error finding file and hunk for comment: {e}")

    return None, None


# === Main Review Logic ===
def analyze_code(repo, pr, parsed_diff: List[Dict[str, Any]], pr_details: PRDetails) -> List[Dict[str, Any]]:
    """Analyze code changes and generate review comments"""
    all_comments = []

    # Check for existing summary
    summary_exists = check_summary_comment_exists(repo, pr)

    # Load custom data
    custom_data = load_custom_prompts(repo, pr_details)
    prompt_templates = custom_data["prompt_templates"]
    system_instructions = custom_data["system_instructions"]
    custom_guidelines = custom_data.get("custom_guidelines", {})

    # Log guidelines info
    if custom_guidelines and custom_guidelines.get("content"):
        print(f"Using custom guidelines from {len(custom_guidelines.get('paths', []))} files")
        if custom_guidelines.get("rules"):
            print(f"Extracted {len(custom_guidelines['rules'])} rules from guidelines")

    # Process each file in the diff
    for file_data in parsed_diff:
        file_path = file_data.get('path', '')
        hunks = file_data.get('hunks', [])

        # Detect app type for this file
        app_type = detect_app_type(repo, file_path)
        print(f"Detected app type for {file_path}: {app_type}")

        # Process each diff hunk
        for i, hunk_data in enumerate(hunks):
            hunk = Hunk()
            hunk.source_start = 1
            hunk.source_length = len(hunk_data.get('lines', []))
            hunk.target_start = 1
            hunk.target_length = len(hunk_data.get('lines', []))
            hunk.content = '\n'.join(hunk_data.get('lines', []))

            # Create prompt and get AI response
            prompt = create_prompt(
                file_path,
                hunk,
                pr_details,
                app_type,
                prompt_templates,
                custom_guidelines
            )

            # First hunk of first file should include summary
            include_summary = (i == 0 and file_data == parsed_diff[0] and not summary_exists)

            # Get AI response
            ai_response = get_ai_response(
                prompt,
                include_summary=include_summary,
                app_type=app_type,
                system_instructions=system_instructions,
                custom_guidelines=custom_guidelines
            )

            # Create and add comments
            file_comments = create_comment(file_path, hunk, ai_response)
            all_comments.extend(file_comments)

    return all_comments


def handle_followup_question(repo, pr_details: PRDetails, comment_id: int, question: str) -> None:
    """Handle follow-up questions from developers"""
    if not comment_id or not question:
        print("Not a valid follow-up question")
        return

    print(f"Handling follow-up question for comment {comment_id}: {question}")

    # Get PR and conversation data
    repo_obj = gh.get_repo(f"{pr_details.owner}/{pr_details.repo}")
    pr = repo_obj.get_pull(pr_details.pull_number)
    conversation_history = get_conversation_history(repo_obj, comment_id)
    file_path, hunk_content = get_file_and_hunk_for_comment(repo_obj, pr, comment_id)

    # Detect app type
    app_type = detect_app_type(repo_obj, file_path) if file_path else 'default'

    # Load guidelines
    custom_guidelines = None
    if CUSTOM_GUIDELINES_PATHS:
        custom_guidelines = load_custom_guidelines(repo_obj)

    # Create prompt for follow-up
    prompt = create_followup_prompt(
        question,
        conversation_history,
        file_path,
        hunk_content,
        pr_details,
        app_type,
        custom_guidelines
    )

    # Get AI response
    ai_response = get_ai_followup_response(prompt, app_type)

    # Post the response
    for comment in pr.get_review_comments():
        if comment.id == comment_id:
            # Add guidelines reference if applicable
            guideline_note = ""
            if CUSTOM_GUIDELINES_PATHS:
                paths_str = ", ".join(CUSTOM_GUIDELINES_PATHS)
                guideline_note = f" _(Using guidelines from: {paths_str})_\n\n"

            pr.create_issue_comment(f"**In reply to [comment](#{comment_id}):**{guideline_note}{ai_response}")
            print(f"Successfully replied to comment {comment_id}")
            return

    print(f"Could not find comment {comment_id} to reply to")


# === Main Function ===
def main():
    """Main function to handle PR review workflow"""
    # Initialize environment and clients
    setup_environment()

    # Load event data
    with open(os.environ["GITHUB_EVENT_PATH"], "r") as f:
        event_data = json.load(f)

    event_name = os.environ.get("GITHUB_EVENT_NAME")
    if event_name != "issue_comment":
        print(f"Unsupported event: {event_name}")
        return

    # Get PR details
    pr_details = get_pr_details()
    repo = gh.get_repo(f"{pr_details.owner}/{pr_details.repo}")
    pr = repo.get_pull(pr_details.pull_number)

    # Check if this is a follow-up question
    is_followup, comment_id, question = is_follow_up_request(event_data, repo)

    if is_followup:
        # Handle follow-up question
        handle_followup_question(repo, pr_details, comment_id, question)
        return

    # Proceed with standard code review
    diff = get_diff(pr)
    if not diff:
        print("No diff found")
        return

    # Log guidelines info
    if CUSTOM_GUIDELINES_PATHS:
        paths_str = ", ".join(CUSTOM_GUIDELINES_PATHS)
        print(f"Using custom guidelines from paths: {paths_str}")
    else:
        print("No custom guidelines paths specified. Using default review criteria.")

    # Parse and filter diff
    parsed_diff = parse_diff(diff)
    exclude_patterns = [p.strip() for p in os.environ.get("INPUT_EXCLUDE", "").split(",") if p.strip()]
    filtered_diff = [f for f in parsed_diff if not any(fnmatch.fnmatch(f.get('path', ''), p) for p in exclude_patterns)]

    # Generate and post comments
    comments = analyze_code(repo, pr, filtered_diff, pr_details)
    if comments:
        # Add guidelines info to review body
        review_body = "Vertex AI Code Review"
        if CUSTOM_GUIDELINES_PATHS:
            paths_str = ", ".join(CUSTOM_GUIDELINES_PATHS)
            review_body += f" (Using guidelines from: {paths_str})"

        print(f"{review_body=}")
        print(f"{comments=}")
        pr.create_review(body=review_body, comments=comments, event="COMMENT")
        print(f"Successfully created review with {len(comments)} comments")


if __name__ == "__main__":
    main()
