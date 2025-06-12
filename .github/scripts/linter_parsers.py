import json
from pathlib import Path
import os # Used for os.path.relpath to normalize paths

def load_json_report(path: Path):
    """
    Safely loads a JSON file from a given path.
    Returns the parsed JSON content or None if the file is not found or invalid.
    """
    try:
        if not path.exists():
            print(f"⚠️ Warning: Linter report not found at {path}. Skipping.")
            return None
        content = path.read_text()
        if not content.strip(): # Handle empty files
            print(f"⚠️ Warning: Linter report {path} is empty. Skipping.")
            return None
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {path}: {e}. Skipping this report.")
        return None
    except Exception as e:
        print(f"❌ An unexpected error occurred while reading {path}: {e}. Skipping.")
        return None

def load_all_linter_reports(reports_dir: Path) -> dict:
    """
    Loads all expected linter JSON reports from the specified directory.
    If a report is missing or invalid, its entry will be None.

    Args:
        reports_dir (Path): The Path object for the directory containing linter reports.

    Returns:
        dict: A dictionary where keys are linter names and values are their parsed JSON reports (or None).
    """
    reports = {}
    print(f"🔍 Loading linter reports from: {reports_dir}")

    # Define expected report files relative to reports_dir
    # Add or remove linters here as needed for your project
    expected_reports = {
        'eslint': reports_dir / 'eslint.json',
        'flake8': reports_dir / 'flake8.json',
        'shellcheck': reports_dir / 'shellcheck.json',
        'dartanalyzer': reports_dir / 'dartanalyzer.json',
        'dotnet': reports_dir / 'dotnet-format.json', # .NET Format can include diagnostics
        'htmlhint': reports_dir / 'htmlhint.json',
        'stylelint': reports_dir / 'stylelint.json',
        # Add more linters here as needed, ensure you have logic to parse them below
    }

    for linter_name, file_path in expected_reports.items():
        reports[linter_name] = load_json_report(file_path)

    return reports

