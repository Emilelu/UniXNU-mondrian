#!/usr/bin/env python3
"""check-tree-clean must name the file it complains about, whole."""
import pathlib
import shutil
import subprocess
import sys
import tempfile

CHECK = pathlib.Path(__file__).resolve().parents[1] / 'check-tree-clean.py'


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / 'scripts').mkdir()
        shutil.copy2(CHECK, root / 'scripts' / 'check-tree-clean.py')
        subprocess.run(['git', 'init', '-q'], cwd=tmp, check=True)
        subprocess.run(['git', 'config', 'user.email', 't@example.com'], cwd=tmp, check=True)
        subprocess.run(['git', 'config', 'user.name', 't'], cwd=tmp, check=True)
        (root / 'board.toml').write_text('a = 1\n', encoding='utf-8')
        subprocess.run(['git', 'add', 'board.toml'], cwd=tmp, check=True)
        subprocess.run(['git', 'commit', '-qm', 'seed'], cwd=tmp, check=True)
        (root / 'board.toml').write_text('a = 2\n', encoding='utf-8')
        out = subprocess.run([sys.executable, str(root / 'scripts' / 'check-tree-clean.py')],
                             capture_output=True, text=True)
    report = out.stdout + out.stderr
    if 'board.toml' not in report:
        print('FAIL the report does not name board.toml: ' + report)
        return 1
    if 'oard.toml' in report.replace('board.toml', ''):
        print('FAIL the report carries a truncated name: ' + report)
        return 1
    print('TESTS OK 1 case')
    return 0


if __name__ == '__main__':
    sys.exit(main())
