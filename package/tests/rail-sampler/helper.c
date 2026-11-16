/* Canonical-C contract probes, not a replacement sampler. Synthetic memory only.
 * MODE distinguishes current-behavior reproduction from compliance assertions.
 * Field offsets below are independent fixed-source fixtures, not a second scanner.
 */
#include "K60PmicRail.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint32_t words[K60_RSC_BYTES / 4u], before[K60_RSC_BYTES / 4u];
static uint8_t db[512], db_before[512];
static const uint32_t resource = 0x30010u;
static const char *cases[] = {
    "v2-fields", "v3-fields", "v2-command0-control", "v3-command0-control",
    "slot7-command15", "v2-command1", "v3-command1", "disabled-command",
    "zero-msgid-status", "whole-value-status2", "duplicate-contradictory",
    "duplicate-first-zero", "truncated-vs-unmatched", "zero-resource",
    "db-bad-magic", "db-head-count-overrun", "db-aux-overrun", "db-short-header"
};

static void put16(uint8_t *p, unsigned v)
{ p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *p, uint32_t v)
{ put16(p, v); put16(p + 2, v >> 16); }

/* Fixed v2.7/v3.0 register facts from the design source table. */
static void seed(unsigned version, unsigned slot, unsigned command,
    uint32_t level, uint32_t status, uint32_t enabled, uint32_t msgid,
    uint32_t cmd_status)
{
    const size_t b = 0xd00u + (size_t)slot * 672u;
    const size_t c = b + (size_t)command * (version == 2 ? 20u : 24u);
    words[(b + (version == 2 ? 0x18u : 0x28u)) / 4u] = status;
    words[(b + (version == 2 ? 0x1cu : 0x2cu)) / 4u] = enabled;
    words[(c + (version == 2 ? 0x30u : 0x34u)) / 4u] = msgid;
    words[(c + (version == 2 ? 0x34u : 0x38u)) / 4u] = resource;
    words[(c + (version == 2 ? 0x38u : 0x3cu)) / 4u] = level;
    words[(c + (version == 2 ? 0x3cu : 0x40u)) / 4u] = cmd_status;
}

static int fields(const K60RscLayout *l, unsigned version)
{
    return l->tcs_stride == 672u && l->cmd_stride == (version == 2 ? 20u : 24u) &&
        l->status == (version == 2 ? 0x18u : 0x28u) &&
        l->cmd_enable == (version == 2 ? 0x1cu : 0x2cu) &&
        l->cmd_msgid == (version == 2 ? 0x30u : 0x34u) &&
        l->cmd_addr == (version == 2 ? 0x34u : 0x38u) &&
        l->cmd_data == (version == 2 ? 0x38u : 0x3cu);
}

static void make_db(void)
{
    memset(db, 0, sizeof db);
    put32(db, 1); put32(db + 4, K60_CMD_DB_MAGIC);
    put16(db + 8, 2); put16(db + 12, 24); put16(db + 14, 1);
    memcpy(db + 144, "lcx.lvl", 7); put32(db + 160, resource);
    put16(db + 164, 4); put16(db + 166, 0);
    put16(db + 168, 0); put16(db + 170, 16);
}

