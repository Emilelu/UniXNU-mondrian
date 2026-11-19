#!/usr/bin/env python3
"""Prove the carried GLINK copy accepts the INTENT id 0 the K60 modem sends.

The k35 B flight ended its QRTR handshake at the third poll with:

    K60MODEM qrtr: glink poll rc=-5 at 2 rx avail=488 head=560 tail=72 ...
        cmd=0x5 p1=0x1 p2=0x1 w2=0x80 w3=0 w4=0x10005 w5=0x1 w6=0x80 w7=0x1

cmd 5 is GLINK INTENT, w2/w3 are the first pair (size 0x80, id 0) and w6/w7 the
second (size 0x80, id 1): the modem numbers its receive buffers from zero.  Linux
stores that id (idr_alloc(id, id + 1) in qcom_glink_handle_intent()) and hakios
stores every pair unvalidated, so zero is legal; drivers/PongPower/QcomGlink.c
treated it as corruption and the link went down.

Two behaviours are fixed in the copy that ships:

  * an intent numbered zero is a legal buffer number, so it is stored;
  * an intent whose size is zero carries nothing, so it is dropped and the link
    keeps running - it is NOT corruption.  This is the power line's semantics
    (142706ad: g->dropped++; continue;), and the point of the second stream is
    that the next, well formed intent is still processed.

The kernel compiles a copy of the GLINK stack out of 0622 under the k60m_ prefix,
so the fix lives in scripts/update-modem-qrtr-patch.py's DELTA and must be tested
in the copy that actually ships.  This test regenerates that copy, compiles it
with a small harness and drives three byte streams through it:

  id0   VERSION, OPEN(IPCRTR), INTENT(size 0x80, id 0), INTENT(size 0x80, id 1)
        must not report corruption, and the first pair must be stored as id 0,
  drop  VERSION, OPEN(IPCRTR), INTENT(size 0, id 0), INTENT(size 0x80, id 1)
        must not report corruption either: the empty intent is counted as
        dropped and the intent after it is still stored as id 1,
  size0 VERSION, OPEN(IPCRTR), INTENT(size 0, id 0)
        must not report corruption and must store nothing.

Run: python3 scripts/tests/test-k60-glink-intent.py
"""

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GENERATOR = REPO / "scripts/update-modem-qrtr-patch.py"
CORRUPT = -5

HARNESS = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "qcom_glink.h"

static void kick(void *ctx) { (void)ctx; }
static void on_state(void *ctx, QcomGlinkChannel *c, int up)
{ (void)ctx; (void)c; (void)up; }
static void on_recv(void *ctx, QcomGlinkChannel *c, const uint8_t *d, uint32_t n)
{ (void)ctx; (void)c; (void)d; (void)n; }

static QcomGlink g;
static uint8_t rxbuf[1024];
static uint32_t w_at;

static void put32(uint8_t *p, uint32_t v)
{ p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }

static void head(uint16_t cmd, uint16_t p1, uint32_t p2)
{
    put32(rxbuf + w_at, (uint32_t)cmd | ((uint32_t)p1 << 16));
    put32(rxbuf + w_at + 4, p2);
    w_at += 8;
}

static void intent(uint16_t rcid, uint32_t size, uint32_t id)
{
    head(QCOM_GLINK_INTENT, rcid, 1);
    put32(rxbuf + w_at, size);
    put32(rxbuf + w_at + 4, id);
    w_at += 8;
}

