/* Host test for the EFS image table and the scatter-to-copy mapping. */
#include <stdio.h>
#include <string.h>

#include "K60ModemEfs.h"
#include "K60ModemRmtfs.h"

static int failures;

static void check(int ok, const char *what)
{
	if (!ok) {
		printf("FAIL %s\n", what);
		failures++;
	}
}

static void put_name(uint8_t *entry, const char *name)
{
	size_t i;

	memset(entry, 0, K60_EFS_GPT_NAME_BYTES);
	for (i = 0; name[i] != '\0' && i < K60_EFS_GPT_NAME_BYTES / 2; i++) {
		entry[2 * i] = (uint8_t)name[i];
		entry[2 * i + 1] = 0;
	}
}

static void test_table(void)
{
	check(strcmp(k60_efs_partition(1), "modemst1") == 0, "storage 1 is modemst1");
	check(strcmp(k60_efs_partition(2), "modemst2") == 0, "storage 2 is modemst2");
	check(strcmp(k60_efs_partition(3), "fsg") == 0, "storage 3 is fsg");
	check(strcmp(k60_efs_partition(4), "fsc") == 0, "storage 4 is fsc");
	check(k60_efs_partition(0) == NULL, "storage 0 has no partition");
	check(k60_efs_partition(5) == NULL, "storage 5 has no partition");
	check(strcmp(k60_efs_boot_path(1), "/boot/modem_fs1") == 0, "boot path 1");
	check(strcmp(k60_efs_boot_path(4), "/boot/modem_fsc") == 0, "boot path 4");
	check(k60_efs_boot_path(0) == NULL, "boot path 0 is absent");
}

static void test_names(void)
{
	uint8_t entry[K60_EFS_GPT_NAME_BYTES];

	put_name(entry, "modemst1");
	check(k60_efs_name_matches(entry, sizeof entry, "modemst1") == 0, "modemst1 matches");
	check(k60_efs_name_matches(entry, sizeof entry, "modemst2") != 0, "modemst2 does not");
	put_name(entry, "fsg");
	check(k60_efs_name_matches(entry, sizeof entry, "fsg") == 0, "fsg matches");
	check(k60_efs_name_matches(entry, sizeof entry, "fsg1") != 0, "fsg1 does not");
	put_name(entry, "userdata");
	check(k60_efs_name_matches(entry, sizeof entry, "fsg") != 0, "userdata is not fsg");
	check(k60_efs_name_matches(NULL, sizeof entry, "fsg") != 0, "NULL entry");
	check(k60_efs_name_matches(entry, sizeof entry, NULL) != 0, "NULL name");
	check(k60_efs_name_matches(entry, 0, "fsg") != 0, "empty entry");
}

