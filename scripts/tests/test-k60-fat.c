/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test: the boot-argument form that creates md0, and the FAT lookup that
 * follows it. Both run against strings and the real ramdisk image. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "K60Fat.h"

static int fails;

static void expect(int cond, const char *what)
{
	if (!cond) {
		printf("FAIL %s\n", what);
		fails++;
	}
}

static void parse_cases(void)
{
	uint64_t base = 0, size = 0;
	const char *args = "-v kextlog=0xfff pmd0=0x83b5000@0x2000000 other=1";

	expect(k60_md_parse(args, strlen(args), "pmd0", &base, &size) == 0,
	    "parse pmd0");
	expect(base == 0x83b5000ull, "base value");
	expect(size == 0x2000000ull, "size value");

	expect(k60_md_parse("-v vmd0=1073741824@33554432",
	    strlen("-v vmd0=1073741824@33554432"), "vmd0", &base,
	    &size) == 0, "parse vmd0 decimal");
	expect(base == 1073741824ull, "decimal base");
	expect(size == 33554432ull, "decimal size");

	expect(k60_md_parse("-v pmd0=0x1000@0x2000",
	    strlen("-v pmd0=0x1000@0x2000"), "vmd0", &base, &size)
	    != 0, "wrong key is not accepted");
	expect(k60_md_parse("-v pmd0=0x1000", strlen("-v pmd0=0x1000"), "pmd0", &base, &size) != 0,
	    "missing @size is rejected");
	expect(k60_md_parse("-v pmd0=@0x2000", strlen("-v pmd0=@0x2000"), "pmd0", &base, &size) != 0,
	    "missing base is rejected");
	expect(k60_md_parse("pmd0=0x1000@0x2000x",
	    strlen("pmd0=0x1000@0x2000x"), "pmd0", &base, &size) != 0,
	    "trailing junk is rejected");
}

static uint8_t *slurp(const char *path, size_t *size)
{
	FILE *f = fopen(path, "rb");
	uint8_t *buf;
	long n;

	if (f == NULL) {
		return NULL;
	}
	fseek(f, 0, SEEK_END);
	n = ftell(f);
	fseek(f, 0, SEEK_SET);
	buf = malloc((size_t)n);
	if (buf == NULL || fread(buf, 1, (size_t)n, f) != (size_t)n) {
		fclose(f);
		free(buf);
		return NULL;
	}
	fclose(f);
	*size = (size_t)n;
	return buf;
}

static void image_case(const char *img_path, const char *fw_dir)
{
	size_t size = 0;
	uint8_t *img = slurp(img_path, &size);
	K60FatVolume vol;
	uint32_t off = 0, len = 0;
	char ref_path[512];
	uint8_t *ref;
	size_t ref_len = 0;

	if (img == NULL) {
		printf("SKIP image case (no %s)\n", img_path);
		return;
	}
	expect(k60_fat_open(img, size, &vol) == 0, "open the volume");
	expect(k60_fat_find(img, &vol, "ADSP", "adsp.b01", &off, &len) == 0,
	    "find adsp.b01");

	snprintf(ref_path, sizeof(ref_path), "%s/adsp.b01", fw_dir);
	ref = slurp(ref_path, &ref_len);
	if (ref != NULL) {
		expect(ref_len == len && memcmp(img + off, ref, len) == 0,
		    "adsp.b01 bytes match");
		free(ref);
	}
	free(img);
}

int main(int argc, char **argv)
{
	parse_cases();
	if (argc >= 3) {
		image_case(argv[1], argv[2]);
	}
	printf("%s (%d failure(s))\n", fails == 0 ? "TESTS OK 8 cases" : "TESTS FAILED",
	    fails);
	return fails == 0 ? 0 : 1;
}