int main(int argc, char **argv)
{
    static uint32_t desc[4];
    static uint8_t txbuf[1024];
    static uint8_t storage[4 * 0x4400];
    const char *mode = argc > 1 ? argv[1] : "id0";
    const int with_zero = strcmp(mode, "size0") == 0 || strcmp(mode, "drop") == 0;
    const char *name = "IPCRTR";
    const uint32_t n = (uint32_t)strlen(name) + 1;

    memset(rxbuf, 0, sizeof rxbuf);
    head(QCOM_GLINK_VERSION, 1, 1);
    head(QCOM_GLINK_OPEN, 1, n);
    memcpy(rxbuf + w_at, name, n);
    w_at += (n + 7u) & ~7u;
    /* drop: an empty intent first, then a well formed one; size0: only empty. */
    intent(1, with_zero ? 0u : 0x80u, 0);
    if (strcmp(mode, "size0") != 0)
        intent(1, 0x80u, 1);

    QcomGlinkFifo tx = {&desc[1], &desc[0], txbuf, sizeof txbuf};
    QcomGlinkFifo rx = {&desc[3], &desc[2], rxbuf, sizeof rxbuf};
    if (k60m_glink_adopt(&g, tx, rx, kick, NULL) != 0) {
        printf("adopt failed\n");
        return 2;
    }
    desc[3] = w_at;
    QcomGlinkClient client = {on_state, on_recv};
    QcomGlinkChannel *chan = k60m_glink_channel(&g, "IPCRTR", 0x4400, 4u,
                                                storage, &client, NULL, 0);
    if (chan == NULL) {
        printf("channel failed\n");
        return 2;
    }
    const int rc = k60m_glink_poll(&g);
    printf("poll=%d broken=%u dropped=%u\n", rc, g.broken, g.dropped);
    for (unsigned i = 0; i < QCOM_GLINK_MAX_REMOTE_INTENTS; ++i)
        if (chan->remote[i].valid)
            printf("remote id=%u size=%u busy=%u\n", chan->remote[i].id,
                   chan->remote[i].size, chan->remote[i].busy);
    return 0;
}
'''


def load_generator():
    spec = importlib.util.spec_from_file_location("update_modem_qrtr_patch", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(tmp):
    gen = load_generator()
    header = gen.body(REPO / "drivers/PongPower/QcomGlink.h", {})
    source = gen.body(REPO / "drivers/PongPower/QcomGlink.c",
                      {'"QcomGlink.h"': '"qcom_glink.h"'})
    text = "\n".join(source)
    if "if (!size || !id) return QcomGlinkCorrupt;" in text:
        raise SystemExit("FAIL the carried copy still rejects id 0")
    if "g->dropped++; continue;" not in text:
        raise SystemExit("FAIL the carried copy does not drop an empty intent")
    (tmp / "qcom_glink.h").write_text("\n".join(header) + "\n", encoding="utf-8")
    (tmp / "qcom_glink.c").write_text(text + "\n", encoding="utf-8")
    (tmp / "harness.c").write_text(HARNESS, encoding="utf-8")
    exe = tmp / "harness"
    build_cmd = ["gcc", "-O1", "-Wall", "-Wextra", "-Werror", "-I", str(tmp),
                 "-o", str(exe), str(tmp / "harness.c"), str(tmp / "qcom_glink.c")]
    done = subprocess.run(build_cmd, capture_output=True, text=True)
    if done.returncode != 0:
        print(done.stdout + done.stderr)
        raise SystemExit("FAIL the carried GLINK copy does not compile")
    return exe


def run(exe, mode):
    done = subprocess.run([str(exe), mode], capture_output=True, text=True)
    if done.returncode != 0:
        print(done.stdout)
        raise SystemExit("FAIL the %s stream did not run" % mode)
    return done.stdout


def main():
    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        exe = build(tmp)

        id0 = run(exe, "id0")
        if "poll=-5" in id0 or "broken=0" not in id0:
            print(id0)
            raise SystemExit("FAIL an INTENT with id 0 is still called corruption")
        if "remote id=0 size=128 busy=0" not in id0:
            print(id0)
            raise SystemExit("FAIL the id 0 buffer was not stored")
        print("K60 GLINK INTENT id0 accepted: " + id0.splitlines()[0])

        drop = run(exe, "drop")
        if "poll=-5" in drop or "broken=0" not in drop:
            print(drop)
            raise SystemExit("FAIL an empty intent still stops the link")
        if "remote id=0 " in drop:
            print(drop)
            raise SystemExit("FAIL the empty intent was stored as a buffer")
        if "remote id=1 size=128 busy=0" not in drop:
            print(drop)
            raise SystemExit("FAIL the intent after the empty one was not processed")
        print("K60 GLINK INTENT drop: " + drop.splitlines()[0])

        size0 = run(exe, "size0")
        if "poll=-5" in size0 or "broken=0" not in size0:
            print(size0)
            raise SystemExit("FAIL an empty intent alone still stops the link")
        if "remote id=" in size0:
            print(size0)
            raise SystemExit("FAIL an empty intent alone was stored")
        print("K60 GLINK INTENT size0: " + size0.splitlines()[0])

    print("K60 GLINK INTENT PASS id0 accepted, drop keeps the link, size0 stores nothing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
