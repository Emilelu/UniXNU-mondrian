#!/usr/bin/env python3
"""P-252: a tag a workflow downloads from is load-bearing, not spam.

`toolchain-linux-20261119` matches none of the three naming patterns and the gate
used to instruct the operator to delete it. Deleting it drafted the release and
broke `.github/workflows/ios27-kernel.yml:39`, which fetches
`releases/download/toolchain-linux-20261119/unixnu-linux-20261119.tar.gz`.

So the gate reads the allowed set out of the workflows. These cases pin the two
halves of that: a downloaded tag is accepted, and a tag nobody downloads is not,
otherwise the exception swallows the rule it exists to carve out.
"""
import importlib.util
import os
import pathlib
import sys
import tempfile

REPO = pathlib.Path(os.environ.get('K60_REPO') or pathlib.Path(__file__).resolve().parents[2])
GATE = REPO / 'scripts' / 'check-snapshot-tag.py'

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load(root):
    """Import the gate with REPO/WORKFLOWS pointed at a fixture tree."""
    spec = importlib.util.spec_from_file_location('snapshot_gate', str(GATE))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.REPO = str(root)
    module.WORKFLOWS = str(pathlib.Path(root) / '.github' / 'workflows')
    return module


def tree(files):
    root = tempfile.mkdtemp(prefix='k60-tag-')
    for rel, body in files.items():
        path = pathlib.Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8')
    return pathlib.Path(root)


WORKFLOW = """name: ios27
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      TOOLCHAIN_URL: https://github.com/x/y/releases/download/toolchain-linux-20261119/unixnu-linux-20261119.tar.gz
"""


@case
def the_downloaded_tag_is_found():
    root = tree({'.github/workflows/ios27-kernel.yml': WORKFLOW})
    module = load(root)
    found = module.release_tags()
    assert 'toolchain-linux-20261119' in found, found
    assert found['toolchain-linux-20261119'] == ['ios27-kernel.yml'], found


@case
def a_tag_nobody_downloads_is_not_allowed():
    root = tree({'.github/workflows/ios27-kernel.yml': WORKFLOW})
    module = load(root)
    found = module.release_tags()
    assert 'toolchain-linux-20261120' not in found, found


@case
def no_workflow_directory_is_not_a_crash():
    root = tree({'README.md': '# empty'})
    module = load(root)
    assert module.release_tags() == {}, module.release_tags()


@case
def the_three_naming_patterns_still_match():
    module = load(pathlib.Path(tempfile.mkdtemp(prefix='k60-tag-')))
    for name in ('boot-proven-20261113', 'snap-r219', 'v0.1.2-first-frame'):
        assert any(p.match(name) for p in module.ALLOWED), name


@case
def the_live_workflow_names_its_release_tag():
    """The real tree must keep the tag this test exists for."""
    module = load(REPO)
    found = module.release_tags()
    assert 'toolchain-linux-20261119' in found, found


def main():
    failures = 0
    for fn in CASES:
        try:
            fn()
            print(f'ok   {fn.__name__}')
        except AssertionError as exc:
            print(f'FAIL {fn.__name__}: {exc}')
            failures += 1
    print(f'TESTS OK {len(CASES) - failures} cases ({failures} failure(s))')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
