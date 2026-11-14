/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* QRTR (the Qualcomm IPC Router) wire format, the read-only half: build one
 * HELLO and one NEW_LOOKUP, then fold every NEW_SERVER reply into a table.
 *
 * Everything here is pure: no SMEM, no GLINK, no allocation. The transport
 * (K60ModemLink.c) owns the bytes and hands each received datagram to
 * k60_qrtr_note(); a host test can therefore prove the encoding and the
 * parsing against recorded traffic without the device.
 *
 * Wire format (qrtr v1, little endian, 8 words = 32 bytes of header):
 *   version type from_node from_port confirm size to_node to_port
 * Control messages carry a 20 byte payload: command plus four words.
 * NEW_LOOKUP is type 10 (0x0a); the modem answers with one NEW_SERVER per
 * service, each of them 20 bytes with command == K60QrtrNewServer. */
#ifndef K60_MODEM_QRTR_H
#define K60_MODEM_QRTR_H
#include <stddef.h>
#include <stdint.h>

#define K60_QRTR_VERSION        1u
#define K60_QRTR_HEADER_BYTES   32u
#define K60_QRTR_CONTROL_BYTES  20u
#define K60_QRTR_LOOKUP_BYTES   (K60_QRTR_HEADER_BYTES + K60_QRTR_CONTROL_BYTES)
#define K60_QRTR_CONTROL_PORT   0xfffffffeu  /* the name service's port */
#define K60_QRTR_BROADCAST_NODE 0xffffffffu  /* "every node", what a lookup is sent to */
#define K60_QRTR_FIRST_PORT     0x4000u      /* first port we hand out */
#define K60_QRTR_MAX_SERVICES   64u
/* The five services that prove the modem's own name service answered:
 * 21 EFS, 1 WDS, 11 UIM, 3 NAS, 16 PDS (01-ANDROID-INVENTORY.md:409-454). */
#define K60_QRTR_WANTED_MASK    0x00u

enum {
	K60QrtrData = 1, K60QrtrHello = 2, K60QrtrBye = 3, K60QrtrNewServer = 4,
	K60QrtrDelServer = 5, K60QrtrDelClient = 6, K60QrtrResumeTx = 7,
	K60QrtrNewLookup = 10, K60QrtrDelLookup = 11,
};

enum { K60QrtrOk = 0, K60QrtrBadArg = -1, K60QrtrShort = -2, K60QrtrNoRoom = -3 };

typedef struct {
	uint32_t version, type, from_node, from_port;
	uint32_t confirm, size, to_node, to_port;
} K60QrtrHeader;

typedef struct {
	uint32_t command;
	uint32_t words[4];
} K60QrtrControl;

typedef struct {
	uint32_t service, instance, node, port;
} K60QrtrServer;

typedef struct {
	uint32_t services;      /* NEW_SERVER replies recorded (including repeats) */
	uint32_t from_node0;    /* of those, the ones that came from node 0 */
	uint32_t wanted;        /* of those, the ones whose service is EFS/WDS/UIM/NAS/PDS */
	uint32_t hello_acks;
	uint32_t malformed;     /* datagrams dropped before a control payload */
	K60QrtrServer table[K60_QRTR_MAX_SERVICES];
} K60QrtrState;

/* Builds the 52 byte datagram a lookup consists of. Returns its length or 0. */
uint32_t k60_qrtr_build_hello(uint8_t *out, size_t cap, uint32_t from_port);
uint32_t k60_qrtr_build_lookup(uint8_t *out, size_t cap, uint32_t from_port);
/* Splits one datagram: header, then the payload that follows it. */
int k60_qrtr_parse(const uint8_t *data, size_t length, K60QrtrHeader *header, const uint8_t **payload);
/* Folds one received datagram into the state. Unknown types are counted as
 * malformed only when they are too short to be a control message. */
int k60_qrtr_note(K60QrtrState *state, const uint8_t *data, size_t length);
/* True for the five services the completion criterion names. */
int k60_qrtr_wanted(uint32_t service);
/* 1 when a NEW_SERVER from node 0 named a wanted service: the judgement line. */
int k60_qrtr_verdict(const K60QrtrState *state);

#endif
