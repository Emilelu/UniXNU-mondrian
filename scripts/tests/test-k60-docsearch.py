#!/usr/bin/env python3
"""Tests for scripts/k60-docsearch.py — no network, no 19 MB download.

The index chunk is a JS module, so the two things that actually broke during
development are the two things tested here: `\\'` inside the JS string literal
(which is not valid JSON) and Chinese tokenization (VitePress indexes CJK with
tokenize:'full', so a run is one term and splitting it finds nothing).
"""
import importlib.util
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = os.path.join(ROOT, 'scripts', 'k60-docsearch.py')


def load_tool():
    spec = importlib.util.spec_from_file_location('k60_docsearch', TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def chunk(payload):
    """Write a chunk the way VitePress does it: `const e='<json>';export{e as default};`.

    The JSON is embedded in a *single-quoted* JS string, so every apostrophe in
    the text becomes \\' — the exact shape that made json.loads fail.
    """
    body = json.dumps(payload, ensure_ascii=False)
    # VitePress serialises with JSON.stringify (inner quotes become \" ) and then
    # escapes the result as a single-quoted JS string: \ -> \\ and ' -> \'.
    body = body.replace('\\', '\\\\').replace("'", "\\'")
    return "const e='%s';export{e as default};\n" % body


PAYLOAD = {
    'documentCount': 3,
    'nextId': 3,
    'documentIds': {'0': '/concepts/payload#adt-sidecar', '1': '/zh/guide#预链接', '2': '/devices/x#证据'},
    'storedFields': {
        '0': {'title': 'ADT sidecar', 'titles': ['Boot payload']},
        '1': {'title': '预链接', 'titles': ['指南']},
        '2': {'title': 'Evidence', 'titles': []},
    },
    'index': [
        ['sidecar', {'0': {'0': 3}}],
        ['预链接', {'2': {'1': 4}}],
        ['共享缓存', {'2': {'1': 1, '2': 2}}],
        ["it's", {'2': {'2': 5}}],
    ],
}

CASES = []


def check(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@check('decode.survives_escaped_apostrophe')
def _(tool):
    payload = {'k': "it's a \\ backslash and \"quotes\""}
    body = json.dumps(payload, ensure_ascii=False).replace('\\', '\\\\').replace("'", "\\'")
    assert json.loads(tool.decode_js_string(body)) == payload, body


@check('decode.plain_json_is_unchanged')
def _(tool):
    assert tool.decode_js_string('{"a":1}') == '{"a":1}'


@check('load.reads_a_real_chunk_shape')
def _(tool):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, '@localSearchIndexroot.test.js')
        open(p, 'w', encoding='utf-8').write(chunk(PAYLOAD))
        got = tool.load(p)
        assert got['documentCount'] == 3
        assert got['documentIds']['1'] == '/zh/guide#预链接'


@check('tokenize.chinese_stays_whole')
def _(tool):
    toks = tool.tokenize('预链接 ADT')
    assert ('cjk', '预链接') in toks, toks
    assert ('word', 'adt') in toks, toks


@check('tokenize.latin_words_split')
def _(tool):
    assert [t for _, t in tool.tokenize('unique-chip id')] == ['unique', 'chip', 'id']


@check('search.finds_a_latin_term')
def _(tool):
    pm = tool.postings(PAYLOAD)
    hits = tool.search(tool.tokenize('sidecar'), pm)
    assert list(hits) == ['0'], hits


@check('search.chinese_exact_term')
def _(tool):
    pm = tool.postings(PAYLOAD)
    hits = tool.search(tool.tokenize('预链接'), pm)
    assert list(hits) == ['1'], hits


@check('search.chinese_substring_of_a_term')
def _(tool):
    # 缓存 is inside the indexed run 共享缓存; a char-split tokenizer would find nothing.
    pm = tool.postings(PAYLOAD)
    hits = tool.search(tool.tokenize('缓存'), pm)
    assert set(hits) == {'1', '2'}, hits


@check('search.and_across_tokens')
def _(tool):
    pm = tool.postings(PAYLOAD)
    assert set(tool.search(tool.tokenize('共享 缓存'), pm)) == {'1', '2'}


@check('search.absent_token_finds_nothing')
def _(tool):
    pm = tool.postings(PAYLOAD)
    assert tool.search(tool.tokenize('ramoops'), pm) == {}


@check('locate.returns_anchor_and_chain')
def _(tool):
    anchor, chain = tool.locate(PAYLOAD, '0')
    assert anchor == '/concepts/payload#adt-sidecar', anchor
    assert chain == 'ADT sidecar / Boot payload', chain


@check('postings.merges_fields')
def _(tool):
    pm = tool.postings(PAYLOAD)
    assert pm['预链接'] == {'1': 4}, pm['预链接']


def main():
    tool = load_tool()
    failed = 0
    for name, fn in CASES:
        try:
            fn(tool)
            print('ok   %s' % name)
        except AssertionError as e:
            failed += 1
            print('FAIL %s: %s' % (name, e))
        except Exception as e:
            failed += 1
            print('FAIL %s: %s: %s' % (name, type(e).__name__, e))
    print()
    if failed:
        print('FAILED %d of %d' % (failed, len(CASES)))
        return 1
    print('OK %d cases: the chunk decodes, Chinese stays whole, absence is absence' % len(CASES))
    return 0


if __name__ == '__main__':
    sys.exit(main())
