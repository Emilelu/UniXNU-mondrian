/* Host test: parse the real ADSP ramdisk and compare two segments byte for
 * byte against the files pulled off the device. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "K60Fat.h"

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

static int check(const uint8_t *img, const K60FatVolume *vol, const char *name,
    const char *ref_path)
{
	uint32_t off = 0, len = 0;
	uint8_t *ref;
	size_t ref_len = 0;
	int rc;

	rc = k60_fat_find(img, vol, "ADSP", name, &off, &len);
	if (rc != 0) {
		printf("FAIL find %s rc=%d\n", name, rc);
		return 1;
	}
	ref = slurp(ref_path, &ref_len);
	if (ref == NULL) {
		printf("SKIP %s (no reference)\n", name);
		return 0;
	}
	if (ref_len != len || memcmp(img + off, ref, len) != 0) {
		printf("FAIL %s len=%u ref=%zu match=no\n", name, len, ref_len);
		free(ref);
		return 1;
	}
	printf("ok %s len=%u\n", name, len);
	free(ref);
	return 0;
}

int main(int argc, char **argv)
{
	size_t size = 0;
	uint8_t *img;
	K60FatVolume vol;
	int fails = 0;
	int rc;

	if (argc < 3) {
		printf("usage: %s <ramdisk.img> <firmware-dir>\n", argv[0]);
		return 2;
	}
	img = slurp(argv[1], &size);
	if (img == NULL) {
		printf("FAIL read %s\n", argv[1]);
		return 2;
	}
	rc = k60_fat_open(img, size, &vol);
	if (rc != 0) {
		printf("FAIL open rc=%d\n", rc);
		return 1;
	}
	printf("volume bps=%u spc=%u root=%u clusters=%u\n",
	    vol.bytes_per_sector, vol.sectors_per_cluster, vol.root_cluster,
	    vol.clusters);

	char path[512];
	for (int i = 0; i < 2; i++) {
		const char *name = i == 0 ? "adsp.b01" : "adsp.mdt";

		snprintf(path, sizeof(path), "%s/%s", argv[2], name);
		fails += check(img, &vol, name, path);
	}
	free(img);
	printf("%s\n", fails == 0 ? "TESTS OK 2 segments" : "TESTS FAILED");
	return fails == 0 ? 0 : 1;
}
