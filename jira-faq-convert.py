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


class JiraSolutionExtractor:
    def __init__(self, jira_url, jira_token, jira_email, project_key, ollama_url="http://localhost:11434", model_name="llama3.2:latest"):
        """Initialize the Jira Solution Extractor with credentials and project info"""
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

    def extract_solutions(self, issue_data):
        """Use Ollama to analyze the issues and comments to identify solutions"""
        print(f"Analyzing issues and comments with Ollama model {self.model_name} to extract solutions...")
        issues_with_solutions = []

        with tqdm(total=len(issue_data), desc="Solution extraction") as pbar:
            for issue in issue_data:
                # Prepare the text for analysis
                issue_text = f"Issue: {issue['key']} - {issue['summary']}\n"
                issue_text += f"Description: {issue['description']}\n"
                issue_text += f"Status: {issue['status']}\n"
                issue_text += f"Type: {issue['issue_type']}\n\n"

                if issue['comments']:
                    issue_text += "Comments:\n"
                    for comment in issue['comments']:
                        issue_text += f"- {comment['author']} ({comment['created']}): {comment['body']}\n\n"

                # Skip if issue is too large (to avoid token limits)
                if len(issue_text) > 8000:
                    issue_text = issue_text[:8000] + "... (truncated)"

                # Define the prompt for the AI to extract solutions
                prompt = f"""
                You are a technical documentation assistant that analyzes Jira issues and comments.

                Read the following Jira issue carefully including its description and ALL comments.
                Your task is to:

                1. Determine if there is a clear SOLUTION to the problem described in the ticket. The solution could be in the description or in any of the comments.
                2. If a solution exists, extract and summarize it clearly.
                3. If NO solution exists, simply state "NO_SOLUTION_FOUND".

                Respond in JSON format with these fields:
                {{
                  "has_solution": true/false,
                  "solution_summary": "Brief summary of the solution (if found)",
                  "solution_details": "Detailed explanation of the solution (if found)",
                  "confidence": "high/medium/low (how confident you are that this is a real solution)"
                }}

                The issue:
                {issue_text}
                """

                try:
                    # Call Ollama API
                    analysis = self.call_ollama(prompt)

                    # Try to parse the JSON response
                    try:
                        # Clean up the response to handle potential formatting issues
                        analysis_text = analysis.strip()
                        # Find JSON content within triple backticks if present
                        json_match = re.search(r'```json\s*(.*?)\s*```', analysis_text, re.DOTALL)
                        if json_match:
                            analysis_text = json_match.group(1)
                        else:
                            # Find JSON content within any backticks if present
                            json_match = re.search(r'```\s*(.*?)\s*```', analysis_text, re.DOTALL)
                            if json_match:
                                analysis_text = json_match.group(1)

                        solution_data = json.loads(analysis_text)

                        # Check if we have a valid solution
                        if solution_data.get('has_solution') and solution_data.get('confidence') != 'low':
                            # Add the solution information to the issue data
                            issue['solution'] = {
                                'summary': solution_data.get('solution_summary', 'No summary provided'),
                                'details': solution_data.get('solution_details', 'No details provided'),
                                'confidence': solution_data.get('confidence', 'medium')
                            }
                            issues_with_solutions.append(issue)
                    except (json.JSONDecodeError, AttributeError) as je:
                        # If JSON parsing fails, try to determine if solution exists through text analysis
                        if "NO_SOLUTION_FOUND" not in analysis:
                            # Assume there might be a solution
                            issue['solution'] = {
                                'summary': "Solution may exist, but couldn't parse automatically",
                                'details': analysis[:500],  # Truncate to avoid excessive text
                                'confidence': 'low'
                            }
                            issues_with_solutions.append(issue)
                        print(f"Warning: Couldn't parse JSON for issue {issue['key']}: {str(je)}")

                except Exception as e:
                    print(f"Error analyzing issue {issue['key']}: {str(e)}")

                pbar.update(1)

        return issues_with_solutions

    def generate_faq_documentation(self, issues_with_solutions):
        """Generate FAQ-style documentation from issues with solutions"""
        print(f"Generating FAQ documentation for {len(issues_with_solutions)} issues with solutions...")

        if not issues_with_solutions:
            print("No issues with solutions found. No documentation will be generated.")
            return None

        class PDF(FPDF):
            def header(self):
                self.set_font('Arial', 'B', 12)
                self.cell(0, 10, f"Solution FAQ for {self.project_key}", 0, 1, 'C')
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
        pdf.project_key = self.project_key
        pdf.add_page()

        # Add title
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, f"Solution FAQ for Project: {self.project_key}", 0, 1, 'C')
        pdf.set_font('Arial', 'I', 10)
        pdf.cell(0, 10, f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}", 0, 1, 'C')
        pdf.ln(10)

        # Add introduction
        pdf.chapter_title("Introduction")
        pdf.chapter_body(
            f"This document contains solutions to common problems identified in the {self.project_key} project. "
            f"Each solution has been extracted from Jira tickets and their associated comments. "
            f"This FAQ-style documentation is intended to help team members quickly find solutions to known issues."
        )
        pdf.ln(10)

        # Organize solutions by issue type
        solutions_by_type = {}
        for issue in issues_with_solutions:
            issue_type = issue['issue_type']
            if issue_type not in solutions_by_type:
                solutions_by_type[issue_type] = []
            solutions_by_type[issue_type].append(issue)

        # Add solutions by category
        for issue_type, issues in solutions_by_type.items():
            pdf.add_page()
            pdf.chapter_title(f"{issue_type} Solutions")

            for issue in issues:
                pdf.section_title(f"Q: {issue['summary']}")

                # Add problem context (from description)
                description_preview = issue['description'][:300] + "..." if len(issue['description']) > 300 else issue['description']
                if description_preview:
                    pdf.chapter_body(f"Context: {description_preview}")

                # Add solution
                pdf.chapter_body(f"A: {issue['solution']['summary']}")

                # Add more detailed solution if available
                if issue['solution'].get('details') and issue['solution']['details'] != issue['solution']['summary']:
                    pdf.chapter_body(f"Details: {issue['solution']['details']}")

                # Add ticket reference
                pdf.set_font('Arial', 'I', 10)
                pdf.chapter_body(f"Reference: {issue['key']} (Confidence: {issue['solution']['confidence']})")
                pdf.set_font('Arial', '', 11)

                pdf.ln(5)

        # Save the PDF
        filename = f"output/solution_faq_{self.project_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf.output(filename)
        print(f"FAQ documentation saved to {filename}")

        return filename

    def run(self):
        """Run the solution extraction and FAQ generation process"""
        try:
            # 1. Get all issues
            issues = self.get_all_issues()

            # 2. Extract data including comments
            issue_data = self.extract_issue_data(issues)

            # 3. Extract solutions
            issues_with_solutions = self.extract_solutions(issue_data)

            # 4. Generate FAQ documentation
            if issues_with_solutions:
                pdf_path = self.generate_faq_documentation(issues_with_solutions)
                print(f"Found solutions for {len(issues_with_solutions)} out of {len(issue_data)} issues.")
                print("FAQ generation complete!")
                return pdf_path
            else:
                print("No solutions found in any issues. No documentation generated.")
                return None

        except Exception as e:
            print(f"Error during solution extraction: {str(e)}")
            return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Extract solutions from Jira project and create FAQ documentation')
    parser.add_argument('--project', required=True, help='Jira project key')
    parser.add_argument('--model', default='deepseek-r1:7b', help='Ollama model to use (default:deepseek-r1:7b)')
    parser.add_argument('--ollama-url', default='http://localhost:11434', help='URL for Ollama API (default: http://localhost:11434)')
    args = parser.parse_args()

    # Load credentials from environment variables
    jira_url = os.getenv('JIRA_URL')
    jira_token = os.getenv('JIRA_API_TOKEN')
    jira_email = os.getenv('JIRA_EMAIL')

    if not all([jira_url, jira_token, jira_email]):
        print("Missing required environment variables. Please set JIRA_URL, JIRA_API_TOKEN, and JIRA_EMAIL.")
        exit(1)

    # Create and run the solution extractor
    extractor = JiraSolutionExtractor(
        jira_url=jira_url,
        jira_token=jira_token,
        jira_email=jira_email,
        project_key=args.project,
        ollama_url=args.ollama_url,
        model_name=args.model
    )

    extractor.run()