static int run(const char *name, int compliance)
{
    K60RscLayout layout = k60_rsc_layout(0x20700u);
    K60RailRecord r = {0};
    int observed = 0, meets = 0, rc = 0;
    const char *contract = "";
    memset(words, 0, sizeof words);
    memset(db, 0, sizeof db);
    if (!strcmp(name, "v2-fields") || !strcmp(name, "v3-fields")) {
        unsigned v = !strcmp(name, "v2-fields") ? 2u : 3u;
        layout = k60_rsc_layout(v == 2 ? 0x20700u : 0x30000u);
        observed = meets = fields(&layout, v);
        contract = "known-version offsets (not a CMD_STATUS API or power test)";
    } else if (!strncmp(name, "db-", 3)) {
        K60RpmhResource res;
        size_t length = sizeof db;
        int expected = K60RpmhCorrupt;
        make_db();
        if (!strcmp(name, "db-bad-magic")) {
            put32(db + 4, 0); expected = K60RpmhNoDb;
        } else if (!strcmp(name, "db-head-count-overrun")) {
            put16(db + 14, 0xffffu);
        } else if (!strcmp(name, "db-aux-overrun")) {
            put16(db + 166, 0xffffu);
        } else if (!strcmp(name, "db-short-header")) {
            length = 143; expected = K60RpmhNoDb;
        } else return 2;
        memcpy(db_before, db, sizeof db);
        rc = k60_cmd_db_find(db, length, "lcx.lvl", &res);
        observed = meets = rc == expected && !memcmp(db, db_before, sizeof db);
        contract = "bounded canonical cmd-db rejection; no diagnostic walk exercised";
    } else {
        size_t bytes = sizeof words;
        uint32_t id = resource;
        int expected_rc = K60RpmhOk;
        unsigned expected_complete = 1, expected_valid = 1, expected_slot = 0;
        if (!strcmp(name, "v2-command0-control") || !strcmp(name, "v3-command0-control")) {
            unsigned v = !strcmp(name, "v2-command0-control") ? 2u : 3u;
            layout = k60_rsc_layout(v == 2 ? 0x20700u : 0x30000u);
            seed(v, 0, 0, 16, 1, 1, 0x10108u, 0x10100u);
            contract = "synthetic command0 branch control; no power inference";
        } else if (!strcmp(name, "slot7-command15")) {
            seed(2, 7, 15, 16, 1, 1u << 15, 0x10108u, 0x10100u);
            expected_rc = K60RpmhMissing; expected_complete = expected_valid = 0;
            contract = "collect permitted synthetic slot7+command15, not authorize physical range";
        } else if (!strcmp(name, "v2-command1") || !strcmp(name, "v3-command1")) {
            unsigned v = !strcmp(name, "v2-command1") ? 2u : 3u;
            layout = k60_rsc_layout(v == 2 ? 0x20700u : 0x30000u);
            seed(v, 0, 1, 16, 1, 2, 0x10108u, 0x10100u);
            expected_rc = K60RpmhMissing; expected_complete = expected_valid = 0;
            contract = "collect nonzero command index (current record has no command-index field)";
        } else if (!strcmp(name, "disabled-command")) {
            seed(2, 0, 0, 16, 1, 0, 0x10108u, 0x10100u);
            contract = "disabled residual remains raw observation, not valid enabled request";
        } else if (!strcmp(name, "zero-msgid-status")) {
            seed(2, 0, 0, 16, 1, 1, 0, 0);
            contract = "zero format/state cannot be called valid issued request";
        } else if (!strcmp(name, "whole-value-status2")) {
            seed(2, 0, 0, 16, 2, 1, 0x10108u, 0x10100u);
            expected_valid = 0;
            contract = "whole nonzero TCS_STATUS, not bit0 predicate; synthetic value only";
        } else if (!strcmp(name, "duplicate-contradictory")) {
            seed(2, 0, 0, 16, 1, 1, 0x10108u, 0x10100u);
            seed(2, 1, 0, 8, 1, 1, 0x10108u, 0x10100u);
            contract = "preserve both matches and report conflict, not silently succeed on first";
        } else if (!strcmp(name, "duplicate-first-zero")) {
            seed(2, 0, 0, 0, 1, 1, 0x10108u, 0x10100u);
            seed(2, 1, 0, 16, 1, 1, 0x10108u, 0x10100u);
            expected_valid = 0;
            contract = "first zero cannot mask contradictory later request";
        } else if (!strcmp(name, "truncated-vs-unmatched")) {
            seed(2, 4, 0, 16, 1, 1, 0x10108u, 0x10100u);
            bytes = 0xd00u + 2u * 672u;
            expected_rc = K60RpmhMissing; expected_complete = expected_valid = 0;
            contract = "coverage-incomplete error distinct from fully-scanned unmatched";
        } else if (!strcmp(name, "zero-resource")) {
            id = 0; expected_rc = K60RpmhMissing; expected_complete = expected_valid = 0;
            contract = "reject absent resource id";
        } else return 2;
        memcpy(before, words, sizeof words);
        rc = k60_rail_measure(words, bytes, &layout, id, &r);
        observed = rc == expected_rc && r.complete == expected_complete &&
            r.valid == expected_valid && r.tcs_slot == expected_slot &&
            !memcmp(words, before, sizeof words);
        if (!strcmp(name, "slot7-command15"))
            meets = rc == K60RpmhOk && r.complete && r.tcs_slot == 7;
        else if (!strcmp(name, "v2-command1") || !strcmp(name, "v3-command1"))
            meets = rc == K60RpmhOk && r.complete && r.level == 16;
        else if (!strcmp(name, "disabled-command") || !strcmp(name, "zero-msgid-status"))
            meets = r.complete && !r.valid;
        else if (!strcmp(name, "whole-value-status2"))
            meets = r.complete && r.valid;
        else if (!strncmp(name, "duplicate-", 10))
            meets = rc != K60RpmhOk && rc != K60RpmhMissing;
        else if (!strcmp(name, "truncated-vs-unmatched")) {
            uint32_t empty[K60_RSC_BYTES / 4u] = {0};
            K60RailRecord unmatched;
            int no_match = k60_rail_measure(empty, sizeof empty, &layout, id, &unmatched);
            meets = rc != no_match && !r.complete;
        } else meets = observed;
        meets = meets && !memcmp(words, before, sizeof words);
    }
    printf("%s case=%s %s rc=%d complete=%u valid=%u slot=%u arc_index=%u contract=%s\n",
        compliance ? "COMPLIANCE" : "REPRODUCED_CURRENT_BEHAVIOR", name,
        (compliance ? meets : observed) ? "PASS" : "FAIL", rc, r.complete, r.valid,
        r.tcs_slot, r.level, contract);
    if (!compliance)
        printf("classification=reproduced-current-behavior compliance=%s no_physical_mmio=1\n",
            meets ? "case-only-not-full-certification" : "FAIL");
    return (compliance ? meets : observed) ? 0 : 1;
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--list")) {
        for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) puts(cases[i]);
        return 0;
    }
    if (argc != 3 || (strcmp(argv[1], "reproduced-current-behavior") &&
        strcmp(argv[1], "compliance"))) return 2;
    return run(argv[2], !strcmp(argv[1], "compliance"));
}
