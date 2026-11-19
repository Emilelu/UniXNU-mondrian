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

#endif /* K60_MODEM_RMTFS_EFS */
