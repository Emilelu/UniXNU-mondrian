/*
 * Canonical K60PmicRail.c KERNEL=1 host contract tests. Link the C file as a
 * separate translation unit: no source inclusion, replacement sampler, PAS,
 * SCM, physical mapping, or real MMIO. All mapped bytes belong to these arrays.
 *
 * CLI: entry --list
 *      entry reproduced-current-behavior CASE
 *      entry compliance CASE
 * One CASE per exec is mandatory: canonical static state is never reset here.
 * A reproduction exit 0 means only that the old behavior was reproduced.
 * Compliance assertions are ordinary failures (exit 1), NOT xfail/XPASS masks.
 *
 * The original ten scenarios extend the artifact-only entry audit cited in
 * docs/research/audio/ADSP-RAIL-SAMPLER-AUDIT.md. New fixtures are independently
 * written from that audit's register facts (v2/v3, not an imported driver).
 *
 * LIMITATIONS: parser events test PE_parse_boot_argn's return/output contract,
 * not the real parser's textual grammar. k60_data_mounted is a synthetic input
 * ignored by current canonical C. Maps have no returned-length parameter: a
 * truncated window is safely tested via the public measure helper, never by
 * returning an undersized allocation to an entry that assumes a full mapping.
 * No volatile-load instrumentation; only actual stub calls are counted. The
 * legacy record has no command index, coverage/error taxonomy, attempt state,
 * recorder provenance, or power-evidence type. These tests cannot prove those
 * missing interfaces, map lifetime/unmapping, hardware atomicity, or power.
 */
#include <limits.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <errno.h>
#include "K60PmicRail.h"
#include <machine/machine_routines.h>

static uint8_t db[K60_CMD_DB_BYTES], db_before[K60_CMD_DB_BYTES];
static uint32_t rsc[K60_RSC_BYTES / 4u], rsc_before[K60_RSC_BYTES / 4u];
static atomic_uint db_maps, drv_maps, parses, event_no, failures;
static int arg_present, arg_value, arg_writes = 1, fail_db, fail_drv;
static int compliance;
/* Only this fixture exports it; the current source does not check this input. */
int k60_data_mounted;

static pthread_mutex_t hold_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t hold_cv = PTHREAD_COND_INITIALIZER;
static int hold_first_map, first_map_entered, release_first_map;
static int reenter, inner_rc = INT_MIN;

#define CHECK(x) do { if (!(x)) { \
    printf("ASSERT_FAIL mode=%s line=%d expr=%s\n", \
        compliance ? "COMPLIANCE" : "REPRODUCED_CURRENT_BEHAVIOR", \
        __LINE__, #x); atomic_fetch_add(&failures, 1); \
} } while (0)
#define CURRENT(x) do { if (!compliance) CHECK(x); } while (0)
#define CONTRACT(x) do { if (compliance) CHECK(x); } while (0)

static void put16(uint8_t *p, unsigned x)
{
    p[0] = (uint8_t)x; p[1] = (uint8_t)(x >> 8);
}
static void put32(uint8_t *p, uint32_t x)
{
    put16(p, x); put16(p + 2, x >> 16);
}
static unsigned events(void) { return atomic_fetch_add(&event_no, 1) + 1; }
static unsigned dm(void) { return atomic_load(&db_maps); }
static unsigned rm(void) { return atomic_load(&drv_maps); }
static unsigned pc(void) { return atomic_load(&parses); }

