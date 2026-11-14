/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * Pure reader for the Awinic ACF tuning file (aw882xx_acf.bin) and the
 * decisions that follow from one.
 *
 * Why this file exists. On hardware both amplifiers answered chip id 0x2113
 * (AW88261, docs/research/audio/AMPS.md section 7.2), which settles which part
 * sits on the board but not which driver to port: every vendor tree drives this
 * part from a per-project ACF blob rather than from a register table, and the
 * K60's own blob was found on the device at /vendor/firmware/aw882xx_acf.bin
 * (3440 bytes, sha256 ce0e16d22380565114f56e6a02e4f85959160baccc6c163df6ecaf9db20cbf9e).
 * The A5 answer is therefore "port the ACF-driven shape and load the blob the
 * phone already ships", not "copy another board's register table".
 *
 * Everything here is a plain function over a byte buffer: no MMIO, no kernel
 * headers, so the host unit test (drivers/PongAudio/tests) can pin it. Layout
 * facts, each read from a source and quoted by line:
 *   D: aw88395_data_type.h:19-21        ACF_FILE_ID, header field offsets
 *   H: hakios.speaker.c:543             dde stride = entry_size / entries
 *   H: hakios.speaker.c:594-599         pairs at +0x40, LE16 reg + LE16 val
 *   H: hakios.speaker.c:604-611         per-block checksum ranges
 *   H: hakios.speaker.c:430-431         I2C 0x35 is dev_index 0, 0x34 is 1
 *   H: hakios.speaker.c:455-524         monitor table offsets and row layout
 *   M: aw88261.c:420-434,437-449,470    SYSCTRL / DBGCTRL / I2SCTRL3 write rules
 *   M: aw88261.c:358-391                vcalb from the four fuse reads
 *
 * This header is deliberately not part of patches/audio yet: nothing in the XNU
 * tree includes it, exactly like PongCodecPlan.h. When a kernel .c starts to
 * include it, add it to NEW_FILES in the patch generator or the build will not
 * see it.
 */
#ifndef PONG_AUDIO_ACF_H
#define PONG_AUDIO_ACF_H

#include <stdbool.h>
#include <stdint.h>

/* D: aw88395_data_type.h:19 ACF_FILE_ID. */
#define PONG_ACF_MAGIC            0x0a15f908u
/* D: aw88395_data_type.h:33-38 the dde entry fields this reader uses. */
#define PONG_ACF_DDE_DEV_INDEX    20u
#define PONG_ACF_DDE_PROFILE      26u
#define PONG_ACF_DDE_KIND         28u
#define PONG_ACF_DDE_LENGTH       32u
#define PONG_ACF_DDE_OFFSET       36u
/* H: hakios.speaker.c:405-406 kind 4 = register block, kind 10 = monitor table. */
#define PONG_ACF_KIND_REGS        4u
#define PONG_ACF_KIND_MONITOR     10u
/* H: hakios.speaker.c:404 ACF_PROFILE_MUSIC is profile 0. */
#define PONG_ACF_PROFILE_MUSIC    0u
/* H: hakios.speaker.c:408 ACF_BLOCK_HEADER = 0x3c: the pair count sits at the
 * end of that fixed header and the pairs start one word (0x40) in. */
#define PONG_ACF_BLOCK_HEADER     0x3cu
#define PONG_ACF_PAIRS_AT         0x40u
#define PONG_ACF_DATA_LENGTH      0x10u
/* H: hakios.speaker.c:594-599 both words must say "16-bit registers, 16-bit
 * values" before the payload is read as pairs. */
#define PONG_ACF_REG_BITS_WORD    0x20u
#define PONG_ACF_VAL_BITS_WORD    0x24u
#define PONG_ACF_BITS_16X16       2u

/* Register words the write pass must treat specially (M: aw88261.c:420-470). */
#define PONG_ACF_REG_ID           0x00u   /* soft reset; never taken from a profile */
#define PONG_ACF_REG_SYSCTRL      0x04u
#define PONG_ACF_REG_I2SCTRL3     0x08u
#define PONG_ACF_REG_DBGCTRL      0x14u
#define PONG_ACF_REG_VSNTM1       0x50u   /* computed from the fuses, skipped here */
#define PONG_ACF_REG_LIMIT        0x70u   /* H: refusal at or above this in the pass */

/* SYSCTRL bits and the mask the merge preserves (M: aw88261.h:119-240). */
#define PONG_ACF_SYSCTRL_PWDN     (1u << 0)
#define PONG_ACF_SYSCTRL_AMPPD    (1u << 1)
#define PONG_ACF_SYSCTRL_HMUTE    (1u << 8)
#define PONG_ACF_SYSCTRL_ULS_HMUTE (1u << 14)
#define PONG_ACF_SYSCTRL_KEEP     (PONG_ACF_SYSCTRL_PWDN | PONG_ACF_SYSCTRL_AMPPD | \
    PONG_ACF_SYSCTRL_HMUTE)
