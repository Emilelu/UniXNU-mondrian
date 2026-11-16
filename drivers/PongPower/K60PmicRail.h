/*
 * Read the applications RSC's command database and say what the pm8350c_l2
 * rail's RPMh address and level table look like, before anyone votes.
 *
 * Every constant here has a source that can be re-read:
 *   - cmd-db at 0x80860000, 0x20000 bytes  -> /reserved-memory/aop_cmd_db_region@80860000
 *     in Platforms/Xiaomi/mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb
 *   - cmd-db layout (magic 0x0c0330db, 8 slave records, 24-byte entries)
 *     -> UniXNU-sheng/package/QcomRpmh.c qcom_cmd_db_find(), which the
 *     sheng host test pins with a synthetic database.
 *   - apps RSC at 0x17a00000..0x17a30000, tcs-offset 0xd00, drv-id 2
 *     -> /soc/rsc@17a00000 in the same device tree, plus the same reference's
 *     qcom_rsc_layout()/qcom_rpmh_active_request().
 *   - pm8350c_l2 resource name "ldoc2" -> /soc/rsc@17a00000/rpmh-regulator-ldoc2
 *     (qcom,resource-name = "ldoc2"; regulator-min-microvolt 1800000).
 * The pass is single-shot per boot: k60_rail_inherit() (first step of
 * k60_adsp_bring_up(), which only runs after Data mount) measures when no pass
 * has run yet, and k60_rail_probe() only prints a ledger that already exists.
 * No path writes a register and no path polls.
 */
#ifndef K60_PMIC_RAIL_H
#define K60_PMIC_RAIL_H

#include <stddef.h>
#include <stdint.h>

#define K60_CMD_DB_PHYS     0x80860000ULL
#define K60_CMD_DB_BYTES    0x20000u
#define K60_RSC_DRV2_PHYS   0x17a20000ULL
#define K60_RSC_BYTES       0x10000u
#define K60_RSC_TCS_OFFSET  0xd00u
#define K60_CMD_DB_MAGIC    0x0c0330dbu
#define K60_RPMH_MAX_LEVELS 16u
#define K60_RAIL_LDOC2      0x1c6u   /* rpmh-regulator-ldoc2 consumer tag */
/* DRV-2 TCS slots the inheritance scan looks at: 0xd00 + n * tcs_stride. The
 * slot number is never assumed, it is whichever slot carries the rail's
 * cmd-db address (docs/research/audio/ADSP-RAIL-INHERITANCE.md). */
#define K60_RAIL_SLOTS      5u
#define K60_RAIL_LEDGER_MAGIC 0x524c3630u /* 'RL60' */
#define K60_RAIL_GATE_PROBE 1u      /* recorded by k60_rail_probe() */

typedef struct {
	uint32_t address;
	uint16_t levels[K60_RPMH_MAX_LEVELS];
	unsigned level_count;
} K60RpmhResource;

typedef struct {
	uint32_t tcs_stride, cmd_stride, irq_status, irq_clear, wait_for_cmpl;
	uint32_t control, status, cmd_enable, cmd_msgid, cmd_addr, cmd_data;
} K60RscLayout;

/* One rail's inheritance evidence. The four-tuple is all-or-nothing: if any
 * field could not be measured, `complete` stays 0 and `missing` names the field
 * that stopped the read, so a partial measurement can never be read as an
 * inherited rail later. `valid` then says whether the complete measurement is
 * self-consistent: a matched slot can still hold a retired command, so a zero
 * ARC level or a busy slot is measured-but-invalid, not missing. */
typedef struct {
	uint32_t resource_id;   /* cmd-db address of the rail, 0 when not found */
	uint32_t address;       /* cmd_addr read back from the matched slot */
	uint32_t level;         /* cmd_data read back: ARC level index, not mV */
	unsigned tcs_slot;      /* DRV-2 TCS slot whose cmd_addr matched */
	unsigned complete;      /* all four fields measured */
	unsigned valid;         /* complete, nonzero level, slot idle */
	const char *missing;    /* static name of the field that stopped the read */
	const char *why;        /* static reason a complete record is invalid */
} K60RailRecord;

/* What the gated read-only pass leaves for a consumer that runs later: who
 * measured it, what state the RSC was in, and whether each rail completed.
 * A consumer that finds no ledger must say "never measured"; one that finds an
 * incomplete rail must name the field. Those are different failures. */
typedef struct {
	uint32_t magic;
	uint32_t drv_id;        /* DRV-2 id word seen when the pass ran */
	unsigned recorded;      /* 1 once a pass stored this ledger */
	unsigned gate;          /* K60_RAIL_GATE_PROBE */
	K60RailRecord lcx;
	K60RailRecord lmx;
} K60RailLedger;

/* Three-state verdict over a ledger. Pure, so the host test can exercise every
 * branch without hardware. resources() must not call this: it runs before the
 * registers may be read, so its only honest answer is a declaration. */
enum {
	K60RailVerdictInherited = 0,
	K60RailVerdictNotRecorded = 1,
	K60RailVerdictIncomplete = 2,
	K60RailVerdictInvalid = 3,
};

/* Same value as K60BoardUnsupported: the PAS layer only sees an int. */
#define K60_RAIL_REFUSED (-63)

enum {
	K60RpmhOk = 0,
	K60RpmhNoDb = -1,
	K60RpmhMissing = -2,
	K60RpmhCorrupt = -3,
	K60RpmhNoLevel = -4,
	K60RpmhArgument = -5,
};

int k60_cmd_db_find(const uint8_t *db, size_t bytes, const char *name,
    K60RpmhResource *out);
int k60_rpmh_level_index(const K60RpmhResource *r, uint32_t level,
    uint32_t *index);
K60RscLayout k60_rsc_layout(uint32_t drv_id);
int k60_rail_measure(const volatile uint32_t *words, size_t words_bytes,
    const K60RscLayout *layout, uint32_t resource_id, K60RailRecord *out);
void k60_rail_ledger_store(uint32_t drv_id, const K60RailRecord *lcx,
    const K60RailRecord *lmx);
const K60RailLedger *k60_rail_ledger(void);
int k60_rail_verdict(const K60RailLedger *ledger, const char **rail,
    const char **field);
int k60_rail_inherit(void);
int k60_rail_probe(void);

#endif /* K60_PMIC_RAIL_H */