/* Explicit offsets are fixture facts, not a fake implementation under test. */
static void command(unsigned slot, unsigned cmd, uint32_t address,
    uint32_t data, unsigned enabled, uint32_t msgid, uint32_t cmd_status,
    uint32_t tcs_status)
{
    unsigned v3 = ((rsc[0] >> 16) & 0xffu) == 3;
    size_t base = K60_RSC_TCS_OFFSET + slot * 672u;
    size_t stride = v3 ? 24u : 20u;
    size_t en = base + (v3 ? 0x2cu : 0x1cu);
    size_t msg = base + (v3 ? 0x34u : 0x30u) + cmd * stride;
    CHECK(slot < 8 && cmd < 16 && msg + 16 < sizeof rsc);
    if (enabled) rsc[en / 4] |= 1u << cmd;
    else rsc[en / 4] &= ~(1u << cmd);
    rsc[(base + (v3 ? 0x28u : 0x18u)) / 4] = tcs_status;
    rsc[msg / 4] = msgid;
    rsc[(msg + 4) / 4] = address;
    rsc[(msg + 8) / 4] = data;
    rsc[(msg + 12) / 4] = cmd_status;
}
static void rails(uint32_t version, unsigned cmd)
{
    memset(rsc, 0, sizeof rsc);
    rsc[0] = version;
    /* Historical caps arithmetic: max_tcs=8 (shift12), ncpt=16 (shift27).
     * Synthetic coverage only: does NOT authorize these addresses on hardware. */
    rsc[0x0c / 4] = 0x800c8104u;
    command(3, cmd, 0x30010, 16, 1, 0x10108, 0x10100, 1);
    command(4, cmd, 0x31000, 8, 1, 0x10108, 0x10100, 1);
}
static void fixture(void)
{
    memset(db, 0, sizeof db);
    put32(db, 1); put32(db + 4, K60_CMD_DB_MAGIC);
    put16(db + 8, 2); put16(db + 10, 0); put16(db + 12, 48);
    put16(db + 14, 2);
    memcpy(db + 144, "lcx.lvl", 7); put32(db + 160, 0x30010);
    memcpy(db + 168, "lmx.lvl", 7); put32(db + 184, 0x31000);
    rails(0x20700, 0);
}
static void freeze_bytes(void)
{
    memcpy(db_before, db, sizeof db); memcpy(rsc_before, rsc, sizeof rsc);
}
static void unchanged_bytes(void)
{
    CHECK(memcmp(db_before, db, sizeof db) == 0);
    CHECK(memcmp(rsc_before, rsc, sizeof rsc) == 0);
}
static void eligible(void)
{
    k60_data_mounted = 1; arg_present = arg_value = 1;
}

int PE_parse_boot_argn(const char *name, void *out, int bytes)
{
    unsigned n = atomic_fetch_add(&parses, 1) + 1;
    CHECK(strcmp(name, "pong_rail_probe") == 0);
    CHECK(bytes == (int)sizeof(int)); CHECK(out != NULL);
    if (arg_writes && out != NULL && bytes == (int)sizeof(int))
        memcpy(out, &arg_value, sizeof arg_value);
    printf("EVENT %u parser call=%u returns=%d writes=%d value=%d\n",
        events(), n, arg_present, arg_writes, arg_value);
    return arg_present;
}

