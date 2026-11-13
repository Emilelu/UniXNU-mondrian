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
 * Nothing in this file writes a register.
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

typedef struct {
	uint32_t address;
	uint16_t levels[K60_RPMH_MAX_LEVELS];
	unsigned level_count;
} K60RpmhResource;

typedef struct {
	uint32_t tcs_stride, cmd_stride, irq_status, irq_clear, wait_for_cmpl;
	uint32_t control, status, cmd_enable, cmd_msgid, cmd_addr, cmd_data;
} K60RscLayout;

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
int k60_rail_probe(void);

#endif /* K60_PMIC_RAIL_H */
