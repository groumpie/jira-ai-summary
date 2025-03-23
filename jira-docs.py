import requests
import json
from jira import JIRA
import pandas as pd
import os
from datetime import datetime
from fpdf import FPDF
from dotenv import load_dotenv
import re
import argparse
from tqdm import tqdm

# Load environment variables
load_dotenv()


class JiraDocumentationGenerator:
    def __init__(self, jira_url, jira_token, jira_email, project_key, ollama_url="http://localhost:11434", model_name="llama3.2:latest"):
        """Initialize the Jira Documentation Generator with credentials and project info"""
        self.jira_url = jira_url
        self.jira_token = jira_token
        self.jira_email = jira_email
        self.project_key = project_key
        self.ollama_url = ollama_url
        self.model_name = model_name

        # Initialize Jira client
        self.jira = JIRA(
            server=self.jira_url,
            basic_auth=(self.jira_email, self.jira_token)
        )

        # Create output directory if it doesn't exist
        if not os.path.exists('output'):
            os.makedirs('output')

    def get_all_issues(self):
        """Fetch all issues for the given project"""
        print(f"Fetching issues for project {self.project_key}...")
        issues = []

        # Use JQL to query all issues for the project
        jql_str = f'project = {self.project_key} ORDER BY created DESC'

        # Get issues with pagination (Jira API limits results)
        start_at = 0
        max_results = 100
        total = 100  # Initial value to start the loop

        with tqdm(desc="Fetching issues", unit="issues") as pbar:
            while start_at < total:
                results = self.jira.search_issues(jql_str, startAt=start_at, maxResults=max_results)

                if start_at == 0:
                    total = results.total

                issues.extend(results)
                start_at += len(results)
                pbar.update(len(results))
                pbar.total = total

        return issues

    def get_comments_for_issue(self, issue):
        """Fetch all comments for a given issue"""
        comments = self.jira.comments(issue)
        return comments

    def extract_issue_data(self, issues):
        """Extract relevant data from issues including comments"""
        print("Extracting data from issues and comments...")
        issue_data = []

        with tqdm(total=len(issues), desc="Processing issues") as pbar:
            for issue in issues:
                # Get basic issue info
                issue_info = {
                    'key': issue.key,
                    'summary': issue.fields.summary,
                    'description': issue.fields.description or "",
                    'status': issue.fields.status.name,
                    'issue_type': issue.fields.issuetype.name,
                    'created': issue.fields.created,
                    'updated': issue.fields.updated,
                    'comments': []
                }

                # Get comments
                comments = self.get_comments_for_issue(issue)
                for comment in comments:
                    issue_info['comments'].append({
                        'author': comment.author.displayName,
                        'body': comment.body,
                        'created': comment.created
                    })

                issue_data.append(issue_info)
                pbar.update(1)

        return issue_data

    def call_ollama(self, prompt, temperature=0.2):
        """Call the local Ollama model for analysis"""
        api_url = f"{self.ollama_url}/api/generate"

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "temperature": temperature,
            "stream": False
        }

        try:
            response = requests.post(api_url, json=payload)
            response.raise_for_status()  # Raise exception for 4XX/5XX responses
            return response.json().get('response', '')
        except Exception as e:
            print(f"Error calling Ollama API: {str(e)}")
            return f"Error analyzing with Ollama: {str(e)}"

    def analyze_with_ai(self, issue_data):
        """Use Ollama to analyze the issues and comments to identify solutions and issues"""
        print(f"Analyzing issues and comments with Ollama model {self.model_name}...")
        analyzed_data = []

        with tqdm(total=len(issue_data), desc="AI analysis") as pbar:
            for issue in issue_data:
                # Prepare the text for analysis
                issue_text = f"Issue: {issue['key']} - {issue['summary']}\n"
                issue_text += f"Description: {issue['description']}\n"
                issue_text += f"Status: {issue['status']}\n"
                issue_text += f"Type: {issue['issue_type']}\n\n"

                if issue['comments']:
                    issue_text += "Comments:\n"
                    for comment in issue['comments']:
                        issue_text += f"- {comment['author']}: {comment['body']}\n\n"

                # Skip if issue is too large (to avoid token limits)
                if len(issue_text) > 8000:
                    issue_text = issue_text[:8000] + "... (truncated)"

                # Define the prompt for the AI
                prompt = f"""
                You are a technical documentation assistant that analyzes Jira issues and comments to extract valuable information.

                Analyze the following Jira issue and its comments. Extract:
                1. Key problems identified
                2. Solutions proposed or implemented
                3. Technical decisions made
                4. Any important information that should be documented

                Provide the analysis in a structured format.

                {issue_text}
                """

                try:
                    # Call Ollama API
                    analysis = self.call_ollama(prompt)

                    # Add the analysis to the issue data
                    issue['ai_analysis'] = analysis
                    analyzed_data.append(issue)

                except Exception as e:
                    print(f"Error analyzing issue {issue['key']}: {str(e)}")
                    issue['ai_analysis'] = "Error during analysis"
                    analyzed_data.append(issue)

                pbar.update(1)

        return analyzed_data

    def categorize_issues(self, analyzed_data):
        """Categorize issues based on their type and content"""
        print("Categorizing issues...")
        categories = {
            'Features': [],
            'Bugs': [],
            'Technical Debt': [],
            'Documentation': [],
            'Other': []
        }

        for issue in analyzed_data:
            if 'bug' in issue['issue_type'].lower():
                categories['Bugs'].append(issue)
            elif 'feature' in issue['issue_type'].lower() or 'story' in issue['issue_type'].lower():
                categories['Features'].append(issue)
            elif 'documentation' in issue['issue_type'].lower():
                categories['Documentation'].append(issue)
            elif 'technical' in issue['issue_type'].lower() or 'debt' in issue['issue_type'].lower():
                categories['Technical Debt'].append(issue)
            else:
                categories['Other'].append(issue)

        return categories

    def generate_documentation(self, categorized_data):
        """Generate comprehensive documentation from the analyzed data"""
        print("Generating comprehensive documentation...")

        # Create a prompt for the executive summary
        all_analyses = []
        for category, issues in categorized_data.items():
            if issues:
                all_analyses.append(f"Category: {category}")
                for issue in issues[:3]:  # Limit to 3 issues per category to avoid token limits
                    all_analyses.append(f"Issue {issue['key']}: {issue['summary']}\nAnalysis: {issue['ai_analysis'][:500]}...")

        summary_text = "\n\n".join(all_analyses)

        # Truncate if too long
        if len(summary_text) > 10000:
            summary_text = summary_text[:10000] + "... (truncated)"

        summary_prompt = f"""
        You are a technical documentation expert that synthesizes information into clear, concise summaries.

        Based on the following analyses of Jira issues for project {self.project_key}, 
        write an executive summary that highlights:

        1. Major features and improvements
        2. Common issues and their resolutions
        3. Technical decisions and their rationale
        4. Recommendations for future improvements

        Keep your summary comprehensive but concise.

        Analyses:
        {summary_text}
        """

        try:
            # Call Ollama for executive summary
            executive_summary = self.call_ollama(summary_prompt, temperature=0.3)

        except Exception as e:
            print(f"Error generating executive summary: {str(e)}")
            executive_summary = "Error generating executive summary. Please see the individual issue analyses for details."

        # Build the documentation structure
        documentation = {
            'title': f"Project Documentation: {self.project_key}",
            'date': datetime.now().strftime("%Y-%m-%d"),
            'executive_summary': executive_summary,
            'categories': categorized_data
        }

        return documentation

    def generate_pdf(self, documentation):
        """Generate a PDF with the documentation"""
        print("Generating PDF...")

        class PDF(FPDF):
            def header(self):
                self.set_font('Arial', 'B', 12)
                self.cell(0, 10, documentation['title'], 0, 1, 'C')
                self.ln(5)

            def footer(self):
                self.set_y(-15)
                self.set_font('Arial', 'I', 8)
                self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

            def chapter_title(self, title):
                self.set_font('Arial', 'B', 14)
                self.set_fill_color(200, 220, 255)
                self.cell(0, 10, title, 0, 1, 'L', 1)
                self.ln(5)

            def chapter_body(self, body):
                self.set_font('Arial', '', 11)
                self.multi_cell(0, 5, body)
                self.ln()

            def section_title(self, title):
                self.set_font('Arial', 'B', 12)
                self.cell(0, 8, title, 0, 1, 'L')
                self.ln(3)

        pdf = PDF()
        pdf.add_page()

        # Add title
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, documentation['title'], 0, 1, 'C')
        pdf.set_font('Arial', 'I', 10)
        pdf.cell(0, 10, f"Generated on {documentation['date']}", 0, 1, 'C')
        pdf.ln(10)

        # Add executive summary
        pdf.chapter_title("Executive Summary")
        pdf.chapter_body(documentation['executive_summary'])
        pdf.ln(10)

        # Add categorized issues
        for category_name, issues in documentation['categories'].items():
            if issues:  # Only add categories that have issues
                pdf.add_page()
                pdf.chapter_title(category_name)

                for issue in issues:
                    pdf.section_title(f"{issue['key']}: {issue['summary']}")
                    pdf.chapter_body(f"Status: {issue['status']}\n")

                    if issue['description']:
                        pdf.chapter_body(f"Description: {issue['description'][:500]}..." if len(issue['description']) > 500 else f"Description: {issue['description']}")

                    pdf.chapter_body(f"AI Analysis:\n{issue['ai_analysis']}")
                    pdf.ln(5)

        # Save the PDF
        filename = f"output/documentation_{self.project_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf.output(filename)
        print(f"Documentation saved to {filename}")

        return filename

    def run(self):
        """Run the complete documentation generation process"""
        try:
            # 1. Get all issues
            issues = self.get_all_issues()

            # 2. Extract data including comments
            issue_data = self.extract_issue_data(issues)

            # 3. Analyze with AI
            analyzed_data = self.analyze_with_ai(issue_data)

            # 4. Categorize issues
            categorized_data = self.categorize_issues(analyzed_data)

            # 5. Generate documentation
            documentation = self.generate_documentation(categorized_data)

            # 6. Generate PDF
            pdf_path = self.generate_pdf(documentation)

            print("Documentation generation complete!")
            return pdf_path

        except Exception as e:
            print(f"Error during documentation generation: {str(e)}")
            return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate documentation from Jira project')
    parser.add_argument('--project', required=True, help='Jira project key')
    parser.add_argument('--model', default='deepseek-r1:7b', help='Ollama model to use (default:deepseek-r1:7b)')
    parser.add_argument('--ollama-url', default='http://localhost:11434', help='URL for Ollama API (default: http://localhost:11434)')
    args = parser.parse_args()

    # Load credentials from environment variables
    jira_url = os.getenv('JIRA_URL')
    jira_token = os.getenv('JIRA_API_TOKEN')
    jira_email = os.getenv('JIRA_EMAIL')
    # Load credentials from environment variables
    
    if not all([jira_url, jira_token, jira_email]):
        print("Missing required environment variables. Please set JIRA_URL, JIRA_API_TOKEN, and JIRA_EMAIL.")
        exit(1)

    # Create and run the generator
    generator = JiraDocumentationGenerator(
        jira_url=jira_url,
        jira_token=jira_token,
        jira_email=jira_email,
        project_key=args.project,
        ollama_url=args.ollama_url,
        model_name=args.model
    )

    generator.run()
