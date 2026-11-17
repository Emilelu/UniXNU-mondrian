/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#ifndef TEST_K60_OWNER_FIXTURE_H
#define TEST_K60_OWNER_FIXTURE_H
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#include "../../drivers/PongPower/K60AdspOwnerStages.h"

/* Each binary links the real engine, SMEM, MDT, builder, parser and readiness. */
#define FX_SMEM_BYTES 0x200000u
#define FX_PART 0x1000u
#define FX_PART_BYTES 0x10000u
#define FX_PREFIX 148u
#define FX_HASH 16u
#define FX_MDT_BYTES (FX_PREFIX + FX_HASH)
static unsigned fx_cases;
static const char *fx_name;
#define CHECK(test) do { if (!(test)) { \
    fprintf(stderr, "FAIL %s:%d: %s: %s\n", __FILE__, __LINE__, fx_name, #test); \
    exit(1); } } while (0)

typedef struct {
    K60OwnerSession session;
    K60OwnerSession *owner;
    K60AdspOwnerLease wrapper_lease;
    unsigned commit_reenter;
    K60BatteryConfig config;
    K60OwnerOps ops;
    K60OwnerPublishOps publish;
    K60HandoffPlan plan;
    _Alignas(8) uint32_t memory[FX_SMEM_BYTES / 4];
    uint8_t mdt[FX_MDT_BYTES], metadata[FX_MDT_BYTES], payload[8], loaded[24];
    uint8_t remote_before[40], property[K60_HANDOFF_BYTES];
    uint32_t remote_offset, baseline_up, lock_up, epoch, ready_bytes, ready_restart;
    int available_value, reader_rc, bad_handle, exclusive_rc, zero_cookie;
    int resources_rc, live_value, running, map_rc, bad_mapping, misaligned_map;
    int init_rc, mem_rc, load_rc, auth_rc, shutdown_rc, stop_after_shutdown;
    int ready_rc, remote_not_ready, root_value, exists_value, commit_rc;
    int lose_live_after_auth;
    unsigned lock_fail_on, live_fail_on, piece_fail_on, piece_short_on, corrupt_parse_on_lock;
    unsigned available_calls, reader_calls, close_calls, exclusive_calls, release_calls;
    unsigned resources_calls, resources_release_calls, stopped_calls, live_calls;
    unsigned map_calls, unmap_calls, lock_calls, unlock_calls, locked, allocations;
    unsigned piece_calls, init_calls, mem_calls, load_calls, auth_calls, shutdown_calls;
    unsigned ready_calls, reports[6], report_stage, root_calls, exists_calls;
    unsigned commit_calls, property_writes;
    int report_rc;
    char pas_trace[16], cleanup[16];
    size_t pas_used, cleanup_used;
} OwnerFixture;