vm_offset_t ml_io_map_unmappable(vm_offset_t physical, vm_size_t bytes,
    unsigned int flags)
{
    unsigned n;
    int is_db = physical == (vm_offset_t)K60_CMD_DB_PHYS;
    CHECK(flags == 0x7u);
    if (is_db) {
        CHECK(bytes == K60_CMD_DB_BYTES);
        n = atomic_fetch_add(&db_maps, 1) + 1;
    } else {
        CHECK(physical == (vm_offset_t)K60_RSC_DRV2_PHYS);
        CHECK(bytes == K60_RSC_BYTES);
        n = atomic_fetch_add(&drv_maps, 1) + 1;
    }
    printf("EVENT %u map=%s call=%u size=%zu flags=%#x result=%s\n",
        events(), is_db ? "db" : "drv2", n, (size_t)bytes, flags,
        (is_db ? fail_db : fail_drv) ? "FAIL" : "SYNTHETIC");
    if (is_db && n == 1 && hold_first_map) {
        CHECK(pthread_mutex_lock(&hold_lock) == 0);
        first_map_entered = 1;
        CHECK(pthread_cond_broadcast(&hold_cv) == 0);
        while (!release_first_map)
            CHECK(pthread_cond_wait(&hold_cv, &hold_lock) == 0);
        CHECK(pthread_mutex_unlock(&hold_lock) == 0);
    }
    if (is_db && n == 1 && reenter) {
        printf("EVENT %u reenter=%s inside first failing map\n", events(),
            reenter == 1 ? "inherit" : "probe");
        inner_rc = reenter == 1 ? k60_rail_inherit() : k60_rail_probe();
    }
    if (is_db) return fail_db ? 0 : (vm_offset_t)db;
    return fail_drv ? 0 : (vm_offset_t)rsc;
}
static int invoke(int probe)
{
    int rc;
    printf("EVENT %u call=%s data=%d parser_returns=%d parser_value=%d\n",
        events(), probe ? "probe" : "inherit", k60_data_mounted,
        arg_present, arg_value);
    rc = probe ? k60_rail_probe() : k60_rail_inherit();
    printf("EVENT %u return=%s rc=%d\n", events(), probe ? "probe" : "inherit", rc);
    return rc;
}
static const K60RailLedger *ledger(void)
{
    const K60RailLedger *l = k60_rail_ledger();
    CHECK(l != NULL); return l;
}
static void seed(void)
{
    K60RailRecord a = {0x30010, 0x30010, 16, 3, 1, 1, NULL, NULL};
    K60RailRecord b = {0x31000, 0x31000, 8, 4, 1, 1, NULL, NULL};
    k60_rail_ledger_store(0x20700, &a, &b);
    printf("EVENT %u seed=public-ledger-store synthetic-not-provenance\n", events());
}
static void counts(unsigned d, unsigned r, unsigned p)
{
    CURRENT(dm() == d); CURRENT(rm() == r); CURRENT(pc() == p);
}
static void no_maps(void) { CONTRACT(dm() == 0 && rm() == 0); }
static void no_remap(unsigned d, unsigned r)
{
    CONTRACT(dm() == d && rm() == r);
}
static int *thread_entry_result;
static void *thread_entry(void *unused)
{
    (void)unused;
    *thread_entry_result = invoke(0);
    return NULL;
}
static void concurrent_case(int drv_failure, int other_probe)
{
    pthread_t thread;
    int winner = INT_MIN, contender, create_rc, wait_rc = 0;
    struct timespec until;
    eligible(); fail_db = !drv_failure; fail_drv = drv_failure;
    hold_first_map = 1; thread_entry_result = &winner;
    create_rc = pthread_create(&thread, NULL, thread_entry, NULL);
    CHECK(create_rc == 0);
    if (create_rc != 0) return;
    CHECK(timespec_get(&until, TIME_UTC) == TIME_UTC); until.tv_sec += 5;
    CHECK(pthread_mutex_lock(&hold_lock) == 0);
    while (!first_map_entered && wait_rc == 0)
        wait_rc = pthread_cond_timedwait(&hold_cv, &hold_lock, &until);
    CHECK(first_map_entered && wait_rc == 0);
    CHECK(pthread_mutex_unlock(&hold_lock) == 0);
    /* Winner cannot finish while this synchronous contender runs. Both maps
     * fail before rail_record_pass, so canonical static ledger is only read.
     * All mutable stub counters are atomic; handshakes are mutex-protected.
     * There is no unsafe successful parallel ledger_store or busy-loop. */
    contender = invoke(other_probe);
    CHECK(pthread_mutex_lock(&hold_lock) == 0);
    release_first_map = 1;
    CHECK(pthread_cond_broadcast(&hold_cv) == 0);
    CHECK(pthread_mutex_unlock(&hold_lock) == 0);
    CHECK(pthread_join(thread, NULL) == 0);
    CHECK(winner < 0 && contender < 0); CHECK(k60_rail_ledger() == NULL);
    counts(2, drv_failure ? 2u : 0u, other_probe ? 1u : 2u);
    CONTRACT(dm() == 1 && rm() == (unsigned)drv_failure);
    printf("OBSERVED concurrency winner=%d contender=%d overlap=first-map-held ledger_writes=none\n",
        winner, contender);
}
static int equal_text(const char *a, const char *b)
{
    return a == b || (a && b && strcmp(a, b) == 0);
}
static int same_record(const K60RailRecord *a, const K60RailRecord *b)
{
    return a->resource_id == b->resource_id && a->address == b->address &&
        a->level == b->level && a->tcs_slot == b->tcs_slot &&
        a->complete == b->complete && a->valid == b->valid &&
        equal_text(a->missing, b->missing) && equal_text(a->why, b->why);
}