def collect_all_issues(reports_dict: dict, changed_files_list: list) -> list:
    """
    Consolidates issues from various linter reports into a standardized list.
    Only includes issues from files that were changed in the PR and have an associated patch.

    Args:
        reports_dict (dict): A dictionary of parsed linter reports (from load_all_linter_reports).
        changed_files_list (list): A list of file paths that were changed in the PR.

    Returns:
        list: A standardized list of dictionaries, where each dictionary represents an issue:
              {'file': 'path/to/file.js', 'line': 123, 'code': 'ESLint_Rule', 'message': 'Issue description'}
    """
    issues = []
    processed_files_count = 0

    # Helper to normalize file paths across different OS environments
    def normalize_path(p):
        return os.path.normpath(p)

    # Convert changed_files_list to a set for faster lookup
    changed_files_set = {normalize_path(f) for f in changed_files_list}

    print(f"✅ Changed files in PR for linting: {changed_files_list}")

    # --- Parser for ESLint Reports ---
    # ESLint reports are typically a list of file objects
    if isinstance(reports_dict.get('eslint'), list):
        print("Processing ESLint reports...")
        for report_entry in reports_dict['eslint']:
            # ESLint 'filePath' might be absolute, make it relative to the repo root
            file_path = normalize_path(report_entry.get('filePath', ''))
            if file_path in changed_files_set:
                processed_files_count += 1
                for message in report_entry.get('messages', []):
                    line_number = message.get('line')
                    if line_number is not None:
                        issues.append({
                            'file': file_path,
                            'line': line_number,
                            'code': message.get('ruleId', 'ESLint'),
                            'message': message.get('message', 'ESLint issue')
                        })

    # --- Parser for Flake8 Reports ---
    # Flake8 JSON reports are typically a dictionary where keys are file paths
    if isinstance(reports_dict.get('flake8'), dict):
        print("Processing Flake8 reports...")
        for file_path_key, errors in reports_dict['flake8'].items():
            file_path = normalize_path(file_path_key)
            if file_path in changed_files_set:
                processed_files_count += 1
                for error in errors:
                    line_number = error.get('line_number') or error.get('line') # Handle potential key variations
                    if line_number is not None:
                        issues.append({
                            'file': file_path,
                            'line': line_number,
                            'code': error.get('code', 'Flake8'),
                            'message': error.get('text', 'Flake8 issue')
                        })

    # --- Parser for ShellCheck Reports ---
    # ShellCheck reports are typically a list of issue objects
    if isinstance(reports_dict.get('shellcheck'), list):
        print("Processing ShellCheck reports...")
        for issue_entry in reports_dict['shellcheck']:
            file_path = normalize_path(issue_entry.get('file', ''))
            line_number = issue_entry.get('line')
            if file_path in changed_files_set and line_number is not None:
                processed_files_count += 1
                issues.append({
                    'file': file_path,
                    'line': line_number,
                    'code': issue_entry.get('code', 'ShellCheck'),
                    'message': issue_entry.get('message', 'ShellCheck issue')
                })

    # --- Parser for Dart Analyzer Reports ---
    # Dart Analyzer reports typically have a 'diagnostics' list
    if isinstance(reports_dict.get('dartanalyzer'), dict):
        print("Processing Dart Analyzer reports...")
        for diagnostic in reports_dict['dartanalyzer'].get('diagnostics', []):
            location = diagnostic.get('location', {})
            file_path = normalize_path(location.get('file', ''))
            line_number = location.get('range', {}).get('start', {}).get('line')
            if file_path in changed_files_set and line_number is not None:
                processed_files_count += 1
                issues.append({
                    'file': file_path,
                    'line': line_number,
                    'code': diagnostic.get('code', 'DartAnalyzer'),
                    'message': diagnostic.get('problemMessage') or diagnostic.get('message', 'Dart Analyzer issue')
                })

    # --- Parser for .NET Format Reports ---
    # .NET Format reports have a 'Diagnostics' or 'diagnostics' list
    if isinstance(reports_dict.get('dotnet'), dict):
        print("Processing .NET Format reports...")
        diagnostics = reports_dict['dotnet'].get('Diagnostics') or reports_dict['dotnet'].get('diagnostics')
        if isinstance(diagnostics, list):
            for diag_entry in diagnostics:
                file_path = normalize_path(diag_entry.get('Path') or diag_entry.get('path', '')) # Handle casing
                # .NET format lines are 0-indexed in JSON, so add 1 for user-facing
                line_number = diag_entry.get('Region', {}).get('StartLine')
                if line_number is not None: line_number += 1 # Convert to 1-indexed
                if file_path in changed_files_set and line_number is not None:
                    processed_files_count += 1
                    issues.append({
                        'file': file_path,
                        'line': line_number,
                        'code': 'DotNetFormat', # Often no specific code for format issues
                        'message': diag_entry.get('Message', 'DotNet Format issue')
                    })

    # --- Parser for HTMLHint Reports ---
    # HTMLHint reports are typically a list of issue objects
    if isinstance(reports_dict.get('htmlhint'), list):
        print("Processing HTMLHint reports...")
        for issue_entry in reports_dict['htmlhint']:
            file_path = normalize_path(issue_entry.get('file', ''))
            line_number = issue_entry.get('line')
            if file_path in changed_files_set and line_number is not None:
                processed_files_count += 1
                issues.append({
                    'file': file_path,
                    'line': line_number,
                    'code': issue_entry.get('rule', 'HTMLHint'), # Rule ID is usually the code
                    'message': issue_entry.get('message', 'HTMLHint issue')
                })

    # --- Parser for Stylelint Reports ---
    # Stylelint reports are typically a list of result objects, each with a 'warnings' list
    if isinstance(reports_dict.get('stylelint'), list):
        print("Processing Stylelint reports...")
        for result_entry in reports_dict['stylelint']:
            file_path = normalize_path(result_entry.get('source', ''))
            if file_path in changed_files_set:
                processed_files_count += 1
                for warning in result_entry.get('warnings', []):
                    line_number = warning.get('line')
                    if line_number is not None:
                        issues.append({
                            'file': file_path,
                            'line': line_number,
                            'code': warning.get('rule', 'Stylelint'),
                            'message': warning.get('text', 'Stylelint issue')
                        })
    print(f"📊 Collected {len(issues)} issues from {processed_files_count} changed files.")
    return issues