/* M: aw88261.h:240-247 I2STXEN sits in I2SCTRL3 bit 6. */
#define PONG_ACF_I2STXEN          (1u << 6)
/* M: aw88261.h:348-352 EF_DBMD_MASK 0xfff7 / OR_VALUE 0x0008. */
#define PONG_ACF_EF_DBMD_MASK     0xfff7u
#define PONG_ACF_EF_OR_VALUE      0x0008u

/* M: aw88261.c:358-391 vcalb = (1 << 13) * (1000 + icalk) / (1000 + vcalk), with
 * the fuse fields signed 10-bit values (M: aw88261.h:114-117, 364-368). */
#define PONG_ACF_FUSE_BITS        0x3ffu
#define PONG_ACF_FUSE_SIGN        0x200u
#define PONG_ACF_CABL_BASE        1000
#define PONG_ACF_VCAL_FACTOR      (1 << 13)

static inline uint16_t
pong_acf_le16(const uint8_t *p)
{
	return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static inline uint32_t
pong_acf_le32(const uint8_t *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
	    ((uint32_t)p[3] << 24);
}

/* A header is usable only if the magic matches and the dde table divides evenly
 * into entries of at least 0x30 bytes (H: hakios.speaker.c:525-534). A malformed
 * file must be refused before any field in the table is trusted. */
static inline bool
pong_acf_header_ok(const uint8_t *buf, uint32_t len)
{
	uint32_t entry_size, entries, table_at;

	if (buf == 0 || len < 0x60u) {
		return false;
	}
	if (pong_acf_le32(buf) != PONG_ACF_MAGIC) {
		return false;
	}
	entry_size = pong_acf_le32(buf + 0x34u);
	entries = pong_acf_le32(buf + 0x38u);
	table_at = pong_acf_le32(buf + 0x3cu);
	if (entries == 0u || entry_size % entries != 0u || entry_size / entries < 0x30u) {
		return false;
	}
	if (table_at < 0x50u || table_at + entry_size > len) {
		return false;
	}
	return true;
}

/* One dde entry is entry_size / entries bytes apart (H: hakios.speaker.c:543). */
static inline uint32_t
pong_acf_stride(const uint8_t *buf)
{
	return pong_acf_le32(buf + 0x34u) / pong_acf_le32(buf + 0x38u);
}

static inline uint32_t
pong_acf_count(const uint8_t *buf)
{
	return pong_acf_le32(buf + 0x38u);
}

/* Find the block for one amplifier. The bus and address fields in the real file
 * are 0xffff (unset), so dev_index - the driver's channel - is the only key;
 * M: aw88395_lib.c:535 compares it against aw_dev->channel for the same reason. */
static inline bool
pong_acf_find(const uint8_t *buf, uint32_t len, uint32_t dev_index,
    uint32_t profile, uint32_t kind, uint32_t *off_out, uint32_t *size_out)
{
	uint32_t table_at, stride, entries, i;

	if (!pong_acf_header_ok(buf, len)) {
		return false;
	}
	table_at = pong_acf_le32(buf + 0x3cu);
	stride = pong_acf_stride(buf);
	entries = pong_acf_count(buf);
	for (i = 0u; i < entries; i++) {
		const uint8_t *e = buf + table_at + i * stride;
		uint32_t off, size;

		if (pong_acf_le16(e + PONG_ACF_DDE_DEV_INDEX) != dev_index ||
		    pong_acf_le16(e + PONG_ACF_DDE_PROFILE) != profile ||
		    pong_acf_le32(e + PONG_ACF_DDE_KIND) != kind) {
			continue;
		}
		off = pong_acf_le32(e + PONG_ACF_DDE_OFFSET);
		size = pong_acf_le32(e + PONG_ACF_DDE_LENGTH);
		if (off < 0x50u || size < 0x40u || off + size > len) {
			return false;
		}
		*off_out = off;
		*size_out = size;
		return true;
	}
	return false;
}

/* Checksum: a register block covers block[4 : 0x3c + data_length], a monitor
 * block covers block[4 : length] (H: hakios.speaker.c:604-611), and the stored
 * value is the LE32 at offset 0. Hashing the whole block instead - the obvious
 * first guess - makes all ten blocks of the K60 file look corrupt. */
static inline uint32_t
pong_acf_checksum(const uint8_t *block, uint32_t size, uint32_t kind)
{
	uint32_t end = size;
	uint32_t sum = 0;
	uint32_t i;

	if (kind == PONG_ACF_KIND_REGS) {
		end = PONG_ACF_BLOCK_HEADER + pong_acf_le32(block + PONG_ACF_DATA_LENGTH);
	}
	if (end > size) {
		return 0u;
	}
	for (i = 4u; i < end; i++) {
		sum += block[i];
	}
	return sum;
}

static inline bool
pong_acf_block_ok(const uint8_t *block, uint32_t size, uint32_t kind)
{
	return pong_acf_checksum(block, size, kind) == pong_acf_le32(block);
}

/* A register block is read as pairs only when it declares 16-bit registers with
 * 16-bit values and the count accounts for the whole payload. */
static inline bool
pong_acf_pairs_ok(const uint8_t *block, uint32_t size)
{
	uint32_t count, data_length;

	if (pong_acf_le32(block + PONG_ACF_REG_BITS_WORD) != PONG_ACF_BITS_16X16 ||
	    pong_acf_le32(block + PONG_ACF_VAL_BITS_WORD) != PONG_ACF_BITS_16X16) {
		return false;
	}
	count = pong_acf_le32(block + PONG_ACF_BLOCK_HEADER);
	data_length = pong_acf_le32(block + PONG_ACF_DATA_LENGTH);
	if (count == 0u || count * 4u + 4u != data_length) {
		return false;
	}
	return PONG_ACF_PAIRS_AT + count * 4u <= size;
}

static inline uint32_t
pong_acf_pair_count(const uint8_t *block)
{
	return pong_acf_le32(block + PONG_ACF_BLOCK_HEADER);
}

/* Pairs are little endian and kept in file order: some registers only latch when
 * written after others, so the order is part of the data, not an artefact. */
static inline bool
pong_acf_pair_at(const uint8_t *block, uint32_t size, uint32_t index,
    uint16_t *reg_out, uint16_t *val_out)
{
	if (!pong_acf_pairs_ok(block, size) || index >= pong_acf_pair_count(block)) {
		return false;
	}
	*reg_out = pong_acf_le16(block + PONG_ACF_PAIRS_AT + index * 4u);
	*val_out = pong_acf_le16(block + PONG_ACF_PAIRS_AT + index * 4u + 2u);
	return true;
}

/* Which half of the ACF belongs to an amplifier. H: hakios.speaker.c:430-431
 * documents that on this board I2C 0x35 carries sound-channel 0 (slot 0, left)
 * and 0x34 the other, while the probe labels 0x34 "amp0"; the two numbering
 * schemes do not coincide, so a lookup must never go by the probe's index.
 * Returns 0xff for an address that is not one of the two. */
static inline uint8_t
pong_acf_channel_for_addr(uint16_t addr)
{
	switch (addr) {
	case 0x35u: return 0u;
	case 0x34u: return 1u;
	default: return 0xffu;
	}
}

/* M: aw88261.c:437-443 the efuse checksum direction follows DBGCTRL: OR when
 * (value & ~EF_DBMD_MASK) == OR_VALUE, AND otherwise. The K60 blob writes
 * 0x14 = 0xc003 and the probe read back 0xa003, so this board takes AND. */
static inline bool
pong_acf_ef_or(uint16_t dbgctrl)
{
	return (dbgctrl & (uint16_t)~PONG_ACF_EF_DBMD_MASK) == PONG_ACF_EF_OR_VALUE;
}

/* M: aw88261.h:114-117 + aw88261.c:316-341 each fuse byte holds one signed
 * 10-bit value; OR combines the two halves when the board check is the OR kind,
 * AND otherwise. */
static inline int
pong_acf_fuse_value(uint16_t hi, uint16_t lo, bool ef_or)
{
	uint32_t bits = ef_or ?
	    ((uint32_t)hi | (uint32_t)lo) & PONG_ACF_FUSE_BITS :
	    ((uint32_t)hi & (uint32_t)lo) & PONG_ACF_FUSE_BITS;

	if ((bits & PONG_ACF_FUSE_SIGN) != 0u) {
		return PONG_ACF_CABL_BASE + (int)bits - 0x400;
	}
	return PONG_ACF_CABL_BASE + (int)bits;
}

/* M: aw88261.c:358-391 the value the driver must write to VSNTM1. Both fuse
 * values are base-1000, so the ratio is taken over those and scaled by 1 << 13.
 * A non-positive value would divide by zero or invert the ratio: refuse rather
 * than write garbage into a register that sets the speaker's calibration. */
static inline bool
pong_acf_vcalb(uint16_t dbgctrl, uint16_t efrh4, uint16_t efrh3,
    uint16_t efrl4, uint16_t efrl3, uint16_t *out)
{
	bool ef_or = pong_acf_ef_or(dbgctrl);
	int icalk = pong_acf_fuse_value(efrh4, efrl4, ef_or);
	int vcalk = pong_acf_fuse_value(efrh3, efrl3, ef_or);

	if (vcalk <= 0 || icalk <= 0) {
		return false;
	}
	*out = (uint16_t)((PONG_ACF_VCAL_FACTOR * (uint32_t)icalk) / (uint32_t)vcalk);
	return true;
}
#endif /* PONG_AUDIO_ACF_H */
