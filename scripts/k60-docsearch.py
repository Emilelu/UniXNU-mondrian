#!/usr/bin/env python3
"""Search the official UniXNU documentation offline.

unixnu.com is a VitePress site whose search is the *local* provider: the whole
index ships as a static chunk, so there is no server to ask and no rate limit to
respect. Two chunks hold everything:

  assets/chunks/@localSearchIndexroot.<hash>.js    2026-11
  assets/chunks/@localSearchIndexzh.<hash>.js

Each chunk is `const e='<json>';export{e as default};` — a JavaScript string
literal, so it contains `\\'` which is not valid JSON. Decoded, the payload is a
serialised MiniSearch index:

  documentIds   {"<docId>": "/path#anchor"}
  storedFields  {"<docId>": {"title": "...", "titles": ["..."]}}
  index         [["<term>", {"<fieldId>": {"<docId>": <score>}}], ...]

That is enough to answer "where does the documentation talk about X" without
fetching 103 pages and without guessing. Snippets still need the page, so this
tool prints locations and the heading chain; `--fetch` pulls the one page you
picked and prints the section text.

Why this exists: iron-13/iron-17 ask whether an official page states a
requirement. Reading pages one at a time and reasoning from memory produced
claims that the page did not support (P-280 family). A term that is absent from
the index is evidence of absence; a term that is present comes with a location.
"""
import argparse
import bisect
import hashlib
import html
import json
import os
import re
import sys
import urllib.request

BASE = 'https://unixnu.com/'
BOX = 'assets/chunks/VPLocalSearchBox.BuZN87Uj.js'   # discovered 2026-11-21
CACHE = os.environ.get('K60_DOCSEARCH_CACHE') or '/mnt/e/iOS Port/Work/unixnu-index'
MIN_BYTES = 1_000_000
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) k60-docsearch/1'


def get(url, timeout=60):
    """Fetch with a browser User-Agent: the site answers 403 to python-urllib."""
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={'User-Agent': UA}), timeout=timeout).read()


def decode_js_string(body):
    """Decode a JS single-quoted string literal body (handles \\' which breaks JSON)."""
    out = []
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if c != '\\':
            out.append(c)
            i += 1
            continue
        i += 1
        if i >= n:
            raise ValueError('trailing backslash')
        e = body[i]
        i += 1
        if e in ("'", '"', '\\', '/'):
            out.append(e)
        elif e == 'n':
            out.append('\n')
        elif e == 't':
            out.append('\t')
        elif e == 'r':
            out.append('\r')
        elif e == 'b':
            out.append('\b')
        elif e == 'f':
            out.append('\f')
        elif e == 'u':
            out.append(chr(int(body[i:i + 4], 16)))
            i += 4
        elif e == 'x':
            out.append(chr(int(body[i:i + 2], 16)))
            i += 2
        else:
            raise ValueError('unknown escape \\%s' % e)
    return ''.join(out)


def chunk_names():
    """Ask the site which index chunks exist, so a rebuild does not break us."""
    try:
        box = get(BASE + BOX, 30).decode('utf-8', 'replace')
    except Exception:
        box = ''
    found = sorted(set(re.findall(r'@localSearchIndex(\w+)\.[A-Za-z0-9_-]+\.js', box)))
    if not found:
        found = ['root', 'zh']
    return found, box


