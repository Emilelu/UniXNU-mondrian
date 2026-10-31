#!/usr/bin/env python3
"""Read-only GitHub fork/branch comparison; never fetch, checkout, execute fork code or merge.

python3 scripts/audit-forks.py --output /tmp/mondrian-forks.json
Review the reported commits' actual diffs/dependencies before cherry-picking.
Only GITHUB_TOKEN/GH_TOKEN (optional) is used for API authentication; no token is printed.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.github.com'
NAME = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')


class ApiError(RuntimeError):
    pass


def get(path):
    headers = {'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'UniXNU-mondrian-fork-audit'}
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(API + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        reset = e.headers.get('X-RateLimit-Reset', '')
        detail = ('; API rate-limit reset epoch=' + reset) if reset and e.code in (403, 429) else ''
        raise ApiError(f'GitHub HTTP {e.code} at {path}{detail}') from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise ApiError(f'GitHub API read failed at {path}: {type(e).__name__}') from None


def items(path):
    page = 1
    while True:
        separator = '&' if '?' in path else '?'
        chunk = get(f'{path}{separator}per_page=100&page={page}')
        if not isinstance(chunk, list):
            raise ApiError(f'Expected paginated list at {path}')
        yield from chunk
        if len(chunk) < 100:
            return
        page += 1


def compare(repo, base, owner, head):
    # Pin BOTH ends to exact object IDs. Reading a moving branch by name can
    # produce a comparison for a head different from the one we enumerated.
    spec = urllib.parse.quote(f'{base}...{owner}:{head}', safe='.')
    path = f'/repos/{repo}/compare/{spec}'
    first = get(path + '?per_page=100&page=1')
    commits = list(first['commits'])
    total = first['total_commits']
    page = 2
    while len(commits) < total:
        chunk = get(path + f'?per_page=100&page={page}')['commits']
        if not chunk:
            raise ApiError(f'Incomplete comparison at {path}')
        commits.extend(chunk)
        page += 1
    if len(commits) != total:
        raise ApiError(f'Comparison commit count changed at {path}')
    return {
        'status': first['status'], 'ahead_by': first['ahead_by'],
        'behind_by': first['behind_by'],
        'merge_base': first['merge_base_commit']['sha'],
        'compare_url': first['html_url'],
        'candidate_commits': [
            {'sha': c['sha'], 'url': c['html_url'],
             'subject': c['commit']['message'].splitlines()[0],
             'author': c['commit']['author'],
             'parents': [p['sha'] for p in c['parents']]}
            for c in commits
        ],
        'note': 'Ancestry candidates only; patch equivalence, diff review and validation still required.',
    }


def audit(repo, base_ref):
    if not NAME.fullmatch(repo):
        raise ValueError('Repository must have owner/name form')
    root = get(f'/repos/{repo}')
    base = get(f'/repos/{repo}/commits/{urllib.parse.quote(base_ref, safe="")}')['sha']
    report = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'upstream': repo, 'upstream_url': root['html_url'],
              'base_ref': base_ref, 'base_sha': base,
              'scope': 'All public forks returned by the forks API, including nested forks; all branches.',
              'forks': [], 'errors': [], 'changes_applied': False}
    pending = [repo]
    visited = {repo}
    while pending:
        parent = pending.pop(0)
        try:
            forks = list(items(f'/repos/{parent}/forks?sort=newest'))
        except ApiError as e:
            report['errors'].append(str(e))
            continue
        for fork in forks:
            name = fork['full_name']
            if name in visited:
                continue
            visited.add(name)
            if not NAME.fullmatch(name):
                report['errors'].append('Unexpected repository identifier in GitHub response')
                continue
            if fork.get('forks_count', 0):
                pending.append(name)
            result = {'repo': name, 'url': fork['html_url'],
                      'default_branch': fork['default_branch'],
                      'pushed_at': fork.get('pushed_at'), 'branches': []}
            try:
                branches = list(items(f'/repos/{name}/branches'))
                for branch in branches:
                    entry = {'name': branch['name'], 'head': branch['commit']['sha']}
                    try:
                        entry.update(compare(repo, base, fork['owner']['login'], entry['head']))
                    except ApiError as e:
                        entry['error'] = str(e)
                        report['errors'].append(f'{name}/{branch["name"]}: {e}')
                    result['branches'].append(entry)
            except ApiError as e:
                result['error'] = str(e)
                report['errors'].append(str(e))
            report['forks'].append(result)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', default='Emilelu/UniXNU-mondrian')
    parser.add_argument('--base', default='main')
    parser.add_argument('--output', type=Path, help='Write a JSON report to this path (optional).')
    args = parser.parse_args()
    try:
        report = audit(args.upstream, args.base)
    except (ApiError, ValueError) as e:
        parser.exit(1, f'Fork audit failed: {e}\n')
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Upstream:', report['upstream'], report['base_sha'])
    print('Checked:', report['checked_at'])
    for fork in report['forks']:
        print(f'\n{fork["repo"]}: {len(fork["branches"])} branches')
        for b in fork['branches']:
            if 'error' in b:
                print(' ', b['name'], 'ERROR:', b['error'])
                continue
            print(f'  {b["name"]} {b["head"][:12]} ahead={b["ahead_by"]} behind={b["behind_by"]}')
            for c in b['candidate_commits']:
                print('   ', c['sha'][:12], c['subject'])
    if report['errors']:
        for error in report['errors']:
            print('ERROR:', error, file=sys.stderr)
        print('PARTIAL: errors are not evidence that a fork has no candidates.', file=sys.stderr)
        return 1
    print('\nCOMPLETE: no code fetched/executed or merged; review candidates before import.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
