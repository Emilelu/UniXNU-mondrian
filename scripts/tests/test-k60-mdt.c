/* Host test for the K60 MDT parser and the ipa_fws layout check. */

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "K60Ipa.h"
#include "K60Mdt.h"

static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *p, uint32_t v) { put16(p, (uint16_t)v); put16(p + 2, (uint16_t)(v >> 16)); }

static size_t build_elf32(uint8_t *blob, uint32_t memsz, uint32_t flags)
{
    const uint32_t phoff = 52;
    const uint32_t phentsize = 32;
    const uint32_t phnum = 3;
    const uint32_t header = phoff + phentsize * phnum;
    const uint32_t hash_off = header + 16;

    memset(blob, 0, hash_off + 16);
    blob[0] = 0x7f; blob[1] = 'E'; blob[2] = 'L'; blob[3] = 'F';
    blob[4] = 1; /* ELF32 */
    blob[5] = 1; /* little endian */
    put32(blob + 28, phoff);
    put16(blob + 42, (uint16_t)phentsize);
    put16(blob + 44, (uint16_t)phnum);

    /* Program header 0: PT_NULL covering the ELF and program headers. */
    put32(blob + 52 + 0, 0);
    put32(blob + 52 + 4, 0);
    put32(blob + 52 + 16, header);
    put32(blob + 52 + 20, header);

    /* Program header 1: the one loadable segment. */
    put32(blob + 84 + 0, 1);
    put32(blob + 84 + 4, header);
    put32(blob + 84 + 16, 16);
    put32(blob + 84 + 20, memsz);
    put32(blob + 84 + 24, flags);

    /* Program header 2: the hash segment. */
    put32(blob + 116 + 0, 1);
    put32(blob + 116 + 4, hash_off);
    put32(blob + 116 + 16, 16);
    put32(blob + 116 + 20, 16);
    put32(blob + 116 + 24, 2u << 24);
    return hash_off + 16;
}

static int blob_read(void *context, uint64_t offset, void *to, size_t length)
{
    memcpy(to, (const uint8_t *)context + offset, length);
    return 0;
}

static int fail(const char *what)
{
    printf("FAIL %s\n", what);
    return 1;
}

int main(void)
{
    uint8_t blob[256];
    K60MdtImage image;
    K60MdtSplit split;
    K60IpaFirmwarePlan plan;
    uint8_t rebuilt[256];
    uint64_t offset = 0;
    size_t size;

    size = build_elf32(blob, 0x2000, 1u << 27);
    if (k60_mdt_parse(&image, size, (K60MdtRead)0, blob) != K60MdtReadError) {
        return fail("NULL callback must be rejected");
    }
    if (k60_mdt_parse(&image, size, blob_read, blob) != K60MdtOk) {
        return fail("valid image parse failed");
    }
    if (image.elf64 || image.count != 3 || image.hash != 2 || image.header_size != 148 ||
        image.min_address != 0 || image.max_address != 0x2000 || !image.relocatable ||
        k60_mdt_metadata_size(&image) != 164 || k60_mdt_span(&image) != 0x2000) {
        return fail("image fields wrong");
    }
    if (k60_mdt_place(&image, 1, 0, 0x10000, &offset) != K60MdtOk || offset != 0) {
        return fail("place of load segment wrong");
    }
    if (k60_ipa_firmware_check(blob, size, &plan) != K60IpaOk) {
        return fail("valid image rejected");
    }
    if (plan.span != 0x2000 || plan.metadata != 164 || plan.load_segments != 1 || !plan.relocatable) {
        printf("FAIL plan span=%llu metadata=%llu loads=%u reloc=%u\n",
            (unsigned long long)plan.span, (unsigned long long)plan.metadata,
            plan.load_segments, plan.relocatable);
        return 1;
    }

    if (k60_ipa_firmware_check(blob, size, NULL) != K60IpaBadArgument) {
        return fail("NULL plan must be rejected");
    }
    if (k60_ipa_firmware_check(blob, 12, &plan) != K60IpaFirmwareBadImage) {
        return fail("short blob must fail parse");
    }

    size = build_elf32(blob, 0x2000, 0);
    if (k60_ipa_firmware_check(blob, size, &plan) != K60IpaFirmwareLayout) {
        return fail("non-relocatable image must not pass");
    }
    size = build_elf32(blob, 0x12000, 1u << 27);
    if (k60_ipa_firmware_check(blob, size, &plan) != K60IpaFirmwareLayout) {
        return fail("oversize span must not pass");
    }

    size = build_elf32(blob, 0x2000, 1u << 27);
    if (k60_ipa_firmware_check(blob, size, &plan) != K60IpaOk) {
        return fail("final valid image rejected");
    }
    if (k60_mdt_split(&split, blob, 148) != K60MdtOk || split.size != 180 || split.count != 3) {
        return fail("split layout rejected");
    }
    if (k60_mdt_split_read(&split, NULL, NULL, 0, rebuilt, sizeof(rebuilt)) != K60MdtOutside) {
        return fail("split read without callback must fail");
    }

    printf("K60 MDT PASS span=%llu metadata=%llu loads=%u split=%llu\n",
        (unsigned long long)plan.span, (unsigned long long)plan.metadata,
        plan.load_segments, (unsigned long long)split.size);
    return 0;
}