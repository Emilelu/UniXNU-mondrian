/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* QRTR (the Qualcomm IPC Router) wire format and QMI helpers: build HELLO,
 * NEW_LOOKUP and NEW_SERVER, fold replies into a table, answer the service
 * locator, and carry one QMI DMS GetRevision request/response.
 *
 * Everything here is pure: no SMEM, no GLINK, no allocation. The transport
 * (K60ModemLink.c) owns the bytes and hands each received datagram to
 * k60_qrtr_note(); a host test can therefore prove the encoding, the QMI
 * TLV parsing and the servloc answer against recorded traffic without the
 * device.
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
#define K60_QRTR_AP_NODE        1u           /* this AP's QRTR node id */
#define K60_QRTR_FIRST_PORT     0x4000u      /* first port we hand out */
#define K60_QRTR_MAX_SERVICES   64u
#define K60_QRTR_MAX_PACKET     512u
/* The five services that prove the modem's own name service answered:
 * 21 EFS, 1 WDS, 11 UIM, 3 NAS, 16 PDS (01-ANDROID-INVENTORY.md:409-454). */
#define K60_QRTR_WANTED_MASK    0x00u

/* Local endpoints this file serves. 0x100 is the service locator the modem
 * queries for the protection-domain table; 0x110 carries our DMS GetRevision
 * request and response. */
#define K60_QRTR_LOCATOR_PORT   0x100u
#define K60_QRTR_DMS_PORT       0x110u
#define K60_QRTR_DMS_SERVICE    2u
/* The modem registers its QMI services while it boots, before our GLINK
 * channel exists; Android's kernel nameserver catches those announcements and
 * a late channel does not. The inventory taken on this device puts DMS on
 * node 0 port 96, so that port is the fallback when nothing is announced. */
#define K60_QRTR_DMS_STATIC_PORT 96u
#define K60_QRTR_SERVLOC_SERVICE 0x40u
#define K60_QRTR_SERVLOC_INSTANCE 0x101u

#define K60_QMI_HEADER          7u
#define K60_QMI_REQUEST         0u
#define K60_QMI_RESPONSE        2u
#define K60_QMI_INDICATION      4u
#define K60_QMI_DMS_GET_REVISION 0x23u

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

/* One parsed QMI message: a seven byte header and the TLV region that
 * follows. All fields little endian, as libqmi defines them. */
typedef struct {
	uint8_t type;
	uint16_t transaction, message;
	const uint8_t *tlvs;
	uint32_t length;
} K60QmiMessage;

/* One protection-domain row of the service locator answer. The strings and
 * arrays must outlive the call; services is NULL when the domain has none. */
typedef struct {
	const char *domain;
	uint32_t instance;
	const char *const *services;
} K60PdDomain;

typedef struct {
	uint32_t services;      /* NEW_SERVER replies recorded (including repeats) */
	uint32_t remote_node;   /* learned from HELLO; broadcast until then */
	uint32_t from_node0;    /* of those, the ones that came from node 0 */
	uint32_t wanted;        /* of those, the ones whose service is EFS/WDS/UIM/NAS/PDS */
	uint32_t hello_acks;
	uint32_t malformed;     /* datagrams dropped before a control payload */
	K60QrtrServer table[K60_QRTR_MAX_SERVICES];
	/* DMS service 2 endpoint and its GetRevision exchange. */
	uint32_t dms_node, dms_port, dms_found;
	uint32_t dms_transaction, dms_sent, dms_answered, dms_errors;
	/* 1 once the request went to the fixed port the Android inventory saw. */
	uint32_t dms_static;
	uint32_t locator_requests;
	uint32_t revision_bytes;
	char revision[128];
} K60QrtrState;

/* Builds the 52 byte datagram a lookup consists of. Returns its length or 0.
 * Control messages come from node 1, port 0xfffffffe, exactly as Pong emits
 * them; HELLO goes to the broadcast node and LOOKUP to the learned modem. */
uint32_t k60_qrtr_build_hello(uint8_t *out, size_t cap);
uint32_t k60_qrtr_build_lookup(uint8_t *out, size_t cap, uint32_t to_node);
uint32_t k60_qrtr_build_lookup_service(uint8_t *out, size_t cap, uint32_t to_node,
    uint32_t service, uint32_t instance);
/* NEW_SERVER for one local service: announces where the AP listens. */
uint32_t k60_qrtr_build_new_server(uint8_t *out, size_t cap, uint32_t service,
    uint32_t instance, uint32_t to_node, uint32_t port);
/* DATA datagram; returns the padded on-wire length or 0. The header's size
 * field is the unpadded payload length. */
uint32_t k60_qrtr_build_data(uint8_t *out, size_t cap, uint32_t from_port,
    uint32_t to_node, uint32_t to_port, const uint8_t *payload, size_t length);
/* Splits one datagram: header, then the payload that follows it. */
int k60_qrtr_parse(const uint8_t *data, size_t length, K60QrtrHeader *header, const uint8_t **payload);
/* Folds one received datagram into the state. Unknown types are counted as
 * malformed only when they are too short to be a control message. */
int k60_qrtr_note(K60QrtrState *state, const uint8_t *data, size_t length);
/* True for the five services the completion criterion names. */
int k60_qrtr_wanted(uint32_t service);
/* 1 when a NEW_SERVER from node 0 named a wanted service: the judgement line. */
int k60_qrtr_verdict(const K60QrtrState *state);

/* QMI helpers. qcom_qmi_parse validates the seven byte header and bounds the
 * TLV region; qcom_qmi_tlv returns the value pointer for one type or NULL. */
int k60_qmi_parse(const uint8_t *data, uint32_t length, K60QmiMessage *message);
const uint8_t *k60_qmi_tlv(const K60QmiMessage *message, uint8_t type, uint32_t *size);
/* DMS GetRevision (service 2, message 0x23): a seven byte request with no
 * TLVs, and a parser for the response TLV 1 revision string. */
uint32_t k60_qmi_build_dms_revision(uint8_t *out, size_t cap, uint16_t transaction);
int k60_qmi_dms_revision(const uint8_t *data, uint32_t length, uint16_t transaction,
    char *out, size_t cap);
/* Answers a QMI service locator GET_DOMAIN_LIST request with the same QMI
 * response Pong sends (result, total, revision, domain list). */
uint32_t k60_qrtr_servloc_answer(const uint8_t *request, uint32_t length,
    uint8_t *out, uint32_t capacity);

#endif
