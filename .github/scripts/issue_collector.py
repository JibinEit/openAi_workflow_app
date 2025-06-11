from linter_reports import *
import os

def collect_issues(changed_files):
    issues = []

    # ESLint
    if isinstance(eslint_report, list):
        for rep in eslint_report:
            path = os.path.relpath(rep.get('filePath',''))
            if path in changed_files:
                for msg in rep.get('messages', []):
                    ln = msg.get('line')
                    if ln: issues.append({'file':path,'line':ln,
                                           'code':msg.get('ruleId','ESLint'),
                                           'message':msg.get('message','')})
    # Flake8
    if isinstance(flake8_report, dict):
        for ap, errs in flake8_report.items():
            path = os.path.relpath(ap)
            if path in changed_files:
                for e in errs:
                    ln = e.get('line_number') or e.get('line')
                    if ln: issues.append({'file':path,'line':ln,
                                           'code':e.get('code','Flake8'),
                                           'message':e.get('text','')})

    # ShellCheck
    if isinstance(shellcheck_report, list):
        for ent in shellcheck_report:
            path = os.path.relpath(ent.get('file',''))
            ln = ent.get('line')
            if path in changed_files and ln: issues.append({'file':path,'line':ln,
                                                             'code':ent.get('code','ShellCheck'),
                                                             'message':ent.get('message','')})

    # Dart Analyzer
    if isinstance(dartanalyzer_report, dict):
        for diag in dartanalyzer_report.get('diagnostics', []):
            loc = diag.get('location', {})
            path = os.path.relpath(loc.get('file',''))
            ln = loc.get('range',{}).get('start',{}).get('line')
            if path in changed_files and ln: issues.append({'file':path,'line':ln,
                                                            'code':diag.get('code','DartAnalyzer'),
                                                            'message':diag.get('problemMessage') or diag.get('message','')})

    # .NET Format
    if isinstance(dotnet_report, dict):
        diags = dotnet_report.get('Diagnostics') or dotnet_report.get('diagnostics')
        if isinstance(diags, list):
            for d in diags:
                path = os.path.relpath(d.get('Path') or d.get('path',''))
                ln = d.get('Region',{}).get('StartLine')
                if path in changed_files and ln: issues.append({'file':path,'line':ln,
                                                               'code':'DotNetFormat',
                                                               'message':d.get('Message','')})
    # HTMLHint
    if isinstance(htmlhint_report, list):
        for ent in htmlhint_report:
            path = os.path.relpath(ent.get('file', ''))
            ln   = ent.get('line', None)
            msg  = ent.get('message', '')
            rule = ent.get('rule', 'HTMLHint')
            if path in changed_files and ln:
                issues.append({'file': path, 'line': ln, 'code': rule, 'message': msg})

    # Stylelint
    if isinstance(stylelint_report, list):
        for rep in stylelint_report:
            path = os.path.relpath(rep.get('source', ''))
            ln   = rep.get('line', None)
            msg  = rep.get('text', '')
            rule = rep.get('rule', 'Stylelint')
            if path in changed_files and ln:
                issues.append({'file': path, 'line': ln, 'code': rule, 'message': msg})

    return issues