def download(name, refresh=False):
    """Return (path, sha256, bytes). Cached under CACHE."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, '@localSearchIndex%s.js' % name)
    if os.path.exists(path) and not refresh and os.path.getsize(path) >= MIN_BYTES:
        data = open(path, 'rb').read()
        return path, hashlib.sha256(data).hexdigest(), len(data)
    _, box = chunk_names()
    m = re.search(r'@localSearchIndex%s\.[A-Za-z0-9_-]+\.js' % re.escape(name), box)
    if not m:
        raise SystemExit('cannot find the %s index chunk: the site changed its bundle '
                         '(rerun --refresh; if it still fails, read %s)' % (name, BASE + BOX))
    url = BASE + 'assets/chunks/' + m.group(0)
    data = get(url, 180)
    if len(data) < MIN_BYTES:
        raise SystemExit('%s returned %d bytes, which is not an index' % (url, len(data)))
    open(path, 'wb').write(data)
    return path, hashlib.sha256(data).hexdigest(), len(data)


def load(path):
    """Decode the chunk once and cache the parsed payload next to it.

    Decoding 19 MB of JS string escapes takes ~4 s; a query should not pay that
    again. The cache key is the chunk's own sha256, so a new index never reuses
    an old parse.
    """
    import pickle
    key = hashlib.sha256(open(path, 'rb').read()).hexdigest()[:16]
    cache = '%s.%s.pkl' % (path, key)
    if os.path.exists(cache):
        try:
            return pickle.load(open(cache, 'rb'))
        except Exception:
            pass
    payload = _decode(path)
    try:
        pickle.dump(payload, open(cache, 'wb'), protocol=4)
    except Exception:
        pass
    return payload


def _decode(path):
    s = open(path, encoding='utf-8', errors='surrogatepass').read()
    a = s.index("'") + 1
    b = s.rindex("';")
    return json.loads(decode_js_string(s[a:b]))


def postings(payload):
    """term -> {docId: score}, merged over fields."""
    out = {}
    for entry in payload['index']:
        term, fields = entry[0], entry[1]
        acc = {}
        for docs in fields.values():
            for doc, score in docs.items():
                acc[doc] = acc.get(doc, 0) + score
        out[term] = acc
    return out


def tokenize(query):
    """Split a query the way each locale is indexed.

    Latin text is indexed per lowercased word. Chinese is indexed with
    tokenize:'full' — a whole run such as 预链接 or 共享缓存 is one term — so a CJK
    run must stay in one piece; splitting it into characters finds nothing.
    Returns a list of (kind, token) with kind in {'word', 'cjk'}.
    """
    out = []
    for chunk in re.split(r'([\u3400-\u9fff]+)', query.lower()):
        if not chunk:
            continue
        if re.search(r'[\u3400-\u9fff]', chunk):
            out.append(('cjk', chunk))
        else:
            for w in re.split(r'[^0-9a-z\u00c0-\u024f]+', chunk):
                if w:
                    out.append(('word', w))
    return out


def search(terms, posting_map, prefix=True):
    """AND across tokens; inside a token, exact hit plus prefix (last) or substring (CJK)."""
    keys = sorted(posting_map)
    hits = None
    for i, (kind, t) in enumerate(terms):
        cand = dict(posting_map.get(t, {}))
        last = (i == len(terms) - 1)
        if kind == 'word' and prefix and last:
            lo = bisect.bisect_left(keys, t)
            for k in keys[lo:]:
                if not k.startswith(t):
                    break
                for doc, score in posting_map[k].items():
                    cand[doc] = max(cand.get(doc, 0), score)
        elif kind == 'cjk':
            # The dictionary holds whole runs; a shorter query is a substring of one.
            for k in keys:
                if k != t and t in k:
                    for doc, score in posting_map[k].items():
                        cand[doc] = max(cand.get(doc, 0), score)
        hits = cand if hits is None else {d: hits[d] + s for d, s in cand.items() if d in hits}
        if not hits:
            return {}
    return hits or {}


def locate(payload, doc_id):
    anchor = payload['documentIds'].get(doc_id, '?')
    sf = payload['storedFields'].get(doc_id) or {}
    chain = ' / '.join([sf.get('title', '')] + list(sf.get('titles') or []))
    return anchor, chain.strip(' /')


def fetch_section(anchor, limit=1600):
    """Pull the page and return the text of the section the anchor names."""
    page = anchor.split('#')[0]
    try:
        raw = get(BASE + page.lstrip('/'), 60).decode('utf-8', 'replace')
    except Exception as e:
        return 'fetch failed: %s' % e
    # VitePress renders each section as <h2 id=...> ... <h2 id=...>. Take the body of
    # the requested id up to the next heading of the same or higher level.
    frag = anchor.split('#')[-1]
    if not frag:
        text = re.sub(r'<[^>]+>', ' ', raw)
        return re.sub(r'\s+', ' ', html.unescape(text))[:limit]
    pid = re.escape(frag)
    m = re.search(r'<h([1-6])[^>]*id="%s"[^>]*>(.*?)</h\1>' % pid, raw, re.S)
    if not m:
        text = re.sub(r'<[^>]+>', ' ', raw)
        return re.sub(r'\s+', ' ', html.unescape(text))[:limit]
    level = int(m.group(1))
    start = m.end()
    rest = raw[start:]
    nxt = re.search(r'<h([1-%d])[^>]*id=' % level, rest)
    body = rest[:nxt.start()] if nxt else rest
    body = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', body, flags=re.S)
    body = re.sub(r'<[^>]+>', ' ', body)
    return re.sub(r'[ \t]+', ' ', html.unescape(body)).strip()[:limit]


def verify_registry(toml_path, refresh=False):
    """Every page the registry claims must exist — in the mirror, and on the site.

    Two different corpora are in play. The registry is pinned by sha256 to the
    docs/zh mirror in the framework repo (versioned, reviewable); unixnu.com is a
    deployment of some revision of it. Measured 2026-11-21: the site indexes 581
    pages, the mirror has 103, and four registry pages exist in the mirror but not
    at those paths on the site.

    So: missing from *both* is an error (a row nobody can ever satisfy). Present in
    the mirror but not deployed is DRIFT — reported with the nearest live path, but
    not fatal, because the pinned text is the one the gate reads.
    """
    import tomllib
    path, sha, size = download('zh', refresh)
    payload = load(path)
    anchors = list(payload['documentIds'].values())
    pages = sorted({a.split('#')[0].rstrip('/') or '/' for a in anchors})
    pageset = set(pages) | {'/zh', '/'}   # the home page carries no section anchors

    mirror = os.environ.get('K60_DOCS_MIRROR')
    if not mirror:
        repo = os.environ.get('K60_FRAMEWORK_REPO') or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'UniXNU')
        mirror = os.path.join(repo, 'docs', 'zh')

    rows = tomllib.load(open(toml_path, 'rb')).get('page', [])
    missing, drift = [], []
    for row in rows:
        rel = row['path'][:-3] if row['path'].endswith('.md') else row['path']
        if rel == 'index':
            want = '/zh'
        elif rel.endswith('/index'):
            want = ('/zh/' + rel[:-len('/index')]).rstrip('/')
        else:
            want = ('/zh/' + rel).rstrip('/')
        if want in ('/zh', ''):
            continue
        if want in pageset:
            continue
        near = [q for q in pages if q.startswith(want[:20])][:3]
        if os.path.isfile(os.path.join(mirror, row['path'])):
            drift.append((row['path'], want, near))
        else:
            missing.append((row['path'], want, near))

    print('registry: %d page(s) in %s' % (len(rows), toml_path))
    print('index:    %d section(s) across %d page(s), sha256 %s'
          % (len(anchors), len(pages), sha[:16]))
    print('mirror:   %s' % mirror)
    for p, want, near in missing:
        print('MISSING  %s -> %s%s' % (p, want,
                                       ('  (near: %s)' % ', '.join(near)) if near else ''))
    for p, want, near in drift:
        print('DRIFT    %s -> %s not deployed%s' % (p, want,
                                                    ('  (live: %s)' % ', '.join(near)) if near else ''))
    if missing:
        print('FAILED: %d page(s) are in neither the mirror nor the site' % len(missing))
        return 1
    if drift:
        print('OK %d page(s) resolve in the pinned mirror; %d are not deployed at that path '
              '(iron-13 reads the mirror, so this is a note, not a failure)'
              % (len(rows) - len(drift), len(drift)))
        return 0
    print('OK every registry page exists on unixnu.com and in the mirror')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='search the official UniXNU documentation offline')
    ap.add_argument('query', nargs='*', help='words; the last one also matches by prefix')
    ap.add_argument('--lang', choices=['en', 'zh', 'both'], default='both')
    ap.add_argument('--page', default='', help='only anchors containing this substring')
    ap.add_argument('--limit', type=int, default=12)
    ap.add_argument('--refresh', action='store_true', help='re-download the index chunks')
    ap.add_argument('--stats', action='store_true', help='print index metadata only')
    ap.add_argument('--fetch', action='store_true', help='also print the section text of the top hit')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--verify-registry', metavar='TOML', default='',
                    help='check that every [[page]] path in the registry exists on the site')
    a = ap.parse_args(argv)

    if a.verify_registry:
        return verify_registry(a.verify_registry, a.refresh)

    names = [n for n in ('root', 'zh') if a.lang in ('both', n if n != 'root' else 'en')]
    payloads = {}
    for n in names:
        path, sha, size = download(n, a.refresh)
        payloads[n] = load(path)
        if a.stats or not a.query:
            print('%s: %s bytes sha256 %s documents %d terms %d'
                  % (n, size, sha[:16], payloads[n]['documentCount'], len(payloads[n]['index'])))

    if a.stats or not a.query:
        return 0

    terms = tokenize(' '.join(a.query))
    if not terms:
        raise SystemExit('no searchable token in %r' % ' '.join(a.query))

    results = []
    for n, payload in payloads.items():
        pm = postings(payload)
        for doc, score in search(terms, pm).items():
            anchor, chain = locate(payload, doc)
            if a.page and a.page not in anchor:
                continue
            results.append((score, n, anchor, chain))
    results.sort(key=lambda r: (-r[0], r[2]))

    if a.json:
        print(json.dumps([{'score': s, 'lang': n, 'anchor': an, 'chain': c}
                          for s, n, an, c in results[:a.limit]], ensure_ascii=False, indent=1))
    else:
        if not results:
            print('no document contains all of: %s' % ' '.join(t for _, t in terms))
            print('(the index holds %d terms; absence here is evidence of absence)'
                  % len(payloads[names[0]]['index']))
        for score, n, anchor, chain in results[:a.limit]:
            print('%-4s %5.1f  %s' % (n, score, anchor))
            if chain:
                print('            %s' % chain)
        if a.fetch and results:
            print('\n--- %s ---' % results[0][2])
            print(fetch_section(results[0][2]))
    return 0 if results else 1


if __name__ == '__main__':
    sys.exit(main())