/* expected_compliance is metadata only; it never changes assertion outcomes.
 * PASS below means a narrow control, never overall sampler compliance/power. */
static const struct { const char *name; const char *expected_compliance; } cases[] = {
    {"inherit-db-failure-twice", "FAIL"},
    {"inherit-drv-failure-twice", "FAIL"},
    {"inherit-failure-then-probe", "FAIL"},
    {"seeded-ledger-probe-remaps", "FAIL"},
    {"direct-probe-data0-argoff", "FAIL"},
    {"cached-inherit-data0-argoff", "FAIL"},
    {"inherit-data0-arg1", "FAIL"},
    {"inherit-data1-arg2", "FAIL"},
    {"inherit-off-negative-control", "PASS"},
    {"inherit-success-then-probe", "FAIL"},
    {"cache-only-after-db-failure-inherit", "FAIL"},
    {"cache-only-after-db-failure-probe", "FAIL"},
    {"cache-only-after-drv-failure-inherit", "FAIL"},
    {"cache-only-after-drv-failure-probe", "FAIL"},
    {"concurrent-db-failure-inherit", "FAIL"},
    {"concurrent-db-failure-probe", "FAIL"},
    {"concurrent-drv-failure-probe", "FAIL"},
    {"reentrant-db-failure-inherit", "FAIL"},
    {"reentrant-db-failure-probe", "FAIL"},
    {"parse-false-writes-one", "PASS"},
    {"parse-absent-no-output", "PASS"},
    {"parse-true-zero", "PASS"},
    {"parse-true-negative", "FAIL"},
    {"parse-true-int-min", "FAIL"},
    {"data-two", "FAIL"},
    {"data0-then-data1", "FAIL"},
    {"direct-probe-argoff", "FAIL"},
    {"cached-inherit-data0", "FAIL"},
    {"cached-inherit-argoff", "FAIL"},
    {"cached-probe-data0", "FAIL"},
    {"cached-probe-argoff", "FAIL"},
    {"corrupt-cache-magic-inherit", "FAIL"},
    {"corrupt-cache-magic-probe", "FAIL"},
    {"corrupt-cache-recorded", "FAIL"},
    {"corrupt-cache-gate", "FAIL"},
    {"corrupt-cache-address", "FAIL"},
    {"v2-command0-control", "FAIL"},
    {"v3-command0-control", "FAIL"},
    {"v2-command1", "FAIL"},
    {"v3-command1", "FAIL"},
    {"slot5-only", "FAIL"},
    {"disabled-command", "FAIL"},
    {"zero-msgid", "FAIL"},
    {"zero-command-status", "FAIL"},
    {"zero-msgid-and-status", "FAIL"},
    {"issued-not-complete", "FAIL"},
    {"tcs-status-two", "FAIL"},
    {"tcs-status-zero-control", "PASS"},
    {"duplicate-contradictory", "FAIL"},
    {"multi-command-contradictory", "FAIL"},
    {"duplicate-zero-first", "FAIL"},
    {"truncated-measure-window", "FAIL"},
    {"db-bad-magic", "PASS"},
    {"db-aux-out-of-bounds", "PASS"},
    {"db-truncated-header-helper", "PASS"},
    {"unsupported-version", "FAIL"},
    {"request-is-not-power", "FAIL"}
};

