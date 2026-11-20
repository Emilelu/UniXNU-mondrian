/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Execute the patched XNU allocation/copy block with bounded fake mbufs.
 * This proves offline bounds and allocation behavior, not socket delivery.
 */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint32_t u_int32_t;
#define KEV_VENDOR_APPLE 1u
#define KEV_IEEE80211_CLASS 6u
#define MLEN TEST_MLEN
#define MCLBYTES 2048u
#define MT_DATA 1
#define relaxed 0
#define os_atomic_inc(p, order) (++*(p))
#define bcopy(src, dst, n) memcpy(dst, src, n)
#define mtod(m, type) ((type)((m)->data))
struct kev_dvector { uint32_t data_length; const void *data_ptr; };
struct kev_msg {
    uint32_t vendor_code, kev_class, kev_subclass, event_code;
    struct kev_dvector dv[5];
};
struct kern_event_msg {
    uint32_t total_size, vendor_code, kev_class, kev_subclass, id, event_code;
    unsigned char event_data[];
};
#define KEV_MSG_HEADER_SIZE ((uint32_t)sizeof(struct kern_event_msg))
struct mbuf { uint32_t m_len; _Alignas(8) unsigned char data[MCLBYTES + 16]; };
static struct mbuf storage;
static struct { unsigned kes_toobig, kes_nomem; } kevtstat;
static unsigned small_calls, cluster_calls, fail_alloc, capacity, static_event_id;
static struct mbuf *allocate(unsigned size) {
    capacity = size;
    memset(&storage, 0, sizeof storage);
    memset(storage.data + size, 0xa5, sizeof storage.data - size);
    return fail_alloc ? NULL : &storage;
}
static struct mbuf *m_get(int wait, int type) {
    (void)wait; (void)type; ++small_calls; return allocate(MLEN);
}
#ifndef BASELINE
static struct mbuf *m_getcl(int wait, int type, int flags) {
    (void)wait; (void)type; (void)flags; ++cluster_calls; return allocate(MCLBYTES);
}
#endif
static int post(struct kev_msg *event_msg, int wait) {
    struct mbuf *m;
    struct kern_event_msg *ev;
    char *tmp;
    u_int32_t total_size;
    int i;
#include "bsd/kern/kern_event.c"
    for (unsigned j = capacity; j < sizeof storage.data; ++j)
        assert(storage.data[j] == 0xa5);
    return 0;
}
static unsigned char payload[MCLBYTES];
static struct kev_msg message(uint32_t vendor, uint32_t klass, uint32_t bytes) {
    struct kev_msg msg = { .vendor_code = vendor, .kev_class = klass };
    msg.dv[0] = (struct kev_dvector){bytes, payload};
    return msg;
}
static void reset(void) {
    small_calls = cluster_calls = fail_alloc = capacity = 0;
    kevtstat.kes_toobig = kevtstat.kes_nomem = 0;
}
static unsigned checks;
#define CHECK(expr) do { assert(expr); ++checks; } while (0)
int main(void) {
    for (unsigned i = 0; i < sizeof payload; ++i) payload[i] = (unsigned char)i;
    reset();
    struct kev_msg msg = message(KEV_VENDOR_APPLE, KEV_IEEE80211_CLASS, 16);
    msg.dv[1] = (struct kev_dvector){540, payload + 16};
#ifdef BASELINE
    CHECK(post(&msg, 1) == EMSGSIZE);
    CHECK(small_calls == 0 && cluster_calls == 0 && kevtstat.kes_toobig == 1);
    printf("baseline rejects 16 + 540 bytes (%u checks)\n", checks);
#else
    CHECK(post(&msg, 1) == 0);
    CHECK(small_calls == 0 && cluster_calls == 1);
    CHECK(storage.m_len == KEV_MSG_HEADER_SIZE + 556);
    CHECK(memcmp(storage.data + KEV_MSG_HEADER_SIZE, payload, 556) == 0);
    CHECK(((struct kern_event_msg *)storage.data)->total_size == storage.m_len);
    reset(); msg = message(1, 6, MLEN - KEV_MSG_HEADER_SIZE);
    CHECK(post(&msg, 1) == 0 && small_calls == 1 && cluster_calls == 0);
    reset(); ++msg.dv[0].data_length;
    CHECK(post(&msg, 1) == 0 && small_calls == 0 && cluster_calls == 1);
    reset(); msg = message(1, 5, MLEN - KEV_MSG_HEADER_SIZE);
    CHECK(post(&msg, 1) == 0 && small_calls == 1);
    reset(); ++msg.dv[0].data_length;
    CHECK(post(&msg, 1) == EMSGSIZE && kevtstat.kes_toobig == 1 && small_calls == 0 && cluster_calls == 0);
    reset(); msg = message(2, 6, 540);
    CHECK(post(&msg, 1) == EMSGSIZE && kevtstat.kes_toobig == 1 && cluster_calls == 0);
    reset(); msg = message(1, 6, MCLBYTES - KEV_MSG_HEADER_SIZE);
    CHECK(post(&msg, 1) == 0 && storage.m_len == MCLBYTES && cluster_calls == 1);
    reset(); ++msg.dv[0].data_length;
    CHECK(post(&msg, 1) == EMSGSIZE && kevtstat.kes_toobig == 1 && cluster_calls == 0);
    reset(); msg = message(1, 6, 16); msg.dv[1] = (struct kev_dvector){UINT32_MAX, payload};
    CHECK(post(&msg, 1) == EMSGSIZE && kevtstat.kes_toobig == 1 && cluster_calls == 0);
    reset(); msg = message(1, 6, UINT32_MAX);
    CHECK(post(&msg, 1) == EMSGSIZE && kevtstat.kes_toobig == 1 && cluster_calls == 0);
    reset(); msg = message(1, 6, 16); msg.dv[2] = (struct kev_dvector){UINT32_MAX, payload};
    CHECK(post(&msg, 1) == 0 && storage.m_len == KEV_MSG_HEADER_SIZE + 16 && small_calls == 1);
    reset(); msg = message(1, 6, 1);
    for (unsigned i = 0; i < 5; ++i) msg.dv[i] = (struct kev_dvector){1, payload + i};
    CHECK(post(&msg, 1) == 0 && storage.m_len == KEV_MSG_HEADER_SIZE + 5);
    CHECK(memcmp(storage.data + KEV_MSG_HEADER_SIZE, payload, 5) == 0);
    reset(); fail_alloc = 1; msg = message(1, 6, 16);
    CHECK(post(&msg, 1) == ENOMEM && kevtstat.kes_nomem == 1 && small_calls == 1);
    reset(); fail_alloc = 1; msg = message(1, 6, 540);
    CHECK(post(&msg, 1) == ENOMEM && kevtstat.kes_nomem == 1 && cluster_calls == 1);
    printf("patched event allocation/copy: %u checks passed (MLEN=%u)\n", checks, (unsigned)MLEN);
#endif
    return 0;
}
