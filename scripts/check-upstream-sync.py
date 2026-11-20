"""Iron rule 15 — every reference and UniXNU repository is fetched on schedule.

Two things go stale here and both cost real work:

  * a reference repository (the Sheng line, the same-SoC t970 and zizhan lines)
    moves ahead of our clone, so a lane "reads the latest" from a two-day-old
    tree and misses the fix that unblocks it;
  * the official device pages gain entries for our SoC, so nobody looks at the
    board another porter already wrote up.

The registry docs/engineering/UPSTREAM-REPOS.toml lists every clone that feeds
porting work with the ref we follow. `--apply` fetches each remote and records
the time, the remote default-branch head and the local head. This gate then
fails when a fetch is older than --hours, when a listed repository is gone, when
a recorded head moved since the last fetch (the clone is behind), and when the
device pages carry a SoC entry the recorded baseline does not know about.

Repositories we own are fetched too; only the read-only ones are compared for
being behind, because pushing is a separate decision.
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'docs/engineering/UPSTREAM-REPOS.toml'
STATE = ROOT / '.cache/upstream-sync.json'
DOCS = Path('/mnt/e/hackios/UniXNU/docs/zh/devices')
WATCHED = ('sm8475', 'sm8550', 'mondrian', 'k60')
DEFAULT_HOURS = 6.0


class Failure(Exception):
    pass


def git(repo, *arguments):
    done = subprocess.run(['git', '-C', str(repo), *arguments], capture_output=True, text=True)
    if done.returncode:
        raise Failure(f'git {" ".join(arguments)} in {repo}: {done.stderr.strip()}')
    return done.stdout.strip()


def git_maybe(repo, *arguments):
    done = subprocess.run(['git', '-C', str(repo), *arguments], capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else ''


def load(path=REGISTRY):
    if not path.is_file():
        raise Failure(f'no upstream repository registry at {path}')
    document = tomllib.loads(path.read_text(encoding='utf-8'))
    repos = document.get('repo')
    if not repos:
        raise Failure(f'{path} lists no [[repo]] entries')
    return repos


def fetch(repo, name):
    if not (repo / '.git').exists():
        raise Failure(f'{name}: {repo} is not a git clone')
    git(repo, 'fetch', '--all', '--prune', '--quiet')
    head = git(repo, 'rev-parse', 'HEAD')
    default = git_maybe(repo, 'symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD')
    upstream = git_maybe(repo, 'rev-parse', default) if default else ''
    return {'fetched': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
            'head': head, 'upstream': upstream}


def sync(records, path=STATE):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')


def device_pages(docs=None):
    docs = docs or DOCS
    if not docs.is_dir():
        return []
    return sorted(page.stem for page in docs.glob('*.md')
                  if any(word in page.stem.lower() for word in WATCHED))


def check(repos, state, hours, pages_now, allow_behind=False):
    problems = []
    notes = []
    now = dt.datetime.now(dt.timezone.utc)
    oldest = None
    for entry in repos:
        name = entry.get('name')
        if not name:
            problems.append('a [[repo]] entry has no name')
            continue
        repo = ROOT / entry.get('path', '') if not Path(entry.get('path', '')).is_absolute() \
            else Path(entry['path'])
        if not repo.is_dir():
            problems.append(f'{name}: {repo} is missing')
            continue
        saved = state.get(name)
        if not saved:
            problems.append(f'{name}: never fetched; run --apply')
            continue
        try:
            age = (now - dt.datetime.fromisoformat(saved['fetched'])).total_seconds() / 3600
        except (KeyError, ValueError):
            problems.append(f'{name}: the recorded fetch time is unreadable')
            continue
        oldest = age if oldest is None else max(oldest, age)
        if age > hours:
            problems.append(f'{name}: last fetched {age:.1f} h ago, limit {hours:g} h')
        head = git(repo, 'rev-parse', 'HEAD')
        if saved.get('head') != head:
            problems.append(f'{name}: HEAD moved since the last fetch; run --apply')
        if entry.get('read_only') and saved.get('upstream'):
            if head != saved['upstream']:
                behind = git(repo, 'rev-list', '--count', f'{head}..{saved["upstream"]}')
                if behind != '0':
                    line = f'{name}: {behind} commit(s) behind the upstream it follows'
                    if allow_behind:
                        notes.append(line)
                    else:
                        problems.append(line)
    known = set(state.get('__device_pages__') or [])
    for page in pages_now:
        if page not in known:
            problems.append(f'device page {page} appeared since the baseline; read it')
    return problems, notes, oldest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='fetch every listed repository and record it')
    parser.add_argument('--allow-behind', action='store_true',
                        help='print a repository that is behind as a note, not a failure')
    parser.add_argument('--hours', type=float, default=DEFAULT_HOURS)
    parser.add_argument('--registry', type=Path, default=REGISTRY)
    parser.add_argument('--state', type=Path, default=STATE)
    parser.add_argument('--device', type=Path, default=DOCS)
    options = parser.parse_args()
    try:
        repos = load(options.registry)
        state = json.loads(options.state.read_text()) if options.state.is_file() else {}
        if options.apply:
            for entry in repos:
                name = entry.get('name')
                path = Path(entry.get('path', ''))
                repo = path if path.is_absolute() else ROOT / path
                record = fetch(repo, name)
                state[name] = record
                print(f'fetched {name} {record["head"][:12]}')
            state['__device_pages__'] = device_pages(options.device)
            sync(state, options.state)
        problems, notes, oldest = check(repos, state, options.hours,
                                        device_pages(options.device),
                                        allow_behind=options.allow_behind)
    except Failure as error:
        print(f'FAIL: {error}')
        return 2
    for note in notes:
        print(f'note: {note}')
    for problem in problems:
        print(f'FAIL: {problem}')
    age = 'never' if oldest is None else f'{oldest:.1f} h'
    print(f'repositories {len(repos)}, oldest fetch {age}, device pages {len(device_pages(options.device))}, behind notes {len(notes)}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
