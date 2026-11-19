/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* RMTFS: the storage service the modem asks for its EFS images before its RF
 * and QMI stack can start. Pong blocks PAS_INIT_IMAGE until its native RFS
 * storage is ready for exactly this reason (PongModemRuntime.cpp:271-277) and
 * serves four images over QMI v1 service 14 (PongModemRmtfs.h:1-13).
 *
 * The wire layout follows linux-msm/rmtfs and the reference:
 *   1 open   -- TLV 1 is the image path, the reply carries the storage id;
 *   2 close  -- TLV 1 is the id;
 *   3 rw     -- TLV 2 direction, TLV 3 the scatter list, TLV 4 force;
 *   4 alloc  -- TLV 1 id, TLV 2 the size of the shared buffer;
 *   5 sync   -- TLV 1 id, acknowledged with one zero byte.
 * This file is protocol only: no buffer, no UFS, no SCM, so the kernel and the
 * host test share one implementation of the parts that can be wrong on paper.
 */
#ifndef K60_MODEM_RMTFS_H
#define K60_MODEM_RMTFS_H

#include <stddef.h>
#include <stdint.h>

#define K60_RMTFS_MAX_PATH 64u
#define K60_RMTFS_MAX_VECS 8u
#define K60_RMTFS_STORAGE_COUNT 4u
#define K60_RMTFS_BLOCK 512u

/* QMI v1 message numbers on service 14, in the order the reference
 * dispatches them (PongModemRmtfs.h:84-145). */
#define K60_RMTFS_OPEN 1u
#define K60_RMTFS_CLOSE 2u
#define K60_RMTFS_RW 3u
#define K60_RMTFS_ALLOC 4u
#define K60_RMTFS_SYNC 5u

typedef struct {
	uint32_t block_offset;
	uint32_t physical;
	uint32_t block_length;
} K60RmtfsVec;

typedef struct {
	uint16_t message;
	uint16_t transaction;
	uint32_t storage;
	uint32_t direction;
	uint32_t force;
	uint32_t alloc_bytes;
	char path[K60_RMTFS_MAX_PATH];
	size_t path_length;
	size_t vectors;
	K60RmtfsVec table[K60_RMTFS_MAX_VECS];
} K60RmtfsRequest;

/* Parses one request. Returns 0 when every field the message defines is
 * present and well formed, -1 otherwise; a rejected request still carries the
 * message number and transaction so the caller can answer with result 2. */
int k60_rmtfs_parse(const void *bytes, size_t length, K60RmtfsRequest *out);

/* Builds the response: a seven byte header, the four byte result TLV and,
 * when the reference answers with one, the value TLV (type 0x10). */
uint32_t k60_rmtfs_build_reply(uint8_t *out, size_t cap, uint16_t message,
    uint16_t transaction, uint16_t result, const void *value, size_t value_bytes);

/* Validates every scatter entry against one image and the shared window: the
 * offsets and lengths count 512-byte blocks, and the physical address must lie
 * inside the window the modem was given. Returns 0 when all entries fit. */
int k60_rmtfs_check_vectors(const K60RmtfsRequest *request, uint64_t image_bytes,
    uint64_t window_base, uint64_t window_bytes);

#endif /* K60_MODEM_RMTFS_H */