static inline uint8_t *fx_bytes(OwnerFixture *f) { return (uint8_t *)f->memory; }
static inline uint32_t fx_get(OwnerFixture *f, uint32_t at) { return f->memory[at / 4]; }
static inline void fx_put(OwnerFixture *f, uint32_t at, uint32_t value)
{ CHECK(!(at & 3u)); f->memory[at / 4] = value; }
static inline void fx_le16(uint8_t *p, uint16_t v)
{ p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static inline void fx_le32(uint8_t *p, uint32_t v)
{ fx_le16(p, (uint16_t)v); fx_le16(p + 2, (uint16_t)(v >> 16)); }
static inline void fx_trace(char *out, size_t *used, char event)
{ CHECK(*used < 15); out[(*used)++] = event; out[*used] = 0; }
static inline void fx_outside(OwnerFixture *f)
{ CHECK(!f->locked); CHECK(!f->owner->locked); }
static inline int fx_zero(const void *p, size_t n)
{ const uint8_t *b = (const uint8_t *)p; while (n--) if (*b++) return 0; return 1; }
static inline void fx_zero_lease(OwnerFixture *f)
{ CHECK(fx_zero(&f->owner->lease, sizeof f->owner->lease)); }
static inline void fx_failed(OwnerFixture *f)
{
    CHECK(f->owner->phase == K60OwnerFailed); fx_zero_lease(f); fx_outside(f);
    CHECK(!f->owner->reserved && !f->owner->resources_held);
    CHECK(!f->owner->mapped && !f->owner->image_open); CHECK(!f->property_writes);
}
static inline void fx_reported(OwnerFixture *f, unsigned stage, int rc)
{ CHECK(f->reports[stage] == 1); CHECK(f->report_stage == stage); CHECK(f->report_rc == rc); }
static inline int fx_available(void *context, const K60BatteryConfig *c)
{
    OwnerFixture *f = context;
    f->owner = (K60OwnerSession *)((uint8_t *)(void *)c - offsetof(K60OwnerSession, config));
    fx_outside(f); ++f->available_calls;
    CHECK(c->smem_base == UINT64_C(0x80900000) && c->smem_bytes == FX_SMEM_BYTES);
    CHECK(c->adsp_base == UINT64_C(0x9fd00000) && c->adsp_bytes == 0x3100000u);
    CHECK(c->mutex_base == 0x1f4100cu && c->ipcc_base == 0xed18000u);
    CHECK(c->remote_pid == 2 && c->ipcc_client == 3 && !c->ipcc_signal);
    return f->available_value;
}
static inline int fx_piece(void *context, uint32_t index, const uint8_t **bytes, size_t *n)
{
    OwnerFixture *f = context; fx_outside(f); ++f->piece_calls; CHECK(index == 2);
    if (f->piece_calls == f->piece_fail_on) return -1;
    *bytes = f->payload; *n = f->piece_calls == f->piece_short_on ? 7 : sizeof f->payload;
    return 0;
}
static inline int fx_reader(void *context, K60OwnerImage *image)
{
    OwnerFixture *f = context; fx_outside(f); ++f->reader_calls;
    if (f->reader_rc) return f->reader_rc;
    image->mdt = f->mdt; image->bytes = sizeof f->mdt; image->piece = fx_piece;
    image->context = f; image->handle = f->bad_handle ? NULL : f->mdt;
    image->metadata = f->metadata; image->metadata_capacity = sizeof f->metadata; return 0;
}
static inline void fx_close(void *context, K60OwnerImage *image)
{
    OwnerFixture *f = context; fx_outside(f); CHECK(image == &f->owner->image);
    ++f->close_calls; fx_trace(f->cleanup, &f->cleanup_used, 'C');
}
static inline int fx_exclusive(void *context, const K60BatteryConfig *c, uint32_t *epoch, void **cookie)
{
    OwnerFixture *f = context; fx_outside(f); CHECK(c == &f->owner->config);
    ++f->exclusive_calls; if (f->exclusive_rc) return f->exclusive_rc;
    *epoch = f->epoch; *cookie = f->zero_cookie ? NULL : f; return 0;
}
static inline void fx_release(void *context, void *cookie)
{
    OwnerFixture *f = context; fx_outside(f); CHECK(cookie == f || f->zero_cookie);
    CHECK(!f->running); ++f->release_calls; fx_trace(f->cleanup, &f->cleanup_used, 'E');
}
static inline int fx_resources(void *context, void *cookie)
{
    OwnerFixture *f = context; fx_outside(f); CHECK(cookie == f);
    ++f->resources_calls; return f->resources_rc;
}
static inline void fx_resources_release(void *context, void *cookie)
{
    OwnerFixture *f = context; fx_outside(f); CHECK(cookie == f && !f->running);
    ++f->resources_release_calls; fx_trace(f->cleanup, &f->cleanup_used, 'R');
}
static inline int fx_stopped(void *context, void *cookie)
{
    OwnerFixture *f = context; fx_outside(f); CHECK(cookie == f || f->zero_cookie);
    ++f->stopped_calls;
    if (f->owner->auth_attempted) fx_trace(f->cleanup, &f->cleanup_used, 'T');
    return !f->running;
}
static inline int fx_live(void *context, void *cookie, uint32_t epoch)
{
    OwnerFixture *f = context; fx_outside(f); CHECK(cookie == f && epoch == f->epoch);
    ++f->live_calls; return f->live_calls == f->live_fail_on ? 0 : f->live_value;
}
static inline int fx_map(void *context, const K60BatteryConfig *c, K60Smem *smem)
{
    OwnerFixture *f = context; fx_outside(f); CHECK(c == &f->owner->config);
    CHECK(!f->running); ++f->map_calls; if (f->map_rc) return f->map_rc;
    smem->base = fx_bytes(f) + f->misaligned_map;
    smem->size = FX_SMEM_BYTES - (f->bad_mapping ? 4096 : 0); return 0;
}
static inline void fx_unmap(void *context, K60Smem *smem)
{
    OwnerFixture *f = context; fx_outside(f); CHECK(smem == &f->owner->smem && !f->running);
    ++f->unmap_calls; fx_trace(f->cleanup, &f->cleanup_used, 'U');
}
static inline int fx_lock(void *context)
{
    OwnerFixture *f = context; fx_outside(f); ++f->lock_calls;
    if (f->lock_calls == f->lock_fail_on) return -1;
    if (f->lock_calls == f->corrupt_parse_on_lock) f->owner->config.adsp_base ^= 4096u;
    f->locked = 1; f->lock_up = fx_get(f, FX_PART + 12); return 0;
}
static inline void fx_unlock(void *context)
{
    OwnerFixture *f = context; CHECK(f->locked && !f->owner->locked);
    const uint32_t up = fx_get(f, FX_PART + 12);
    if (up != f->lock_up) {
        CHECK(!f->running && f->owner->phase == K60OwnerClaimed);
        uint32_t at = f->lock_up;
        while (at < up) {
            const uint32_t tag = fx_get(f, FX_PART + at), n = fx_get(f, FX_PART + at + 4);
            CHECK((tag & 65535u) == 0xa5a5u);
            CHECK((tag >> 16) == 478u + f->allocations);
            CHECK(n == (f->allocations ? 4096u : 32u));
            CHECK(fx_zero(fx_bytes(f) + FX_PART + at + 16, n));
            ++f->allocations; at += 16 + n;
        }
        CHECK(at == up && f->allocations <= 3);
    }
    CHECK(!memcmp(fx_bytes(f) + f->remote_offset, f->remote_before, 36));
    f->locked = 0; ++f->unlock_calls;
}
static inline int fx_init(void *context, const uint8_t *metadata, size_t n)
{
    OwnerFixture *f = context; fx_outside(f); ++f->init_calls;
    CHECK(n == FX_MDT_BYTES && metadata == f->metadata);
    CHECK(!memcmp(metadata, f->mdt, FX_MDT_BYTES)); CHECK(f->init_calls == 1);
    fx_trace(f->pas_trace, &f->pas_used, 'I'); return f->init_rc;
}
static inline int fx_mem(void *context, uint64_t base, uint64_t span)
{
    OwnerFixture *f = context; fx_outside(f); ++f->mem_calls;
    CHECK(base == f->config.adsp_base && span == 4096);
    fx_trace(f->pas_trace, &f->pas_used, 'M'); return f->mem_rc;
}
static inline int fx_load(void *context, uint64_t dest, const uint8_t *payload, uint32_t copy, uint32_t zero)
{
    OwnerFixture *f = context; fx_outside(f); ++f->load_calls;
    CHECK(!f->running && dest == f->config.adsp_base && payload == f->payload); CHECK(copy == 8 && zero == 16);
    fx_trace(f->pas_trace, &f->pas_used, 'C'); if (f->load_rc) return f->load_rc;
    memcpy(f->loaded, payload, copy); memset(f->loaded + copy, 0, zero);
    fx_trace(f->pas_trace, &f->pas_used, 'Z'); return 0;
}
static inline int fx_auth(void *context)
{
    OwnerFixture *f = context; fx_outside(f); ++f->auth_calls; CHECK(!strcmp(f->pas_trace, "IMCZ"));
    fx_trace(f->pas_trace, &f->pas_used, 'A'); f->running = 1;
    if (f->lose_live_after_auth) f->live_value = 0;
    return f->auth_rc;
}
static inline int fx_shutdown(void *context)
{
    OwnerFixture *f = context; fx_outside(f); ++f->shutdown_calls;
    fx_trace(f->cleanup, &f->cleanup_used, 'S');
    if (!f->shutdown_rc && f->stop_after_shutdown) f->running = 0;
    return f->shutdown_rc;
}
static inline int fx_ready(void *context, const K60BatteryConfig *c, const K60Smem *smem,
                           uint32_t *n, uint32_t *restart)
{
    OwnerFixture *f = context; fx_outside(f); ++f->ready_calls;
    CHECK(c == &f->owner->config && smem == &f->owner->smem && f->running);
    if (f->remote_not_ready) fx_put(f, f->remote_offset + 36, 0);
    *n = f->ready_bytes; *restart = f->ready_restart; return f->ready_rc;
}
static inline void fx_report(void *context, unsigned stage, int rc)
{
    OwnerFixture *f = context; fx_outside(f); CHECK(stage >= 1 && stage <= 5);
    ++f->reports[stage]; f->report_stage = stage; f->report_rc = rc;
}
static inline int fx_root(void *context)
{ OwnerFixture *f = context; fx_outside(f); ++f->root_calls; return f->root_value; }
static inline int fx_exists(void *context)
{ OwnerFixture *f = context; fx_outside(f); ++f->exists_calls; return f->exists_value; }
static inline int fx_commit(void *context, const uint8_t *blob, size_t n)
{
    OwnerFixture *f = context; K60AdspGlinkHandoff parsed; fx_outside(f); ++f->commit_calls;
    CHECK(n == K60_HANDOFF_BYTES); CHECK(!k60_adsp_handoff_parse(blob, n, &f->config, &parsed));
    CHECK(parsed.epoch == f->epoch && parsed.flags == 15u && f->running);
    if (f->commit_reenter == 1) {
        k60_owner_abort(f->owner);
        CHECK(k60_owner_publish(f->owner, &f->publish, f) == K60_ADSP_OWNER_UNAVAILABLE);
        CHECK(f->owner->phase == K60OwnerBuilt && f->owner->operation_busy);
        CHECK(!f->shutdown_calls && !f->release_calls);
    } else if (f->commit_reenter == 2) {
        k60_adsp_owner_abort(&f->wrapper_lease);
        CHECK(k60_adsp_owner_publish(&f->wrapper_lease, &f->publish, f) == K60_ADSP_OWNER_UNAVAILABLE);
        CHECK(k60_adsp_owner_revalidate(&f->wrapper_lease) == K60_ADSP_OWNER_UNAVAILABLE);
        CHECK(!f->shutdown_calls && !f->release_calls);
    }
    if (f->commit_rc) return f->commit_rc;
    CHECK(!f->exists_value); memcpy(f->property, blob, n); ++f->property_writes; return 0;
}
static inline void fx_case(OwnerFixture *f, const char *name)
{
    memset(f, 0, sizeof *f); f->owner = &f->session; fx_name = name; ++fx_cases;
    f->config = (K60BatteryConfig){UINT64_C(0x80900000), FX_SMEM_BYTES, 0xed18000u, 0x1f4100cu,
        UINT64_C(0x9fd00000), 0x3100000u, 2, 3, 0, 478, 479, 480, 443, 1, 0};
    f->epoch = 0x13579bdfu; f->available_value = f->live_value = f->stop_after_shutdown = 1;
    f->ready_bytes = 40; f->ready_restart = 1; f->root_value = 1;
    f->ops = (K60OwnerOps){K60_OWNER_OPS_VERSION, sizeof(K60OwnerOps), fx_available, fx_reader, fx_close,
        fx_exclusive, fx_release, fx_resources, fx_resources_release, fx_stopped, fx_live, fx_map, fx_unmap,
        fx_lock, fx_unlock, fx_init, fx_mem, fx_load, fx_auth, fx_shutdown, fx_ready, fx_report};
    f->publish = (K60OwnerPublishOps){fx_root, fx_exists, fx_commit};
    f->plan = (K60HandoffPlan){15, f->epoch, f->config.smem_base, FX_SMEM_BYTES,
        f->config.adsp_base, 0x3100000u, 478, 479, 480, 443, 2, 32, 4096, 4096, 40, 0, 0, 1};
    /* ELF32LE ET_EXEC/Hexagon: PT_NULL prefix + hash + relocatable PT_LOAD. */
    uint8_t *m = f->mdt;
    m[0] = 0x7f; m[1] = 'E'; m[2] = 'L'; m[3] = 'F'; m[4] = m[5] = m[6] = 1;
    fx_le16(m + 16, 2); fx_le16(m + 18, 164); fx_le32(m + 20, 1); fx_le32(m + 28, 52);
    fx_le16(m + 40, 52); fx_le16(m + 42, 32); fx_le16(m + 44, 3);
    fx_le32(m + 52 + 16, FX_PREFIX);
    fx_le32(m + 84 + 4, 0x2000); fx_le32(m + 84 + 16, FX_HASH);
    fx_le32(m + 84 + 20, FX_HASH); fx_le32(m + 84 + 24, K60_ADSP_MDT_HASH);
    fx_le32(m + 116, 1); fx_le32(m + 116 + 4, 0x1000);
    fx_le32(m + 116 + 8, 0x100000); fx_le32(m + 116 + 12, 0x100000);
    fx_le32(m + 116 + 16, 8); fx_le32(m + 116 + 20, 24);
    fx_le32(m + 116 + 24, K60_ADSP_MDT_RELOCATABLE | 5); fx_le32(m + 116 + 28, 4096);
    for (unsigned i = 0; i < FX_HASH; ++i) m[FX_PREFIX + i] = (uint8_t)(0xa0u + i);
    for (unsigned i = 0; i < sizeof f->payload; ++i) f->payload[i] = (uint8_t)(0x40u + i);
    memset(f->metadata, 0xee, sizeof f->metadata); memset(f->loaded, 0xcc, sizeof f->loaded);
    const uint32_t toc = FX_SMEM_BYTES - 4096;
    fx_put(f, toc, 0x434f5424u); fx_put(f, toc + 4, 1); fx_put(f, toc + 8, 1);
    fx_put(f, toc + 32, FX_PART); fx_put(f, toc + 36, FX_PART_BYTES);
    fx_put(f, toc + 44, 2u << 16); fx_put(f, toc + 48, 8);
    fx_put(f, FX_PART, 0x54525024u); fx_put(f, FX_PART + 4, 2u << 16);
    fx_put(f, FX_PART + 8, FX_PART_BYTES); fx_put(f, FX_PART + 12, 32);
    fx_put(f, FX_PART + 16, FX_PART_BYTES);
    K60Smem smem = {fx_bytes(f), FX_SMEM_BYTES}; K60SmemPartition part; uint32_t n;
    CHECK(!k60_smem_partition(&smem, 0, 2, &part));
    /* Only the remote fixture creates item 443, before the owner starts. */
    CHECK(!k60_smem_alloc(&smem, &part, 443, 40, &f->remote_offset, &n) && n == 40);
    fx_put(f, f->remote_offset, 0x504d5324u); fx_put(f, f->remote_offset + 4, 1);
    fx_put(f, f->remote_offset + 8, 2); fx_put(f, f->remote_offset + 12, 0x10001);
    fx_put(f, f->remote_offset + 16, 1); memcpy(fx_bytes(f) + f->remote_offset + 20, "slave-kernel", 13);
    fx_put(f, f->remote_offset + 36, 2);
    memcpy(f->remote_before, fx_bytes(f) + f->remote_offset, 40); f->baseline_up = fx_get(f, FX_PART + 12);
}
static inline void fx_claim(OwnerFixture *f)
{ CHECK(!k60_owner_claim(&f->session, &f->config, &f->ops, f)); }
static inline void fx_prepare(OwnerFixture *f)
{ fx_claim(f); CHECK(!k60_owner_prepare_pas1(&f->session)); }
static inline void fx_start(OwnerFixture *f)
{ fx_prepare(f); CHECK(!k60_owner_auth_and_start(&f->session)); }
static inline void fx_build(OwnerFixture *f)
{ fx_start(f); CHECK(!k60_owner_build_handoff(&f->session, &f->plan)); }
static inline uint32_t fx_item(OwnerFixture *f, uint16_t id, uint32_t *n)
{
    K60Smem smem = {fx_bytes(f), FX_SMEM_BYTES}; K60SmemPartition part; uint32_t at = 0;
    CHECK(!k60_smem_partition(&smem, 0, 2, &part)); CHECK(!k60_smem_find(&smem, &part, id, &at, n)); return at;
}
static inline int fx_done(const char *stage)
{ printf("TESTS OK owner-%s: %u scenarios\n", stage, fx_cases); return 0; }
#endif