static void test_plan(void)
{
	K60RmtfsRequest request;
	K60EfsSpan spans[K60_RMTFS_MAX_VECS];
	const uint64_t window_base = 0xaf000000ull;
	const uint64_t window_bytes = 0x280000ull;
	const uint64_t image_bytes = 0x400000ull;
	int n;

	memset(&request, 0, sizeof request);
	request.message = K60_RMTFS_RW;
	request.storage = 1;
	request.direction = 0;
	request.vectors = 2;
	request.table[0].block_offset = 0x10;
	request.table[0].physical = (uint32_t)(window_base + 0x200);
	request.table[0].block_length = 2;
	request.table[1].block_offset = 0x20;
	request.table[1].physical = (uint32_t)(window_base + 0x1000);
	request.table[1].block_length = 4;

	n = k60_efs_plan(&request, image_bytes, window_base, window_bytes, spans,
	    K60_RMTFS_MAX_VECS);
	check(n == 2, "two vectors plan two copies");
	check(spans[0].image_offset == 0x2000 && spans[0].buffer_offset == 0x200 &&
	    spans[0].bytes == 1024, "first copy is image 0x2000 to window 0x200");
	check(spans[1].image_offset == 0x4000 && spans[1].buffer_offset == 0x1000 &&
	    spans[1].bytes == 2048, "second copy is image 0x4000 to window 0x1000");
	check(k60_rmtfs_check_vectors(&request, image_bytes, window_base,
	    window_bytes) == 0, "the same request passes the protocol check");

	/* A read past the end of the image is refused even when the window fits. */
	request.table[1].block_offset = (uint32_t)(image_bytes / K60_RMTFS_BLOCK) - 1;
	check(k60_efs_plan(&request, image_bytes, window_base, window_bytes, spans,
	    K60_RMTFS_MAX_VECS) == -1, "a copy past the image end is refused");
	request.table[1].block_offset = 0x20;

	/* The physical address must stay inside the window. */
	request.table[0].physical = (uint32_t)(window_base - 0x200);
	check(k60_efs_plan(&request, image_bytes, window_base, window_bytes, spans,
	    K60_RMTFS_MAX_VECS) == -1, "a copy below the window is refused");
	request.table[0].physical = (uint32_t)(window_base + 0x200);
	request.table[0].physical = (uint32_t)(window_base + window_bytes - 0x200);
	check(k60_efs_plan(&request, image_bytes, window_base, window_bytes, spans,
	    K60_RMTFS_MAX_VECS) == -1, "a copy ending past the window is refused");
	request.table[0].physical = (uint32_t)(window_base + 0x200);

	/* Zero-length entries carry nothing and are skipped. */
	request.vectors = 1;
	request.table[0].block_length = 0;
	check(k60_efs_plan(&request, image_bytes, window_base, window_bytes, spans,
	    K60_RMTFS_MAX_VECS) == -1, "a plan with no bytes is refused");

	request.table[0].block_length = 2;
	request.vectors = 0;
	check(k60_efs_plan(&request, image_bytes, window_base, window_bytes, spans,
	    K60_RMTFS_MAX_VECS) == -1, "a request without vectors is refused");
	request.vectors = 2;
	check(k60_efs_plan(&request, image_bytes, window_base, window_bytes, spans,
	    1) == -1, "more vectors than the caller can hold is refused");

	request.message = K60_RMTFS_ALLOC;
	check(k60_efs_plan(&request, image_bytes, window_base, window_bytes, spans,
	    K60_RMTFS_MAX_VECS) == -1, "only rw requests are planned");
}

static void
test_copy(void)
{
	uint8_t image[0x4000];
	uint8_t window[0x800];
	K60EfsSpan spans[2];

	for (size_t i = 0; i < sizeof image; i++) {
		image[i] = (uint8_t)(i * 7u + 3u);
	}
	memset(window, 0, sizeof window);
	spans[0].image_offset = 0x2000;
	spans[0].buffer_offset = 0x100;
	spans[0].bytes = 0x40;
	spans[1].image_offset = 0x2100;
	spans[1].buffer_offset = 0x200;
	spans[1].bytes = 0x20;

	check(k60_efs_copy(spans, 2, K60_EFS_TO_WINDOW, image, sizeof image, window,
	    sizeof window) == 0, "the plan copies into the window");
	check(window[0x100] == image[0x2000] &&
	    window[0x13f] == image[0x203f], "first span lands where it says");
	check(window[0x200] == image[0x2100] &&
	    window[0x21f] == image[0x211f], "second span lands where it says");

	/* The modem writes the image: the same spans run the other way. */
	image[0x2000] = 0xaa;
	image[0x203f] = 0xbb;
	check(k60_efs_copy(spans, 2, K60_EFS_TO_IMAGE, image, sizeof image, window,
	    sizeof window) == 0, "the plan copies back into the image");
	check(image[0x2000] == window[0x100] && image[0x203f] == window[0x13f],
	    "the write direction restores the image");

	spans[0].bytes = 0x41;
	spans[0].buffer_offset = sizeof window - 0x20;
	check(k60_efs_copy(spans, 1, K60_EFS_TO_WINDOW, image, sizeof image, window,
	    sizeof window) == -1, "a span past the window is refused");
	spans[0].buffer_offset = 0x100;
	spans[0].image_offset = sizeof image - 0x10;
	spans[0].bytes = 0x40;
	check(k60_efs_copy(spans, 1, K60_EFS_TO_WINDOW, image, sizeof image, window,
	    sizeof window) == -1, "a span past the image is refused");
	spans[0].image_offset = 0x2000;
	spans[0].bytes = 0x40;
	check(k60_efs_copy(spans, 0, K60_EFS_TO_WINDOW, image, sizeof image, window,
	    sizeof window) == -1, "an empty plan copies nothing");
	check(k60_efs_copy(spans, 1, 7, image, sizeof image, window,
	    sizeof window) == -1, "an unknown direction is refused");
	check(k60_efs_copy(NULL, 1, K60_EFS_TO_WINDOW, image, sizeof image, window,
	    sizeof window) == -1, "a NULL plan is refused");
}