static void run_case(const char *s)
{
    int a, b;
    const K60RailLedger *l;
    if (!strcmp(s, "inherit-db-failure-twice") ||
        !strcmp(s, "inherit-drv-failure-twice") ||
        !strcmp(s, "inherit-failure-then-probe")) {
        int drv = !strcmp(s, "inherit-drv-failure-twice");
        int probe = !strcmp(s, "inherit-failure-then-probe");
        eligible(); fail_db = !drv; fail_drv = drv;
        a = invoke(0); b = invoke(probe);
        CHECK(a < 0 && b < 0); CHECK(k60_rail_ledger() == NULL);
        counts(2, drv ? 2u : 0u, probe ? 1u : 2u);
        CONTRACT(dm() == 1 && rm() == (unsigned)drv);
    } else if (!strcmp(s, "seeded-ledger-probe-remaps")) {
        eligible(); seed(); a = invoke(1);
        CURRENT(a == 0); counts(1, 1, 0); no_maps();
    } else if (!strcmp(s, "direct-probe-data0-argoff") ||
        !strcmp(s, "direct-probe-argoff")) {
        k60_data_mounted = !strcmp(s, "direct-probe-argoff");
        a = invoke(1); CURRENT(a == 0); counts(1, 1, 0);
        CONTRACT(a < 0); no_maps();
    } else if (!strcmp(s, "cached-inherit-data0-argoff") ||
        !strcmp(s, "cached-inherit-data0") ||
        !strcmp(s, "cached-inherit-argoff") ||
        !strcmp(s, "cached-probe-data0") ||
        !strcmp(s, "cached-probe-argoff")) {
        int probe = strstr(s, "cached-probe") != NULL;
        eligible(); seed();
        if (strstr(s, "data0")) k60_data_mounted = 0;
        if (strstr(s, "argoff")) arg_present = arg_value = 0;
        a = invoke(probe); CURRENT(a == 0);
        counts(probe ? 1u : 0u, probe ? 1u : 0u, 0);
        CONTRACT(a < 0); no_maps();
    } else if (!strcmp(s, "inherit-data0-arg1") ||
        !strcmp(s, "inherit-data1-arg2") || !strcmp(s, "data-two")) {
        eligible();
        if (!strcmp(s, "inherit-data0-arg1")) k60_data_mounted = 0;
        else if (!strcmp(s, "data-two")) k60_data_mounted = 2;
        else arg_value = 2;
        a = invoke(0); CURRENT(a == 0); counts(1, 1, 1);
        CONTRACT(a < 0); no_maps();
    } else if (!strcmp(s, "inherit-off-negative-control") ||
        !strcmp(s, "parse-false-writes-one") ||
        !strcmp(s, "parse-absent-no-output") ||
        !strcmp(s, "parse-true-zero") ||
        !strcmp(s, "parse-true-negative") ||
        !strcmp(s, "parse-true-int-min")) {
        eligible();
        if (!strcmp(s, "parse-false-writes-one")) arg_present = 0;
        else if (!strcmp(s, "parse-absent-no-output")) {
            arg_present = 0; arg_writes = 0;
        } else if (!strcmp(s, "parse-true-negative")) arg_value = -1;
        else if (!strcmp(s, "parse-true-int-min")) arg_value = INT_MIN;
        else if (!strcmp(s, "parse-true-zero")) arg_value = 0;
        else arg_present = arg_value = 0;
        a = invoke(0);
        if (arg_value < 0) { CURRENT(a == 0); counts(1, 1, 1); }
        else { CHECK(a == K60_RAIL_REFUSED); counts(0, 0, 1); }
        CONTRACT(a < 0); no_maps();
    } else if (!strcmp(s, "data0-then-data1")) {
        eligible(); k60_data_mounted = 0;
        a = invoke(0); CURRENT(a == 0); CONTRACT(a < 0); no_maps();
        k60_data_mounted = 1; b = invoke(0);
        CURRENT(b == 0); counts(1, 1, 1);
        CONTRACT(dm() == 1 && rm() == 1);
    } else if (!strcmp(s, "inherit-success-then-probe")) {
        unsigned d, r;
        eligible(); a = invoke(0); d = dm(); r = rm(); b = invoke(1);
        CURRENT(a == 0 && b == 0); counts(2, 2, 1); no_remap(d, r);
    } else if (!strncmp(s, "cache-only-after-", 17)) {
        int drv = strstr(s, "-drv-") != NULL;
        int probe = strstr(s, "-probe") != NULL;
        unsigned d, r;
        eligible(); fail_db = !drv; fail_drv = drv;
        a = invoke(0); CHECK(a < 0); d = dm(); r = rm();
        /* Only the stub availability changes. No synthetic terminal cache is
         * supplied: the current canonical source must own its failure state. */
        fail_db = fail_drv = 0; b = invoke(probe);
        CURRENT(b == 0); CURRENT(k60_rail_ledger() != NULL);
        counts(2, drv ? 2u : 1u, probe ? 1u : 2u);
        CONTRACT(b < 0); no_remap(d, r);
    } else if (!strncmp(s, "concurrent-", 11)) {
        concurrent_case(strstr(s, "-drv-") != NULL, strstr(s, "-probe") != NULL);
    } else if (!strncmp(s, "reentrant-", 10)) {
        eligible(); fail_db = 1; reenter = strstr(s, "-probe") ? 2 : 1;
        a = invoke(0); CHECK(a < 0 && inner_rc < 0);
        CHECK(k60_rail_ledger() == NULL); counts(2, 0, reenter == 1 ? 2u : 1u);
        CONTRACT(dm() == 1 && rm() == 0);
    } else if (!strncmp(s, "corrupt-cache-", 14)) {
        K60RailLedger *mutable;
        int probe = strstr(s, "-probe") != NULL;
        eligible(); seed(); l = ledger(); if (!l) return;
        /* The underlying object is not const. Deliberate post-store fault
         * injection is sequential, never concurrent; no private symbol access. */
        mutable = (K60RailLedger *)(uintptr_t)l;
        if (strstr(s, "-magic")) mutable->magic ^= 1u;
        else if (strstr(s, "-recorded")) mutable->recorded = 0;
        else if (strstr(s, "-gate")) mutable->gate = 0;
        else mutable->lcx.address ^= 4u;
        a = invoke(probe); CURRENT(a == 0);
        if (strstr(s, "-magic") || strstr(s, "-recorded")) counts(1, 1, probe ? 0u : 1u);
        else counts(0, 0, 0);
        CONTRACT(a < 0); no_maps();
    } else if (!strcmp(s, "truncated-measure-window")) {
        K60RailRecord cut, absent;
        K60RscLayout layout = k60_rsc_layout(0x20700);
        size_t bytes = K60_RSC_TCS_OFFSET + 2u * 672u;
        a = k60_rail_measure(rsc, bytes, &layout, 0x30010, &cut);
        b = k60_rail_measure(rsc, sizeof rsc, &layout, 0x39999, &absent);
        printf("OBSERVED helper=cut bytes=%zu rc=%d absent_rc=%d complete=%u missing=%s\n",
            bytes, a, b, cut.complete, cut.missing ? cut.missing : "none");
        CURRENT(a == K60RpmhMissing && b == K60RpmhMissing);
        CURRENT(cut.complete == 0);
        CONTRACT(a < 0 && a != b); /* coverage failure is not full miss */
        CHECK(dm() == 0 && rm() == 0 && pc() == 0);
        printf("LIMITATION truncated is helper-only; entry map API has no actual-byte-count result\n");
    } else if (!strcmp(s, "duplicate-zero-first")) {
        K60RailRecord single, duplicate;
        K60RscLayout layout = k60_rsc_layout(0x20700);
        command(3, 0, 0, 0, 0, 0, 0, 0);
        command(1, 0, 0x30010, 0, 1, 0x10108, 0x10100, 1);
        freeze_bytes();
        a = k60_rail_measure(rsc, sizeof rsc, &layout, 0x30010, &single);
        unchanged_bytes();
        command(3, 0, 0x30010, 16, 1, 0x10108, 0x10100, 1);
        freeze_bytes();
        b = k60_rail_measure(rsc, sizeof rsc, &layout, 0x30010, &duplicate);
        /* Both results must be compared verbatim, not normalized: the first
         * zero record is identical, but the second input has a conflicting
         * later command. The canonical output loses that distinction. */
        CURRENT(a == 0 && b == 0 && same_record(&single, &duplicate));
        CONTRACT(a != b || !same_record(&single, &duplicate));
        printf("OBSERVED zero-first single_rc=%d duplicate_rc=%d same_record=%d\n",
            a, b, same_record(&single, &duplicate));
        unchanged_bytes(); /* second canonical read must preserve synthetic bytes */
    } else if (!strcmp(s, "db-truncated-header-helper")) {
        K60RpmhResource resource;
        a = k60_cmd_db_find(db, 143, "lcx.lvl", &resource);
        CHECK(a == K60RpmhNoDb); CHECK(dm() == 0 && rm() == 0 && pc() == 0);
    } else {
        int control = !strcmp(s, "v2-command0-control") ||
            !strcmp(s, "v3-command0-control");
        eligible();
        if (!strncmp(s, "v3-", 3)) rails(0x30000, strstr(s, "command1") ? 1u : 0u);
        else if (!strcmp(s, "v2-command1")) rails(0x20700, 1);
        else if (!strcmp(s, "slot5-only")) {
            rails(0x20700, 0); command(3, 0, 0, 0, 0, 0, 0, 0);
            command(5, 0, 0x30010, 16, 1, 0x10108, 0x10100, 1);
        } else if (!strcmp(s, "disabled-command"))
            command(3, 0, 0x30010, 16, 0, 0x10108, 0x10100, 1);
        else if (!strcmp(s, "zero-msgid"))
            command(3, 0, 0x30010, 16, 1, 0, 0x10100, 1);
        else if (!strcmp(s, "zero-command-status"))
            command(3, 0, 0x30010, 16, 1, 0x10108, 0, 1);
        else if (!strcmp(s, "zero-msgid-and-status"))
            command(3, 0, 0x30010, 16, 1, 0, 0, 1);
        else if (!strcmp(s, "issued-not-complete"))
            command(3, 0, 0x30010, 16, 1, 0x10108, 0x100, 1);
        else if (!strcmp(s, "tcs-status-two"))
            command(3, 0, 0x30010, 16, 1, 0x10108, 0x10100, 2);
        else if (!strcmp(s, "tcs-status-zero-control"))
            command(3, 0, 0x30010, 16, 1, 0x10108, 0x10100, 0);
        else if (!strcmp(s, "duplicate-contradictory"))
            command(1, 0, 0x30010, 8, 1, 0x10108, 0x10100, 1);
        else if (!strcmp(s, "multi-command-contradictory"))
            command(3, 1, 0x30010, 8, 1, 0x10108, 0x10100, 1);
        else if (!strcmp(s, "db-bad-magic")) put32(db + 4, 0);
        else if (!strcmp(s, "db-aux-out-of-bounds")) {
            put16(db + 12, 65535); put16(db + 164, 65535);
            put16(db + 166, 65535);
        } else if (!strcmp(s, "unsupported-version")) {
            rails(0x30000, 0); rsc[0] = 0x40000;
        }
        freeze_bytes(); a = invoke(0); l = ledger(); if (!l) return;
        counts(1, 1, 1);
        if (control) {
            CURRENT(a == 0);
            CHECK(l->lcx.complete && l->lcx.valid);
            CHECK(l->lcx.level == 16 && l->lmx.level == 8);
            CONTRACT(a < 0); /* valid request observation must not grant inheritance */
            printf("LIMITATION raw fields remain valid; legacy inherit success is forbidden authority\n");
        } else if (strstr(s, "command1") || !strcmp(s, "slot5-only")) {
            CURRENT(a == K60_RAIL_REFUSED && !l->lcx.complete);
            CONTRACT(a < 0 && l->lcx.complete && l->lcx.address == 0x30010);
            printf("LIMITATION legacy record cannot expose command index or complete scan coverage\n");
        } else if (!strcmp(s, "tcs-status-two")) {
            CURRENT(a == K60_RAIL_REFUSED && !l->lcx.valid);
            CONTRACT(a < 0 && l->lcx.valid); /* whole nonzero idle is not power authority */
        } else if (!strcmp(s, "tcs-status-zero-control") ||
            !strncmp(s, "db-", 3)) {
            CHECK(a == K60_RAIL_REFUSED && !l->lcx.valid);
        } else {
            CURRENT(a == 0 && l->lcx.valid);
            CONTRACT(a < 0); /* refuse power authority without requiring raw observation invalidity */
            printf("LIMITATION legacy valid bit cannot express separate request annotations/power types\n");
        }
        printf("OBSERVED legacy_lcx slot=%u complete=%u valid=%u level=%u missing=%s why=%s\n",
            l->lcx.tcs_slot, l->lcx.complete, l->lcx.valid, l->lcx.level,
            l->lcx.missing ? l->lcx.missing : "none", l->lcx.why ? l->lcx.why : "none");
    }
}
int main(int argc, char **argv)
{
    size_t selected, count = sizeof cases / sizeof cases[0];
    if (argc == 2 && !strcmp(argv[1], "--list")) {
        for (size_t i = 0; i < count; ++i) puts(cases[i].name);
        return 0;
    }
    if (argc != 3 || (strcmp(argv[1], "reproduced-current-behavior") &&
        strcmp(argv[1], "compliance"))) {
        fprintf(stderr, "usage: %s --list | {reproduced-current-behavior|compliance} CASE\n", argv[0]);
        return 2;
    }
    for (selected = 0; selected < count; ++selected)
        if (!strcmp(argv[2], cases[selected].name)) break;
    if (selected == count) { fprintf(stderr, "unknown case: %s\n", argv[2]); return 2; }
    compliance = !strcmp(argv[1], "compliance");
    fixture(); freeze_bytes(); CHECK(k60_rail_ledger() == NULL);
    printf("%s case=%s process_reset=exec expected_current_compliance=%s\n",
        compliance ? "COMPLIANCE" : "REPRODUCED_CURRENT_BEHAVIOR", argv[2],
        cases[selected].expected_compliance);
    printf("LIMITATION actual map/parser stub counts only; NO volatile-load instrumentation; NO PAS/SCM or real MMIO\n");
    run_case(argv[2]); unchanged_bytes();
    printf("RESULT mode=%s case=%s db_maps=%u drv_maps=%u parse_calls=%u ledger=%d failures=%u result=%s authority=none\n",
        compliance ? "COMPLIANCE" : "REPRODUCED_CURRENT_BEHAVIOR", argv[2],
        dm(), rm(), pc(), k60_rail_ledger() != NULL, atomic_load(&failures),
        atomic_load(&failures) ? "FAIL" : compliance ? "PASS_NARROW_CASE_ONLY" :
        "PASS_EXPECTED_CURRENT_BEHAVIOR_NOT_COMPLIANCE");
    return atomic_load(&failures) ? 1 : 0;
}
