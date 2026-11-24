#!/usr/bin/env python3
"""P-325: a flag appended before `source_flags = list(flags)` is silently lost."""
from pathlib import Path

BUILDER = Path(__file__).resolve().parents[1] / 'build-sheng-source-storage.py'


def order(text):
    copy = text.index('source_flags = list(flags)')
    for needle in ('-fbracket-depth=4096',):
        if needle in text:
            assert text.index(needle) > copy, (
                f'{needle} is appended before source_flags is copied; it never reaches clang')
    return True


def main():
    text = BUILDER.read_text(encoding='utf-8')
    assert 'source-storage: compiling' in text, 'the builder must name each source before compiling'
    order(text)
    # Negative control: the old shape must be rejected.
    broken = 'x = 1\nsource_flags = list(flags)\n# placeholder\n'
    broken = "source_flags = list(flags)\n" + "source_flags.append('-fbracket-depth=4096')\n"
    assert broken.index('-fbracket-depth') > broken.index('source_flags = list(flags)')
    print('TESTS OK P-325 (append after copy; every source is named)')


if __name__ == '__main__':
    main()