static uint32_t
mix(uint32_t *state)
{
	uint32_t x = *state;

	x ^= x << 13;
	x ^= x >> 17;
	x ^= x << 5;
	*state = x;
	return x;
}

/* The protocol check and the plan must agree: whenever the request is legal the
 * plan returns one span per vector, and whenever the check refuses it the plan
 * refuses too. Random tables catch a divergence the fixed cases would miss. */
static void
test_sweep(void)
{
	K60RmtfsRequest request;
	K60EfsSpan spans[K60_RMTFS_MAX_VECS];
	const uint64_t window_base = 0xaf000000ull;
	const uint64_t window_bytes = 0x8000ull;
	const uint64_t image_bytes = 0x20000ull;
	uint32_t state = 0x1234567u;
	unsigned legal = 0, refused = 0;

	for (unsigned i = 0; i < 4000; i++) {
		uint64_t expected = 0;

		memset(&request, 0, sizeof request);
		request.message = K60_RMTFS_RW;
		request.vectors = 1 + mix(&state) % K60_RMTFS_MAX_VECS;
		for (size_t v = 0; v < request.vectors; v++) {
			request.table[v].block_offset = mix(&state) % 64u;
			request.table[v].block_length = mix(&state) % 8u;
			request.table[v].physical = (uint32_t)(window_base +
			    mix(&state) % window_bytes);
			expected += (uint64_t)request.table[v].block_length *
			    K60_RMTFS_BLOCK;
		}
		int checked = k60_rmtfs_check_vectors(&request, image_bytes,
		    window_base, window_bytes);
		int planned = k60_efs_plan(&request, image_bytes, window_base,
		    window_bytes, spans, K60_RMTFS_MAX_VECS);

		if (checked == 0) {
			uint64_t total = 0;

			legal++;
			check(planned == (int)request.vectors,
			    "a legal request plans one span per vector");
			for (int s = 0; s < planned; s++) {
				total += spans[s].bytes;
				check(spans[s].bytes != 0, "no empty span");
				check(spans[s].image_offset + spans[s].bytes <=
				    image_bytes, "the span stays inside the image");
				check(spans[s].buffer_offset + spans[s].bytes <=
				    window_bytes, "the span stays inside the window");
			}
			check(total == expected, "the spans move every byte once");
		} else {
			refused++;
			check(planned == -1, "a refused request is not planned");
		}
	}
	check(legal > 100 && refused > 100, "the sweep covers both outcomes");
}

int
main(void)
{
	test_table();
	test_names();
	test_plan();
	test_copy();
	test_sweep();
	if (failures != 0) {
		printf("K60 EFS FAIL %d checks\n", failures);
		return 1;
	}
	printf("K60 EFS PASS table, gpt names, scatter plan, copies, sweep, refusals\n");
	return 0;
}