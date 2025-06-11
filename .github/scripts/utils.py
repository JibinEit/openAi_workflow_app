from pathlib import Path

def get_patch_context(patch: str, line_no: int, ctx: int = 3) -> str:
    file_line = None
    hunk = []
    for line in patch.splitlines():
        if line.startswith('@@ '):
            start = int(line.split()[2].split(',')[0][1:]) - 1
            file_line = start
            hunk = [line]
        elif file_line is not None:
            prefix = line[0]
            if prefix in (' ', '+', '-'):
                if prefix != '-': file_line += 1
                if abs(file_line - line_no) <= ctx: hunk.append(line)
                if file_line > line_no + ctx: break
    return '\n'.join(hunk)

def detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return {
        '.dart': 'Dart/Flutter',
        '.ts': 'TypeScript/Angular',
        '.js': 'JavaScript/React',
        '.jsx': 'JavaScript/React',
        '.tsx': 'TypeScript/React',
        '.py': 'Python',
        '.java': 'Java',
        '.cs': '.NET C#',
        '.go': 'Go',
        '.html': 'HTML',
        '.htm': 'HTML',
        '.css': 'CSS',
        '.scss': 'SCSS/Sass',
        '.less': 'Less',
    }.get(ext, 'general programming')

FENCE_BY_LANG = {
    'Dart/Flutter': 'dart',
    'TypeScript/Angular':'ts',
    'JavaScript/React': 'js',
    'TypeScript/React': 'ts',
    'Python': 'python',
    'Java': 'java',
    '.NET C#': 'csharp',
    'Go': 'go',
    'HTML': 'html',
    'CSS': 'css',
    'SCSS/Sass': 'scss',
    'Less': 'less',
    'general programming': ''
}