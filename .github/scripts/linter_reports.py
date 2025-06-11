import json
from pathlib import Path

def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except:
        return None

reports_dir = Path('.github/linter-reports')

eslint_report = load_json(reports_dir / 'eslint.json')
flake8_report = load_json(reports_dir / 'flake8.json')
shellcheck_report = load_json(reports_dir / 'shellcheck.json')
dartanalyzer_report = load_json(reports_dir / 'dartanalyzer.json')
dotnet_report = load_json(reports_dir / 'dotnet-format.json')
htmlhint_report = load_json(reports_dir / 'htmlhint.json')
stylelint_report = load_json(reports_dir / 'stylelint.json')