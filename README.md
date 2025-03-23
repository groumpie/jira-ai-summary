# 🚀 Jira Issue Report Generator

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)
![Ollama](https://img.shields.io/badge/Ollama-Local_AI-brightgreen)
![License](https://img.shields.io/badge/License-MIT-green)

## 📌 Overview
The **Jira Issue Report Generator** is a Python-based tool that automates the creation of PDF summary reports for Jira issues. It leverages API integrations to fetch data and uses AI via Ollama (running locally) to analyze and summarize issue details efficiently.

🔗 **GitHub Repository**: [Jira AI Summary](https://github.com/groumpie/jira-ai-summary)

## ✨ Features
✅ Fetches Jira issues via API  
✅ AI-powered summarization of issue details  
✅ Generates professional-looking PDF reports  
✅ Works locally with **Ollama**, ensuring privacy and speed  
✅ Simple and easy-to-use interface

## 🔧 Prerequisites
Before running the project, ensure you have the following installed:

- 🐍 **Python** (>= 3.11)
- 📦 **pip**
- 🧠 **Ollama** (running locally)
- 📜 Required Python libraries (see `requirements.txt`)

## 📥 Installation
1. Clone the repository:
   ```sh
   git clone https://github.com/groumpie/jira-ai-summary.git
   cd jira-ai-summary
   ```
2. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
3. Ensure **Ollama** is running locally.

## ⚙️ Configuration
Update the `.env` file with your Jira API credentials and necessary configurations:
```env
JIRA_URL=https://your-jira-instance/api
JIRA_API_TOKEN=your_api_token_here
JIRA_EMAIL=your_email@example.com
```

## 🚀 Usage
Run the script to generate a report with the required arguments:
```sh
python jira-docs.py --project=project-name --model=llama3.2:latest --ollama-url=http://localhost:11434
```

Alternatively, specify issue IDs:
```sh
python jira-docs.py --project=project-name --model=llama3.2:latest --ollama-url=http://localhost:11434
```

### 📂 Output
The script generates a PDF summary report, saved in the `output/` directory.

## 🛠 Roadmap
- [ ] Add customizable report templates
- [ ] Support for multiple output formats (e.g., DOCX, HTML)
- [ ] Enhanced AI summarization options

## 📜 License
This project is licensed under the MIT License.

## 🤝 Contributions
Contributions are welcome! Feel free to open an issue or submit a pull request.

## 📧 Contact
For questions or suggestions, reach out via GitHub Issues or email **george@roumpie.com**.

