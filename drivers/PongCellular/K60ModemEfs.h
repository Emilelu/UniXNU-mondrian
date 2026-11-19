/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* The four EFS images the modem opens by name, and the copy plan its scatter
 * list turns into. This is the piece between the RMTFS protocol and the UFS:
 * it knows which GPT partition backs /boot/modem_fs1 and friends, how a
 * 512-byte-block scatter entry maps onto that image and into the shared
 * window, and nothing about how the bytes are actually read.
 *
 * Reference: PongModemRmtfs.h maps /boot/modem_fs1|fs2|fsg|fsc onto the Android
 * partitions modemst1, modemst2, fsg and fsc; rmtfsAnswer() copies between the
 * image and the region the scatter entry names.
 */
#ifndef K60_MODEM_EFS_H
#define K60_MODEM_EFS_H

#include <stddef.h>
#include <stdint.h>

#include "K60ModemRmtfs.h"

#define K60_EFS_IMAGE_COUNT 4u
/* A GPT partition entry name is 36 UTF-16LE code units (72 bytes). */
#define K60_EFS_GPT_NAME_BYTES 72u

/* Storage ids start at one, exactly as the open reply numbers them. */
const char *k60_efs_partition(uint32_t storage);
const char *k60_efs_boot_path(uint32_t storage);

/* Compares a GPT partition entry name, which is UTF-16LE with the remainder
 * zero filled, against an ASCII name. Returns 0 when they are the same. */
int k60_efs_name_matches(const void *entry, size_t entry_bytes, const char *name);

/* One copy the scatter list asks for: 'bytes' move from image_offset in the
 * image to buffer_offset in the shared window. */
typedef struct {
	uint64_t image_offset;
	uint64_t buffer_offset;
	uint32_t bytes;
} K60EfsSpan;

/* Turns a validated rw request into the copies that serve it. The request must
 * already have passed k60_rmtfs_check_vectors(); this function additionally
 * requires every byte to fall inside the image. Returns the number of spans
 * written to 'out', or -1 when the request does not fit (wrong message, no
 * vectors, more vectors than 'cap', or an offset past the end of the image). */
int k60_efs_plan(const K60RmtfsRequest *request, uint64_t image_bytes,
    uint64_t window_base, uint64_t window_bytes, K60EfsSpan *out, size_t cap);

/* Performs the copies a plan describes. direction 0 moves bytes from the image
 * into the shared window (the modem reads the image), direction 1 moves them
 * back (the modem writes it). 'image' and 'window' carry the whole image and
 * the whole window, so a span indexes them directly; every span must stay
 * inside both. Returns 0, or -1 when a span leaves a buffer or nothing is
 * planned. */
#define K60_EFS_TO_WINDOW 0
#define K60_EFS_TO_IMAGE  1
int k60_efs_copy(const K60EfsSpan *spans, size_t count, int direction,
    uint8_t *image, size_t image_bytes, uint8_t *window, size_t window_bytes);

/* Maps an open request path onto the storage id the reply must carry: 1..4 for
 * the four EFS images, 0 for anything else. The comparison is byte for byte
 * against k60_efs_boot_path(), because the wire path has no terminator. */
uint32_t k60_efs_storage_for_path(const char *path, size_t length);

/* Reads image bytes on the modem's behalf. 'read' must fill dst with 'bytes'
 * from the image at 'offset' and return 0; anything else counts as a failure.
 * The callback is what the kernel supplies once the UFS path exists. */
typedef int (*K60EfsRead)(void *context, uint32_t storage, uint64_t offset,
    uint8_t *dst, size_t bytes);

/* Serves one read request end to end: it must be an rw request in the read
 * direction, its vectors must fit the image and the window, and the reader must
 * deliver every span. On success the window holds what the modem asked for and
 * the caller answers result 0. Returns 0 on success, -1 otherwise. */
int k60_efs_serve_read(const K60RmtfsRequest *request, K60EfsRead read,
    void *context, uint8_t *image, size_t image_bytes, uint8_t *window,
    size_t window_bytes, uint64_t window_base);

/* Serves the write direction into a boot-session shadow: the bytes land in
 * 'image' and nothing reaches the flash. Pong does the same (a write only ever
 * reaches the shadow), so a modem write is acknowledged without a UFS writer.
 * Returns 0 when the image now holds the bytes, -1 otherwise. */
int k60_efs_serve_write(const K60RmtfsRequest *request, uint8_t *image,
    size_t image_bytes, const uint8_t *window, size_t window_bytes,
    uint64_t window_base);

#endif /* K60_MODEM_RMTFS_EFS */