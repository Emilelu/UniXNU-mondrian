/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* The modem's GLINK edge: prepare the AP-owned SMP2P and GLINK items before
 * PAS starts, adopt the two SMEM FIFOs the modem and the APSS share, answer
 * the channel the modem opens for QRTR ("IPCRTR", the DT's
 * qcom,glink-channels), send one HELLO and one NEW_LOOKUP, and fold the
 * NEW_SERVER replies into K60ModemQrtr's table. Nothing here writes a modem
 * partition, an EFS item or an NV item: the bytes written are the transport
 * items themselves and the GLINK ring.
 *
 * Layout facts, all from the live DT (docs/research/cellular/02-DT-TRUTH.md):
 *   smem  0x80900000 + 0x200000   qcom,smem
 *   ipcc  0x0ed18000              mboxes = <&ipcc 2 0>
 *   glink edge qcom,remote-pid = <1>, transport "smem"
 *   channel "IPCRTR", intents 0x800x5 0x2000x3 0x4400x2
 * SMEM item ids 428 (our SMP2P), 478/479/480 (descriptor, our queue, its
 * queue) and 435 (the modem's SMP2P state) are the modem transport's, not
 * the ADSP's: the ADSP used 428/435 on its own partition, so this file reads
 * its own partition (host 0 <-> remote 1) and never touches the DSP's.
 *
 * Every line starts with K60MODEM, and the whole probe is inert unless
 * pong_modem is set to 2 or more. */
#include "K60ModemQrtr.h"
#include "K60Smem.h"
#include "QcomGlink.h"
#include "K60PmicRail.h"

/* QcomBaseband's C ABI (drivers/QcomBaseband/baseband/QcomBaseband.h). The
 * bridge is a separate component archive; keep the declarations here so this
 * file stays one patch hunk and does not depend on the archive's header path. */
extern int coachz_baseband_enabled(void);
extern void coachz_baseband_configure(void (*send)(uint32_t, uint32_t,
    uint32_t, const void *, uint32_t), void (*del_client)(uint32_t));
extern void coachz_baseband_new_server(uint32_t service,
    uint32_t version_instance, uint32_t node, uint32_t port);
extern void coachz_baseband_del_server(uint32_t service, uint32_t node,
    uint32_t port);
extern int coachz_baseband_qrtr(uint32_t dst_port, uint32_t src_node,
    uint32_t src_port, const void *body, uint32_t size);
extern void coachz_baseband_poll(void);
extern void coachz_baseband_report(unsigned second);
extern int coachz_modem_data_send(uint32_t mux, const uint8_t *ip,
    uint32_t length);
extern void coachz_modem_data_receiver(void (*receiver)(uint32_t mux,
    const uint8_t *ip, uint32_t length, uint32_t ip_version));

#ifndef K60_HOST_TEST

/* The XNU compile-record bootstrap pass links this object before any component
 * archive exists. Keep weak fallbacks so that pass links; the real link
 * force-loads libQcomBaseband.a and its strong definitions replace these. */
__attribute__((weak)) int
coachz_baseband_enabled(void)
{
	return 0;
}

__attribute__((weak)) void
coachz_baseband_configure(void (*send)(uint32_t, uint32_t, uint32_t,
    const void *, uint32_t), void (*del_client)(uint32_t))
{
	(void)send;
	(void)del_client;
}

__attribute__((weak)) void
coachz_baseband_new_server(uint32_t service, uint32_t version_instance,
    uint32_t node, uint32_t port)
{
	(void)service;
	(void)version_instance;
	(void)node;
	(void)port;
}

__attribute__((weak)) void
coachz_baseband_del_server(uint32_t service, uint32_t node, uint32_t port)
{
	(void)service;
	(void)node;
	(void)port;
}

__attribute__((weak)) int
coachz_baseband_qrtr(uint32_t dst_port, uint32_t src_node, uint32_t src_port,
    const void *body, uint32_t size)
{
	(void)dst_port;
	(void)src_node;
	(void)src_port;
	(void)body;
	(void)size;
	return 0;
}

__attribute__((weak)) void
coachz_baseband_poll(void)
{
}

__attribute__((weak)) void
coachz_baseband_report(unsigned second)
{
	(void)second;
}

#include <pexpert/pexpert.h>
#include <sys/systm.h>

/* osfmk/arm/machine_routines.h:703 (same declaration K60AdspBoot.c uses). */
extern vm_offset_t ml_io_map_unmappable(vm_offset_t phys, vm_size_t size, uint32_t flags);
extern void delay(int microseconds);

#define K60_MODEM_SMEM_BASE      0x80900000u
#define K60_MODEM_SMEM_BYTES     0x00200000u
#define K60_MODEM_SMEM_MUTEX_BASE 0x1f43000u
#define K60_MODEM_IPCC_BASE      0x0ed18000u
#define K60_MODEM_IPCC_CLIENT    2u
#define K60_MODEM_IPCC_SIGNAL    0u
#define K60_MODEM_IPCC_SEND      0x0cu

#define K60_MODEM_SMP2P_THEIRS   435u
#define K60_MODEM_SMP2P_OURS     428u
#define K60_MODEM_GLINK_DESC     478u
#define K60_MODEM_GLINK_OURS     479u
#define K60_MODEM_GLINK_THEIRS   480u
#define K60_MODEM_SMP2P_MAGIC    0x504d5324u
#define K60_MODEM_SMP2P_ITEM_WORDS (20u + 20u * 16u) / 4u
#define K60_MODEM_GLINK_TX_BYTES 0x4000u

/* Our receive intents: the DT asks for three groups (0x800x5, 0x2000x3,
 * 0x4400x2); QcomGlink carries one group per channel, so pick the largest
 * size and the largest count that fit its limits (4 local intents). */
#define K60_QRTR_INTENT_SIZE     0x4400u
#define K60_QRTR_INTENT_COUNT    4u
#define K60_QRTR_POLL_US         2000
#define K60_QRTR_POLLS           5000   /* ten seconds of verdict polling */
/* The modem firmware boots asynchronously after AUTH_AND_RESET. Pong keeps a
 * worker polling until it is ready; a single boot has only this window, so
 * allow thirty seconds before declaring the modem absent. */
#define K60_QRTR_READY_POLLS     15000  /* thirty seconds of readiness polling */

static QcomGlink k60_qrtr_link;
static QcomGlinkChannel *k60_qrtr_channel;
static uint8_t k60_qrtr_intents[K60_QRTR_INTENT_COUNT * K60_QRTR_INTENT_SIZE];
static K60QrtrState k60_qrtr_state;
static volatile uint8_t *k60_qrtr_ipcc;
static int k60_qrtr_up;
static int k60_qrtr_glink_ready;
static int k60_qrtr_hello_sent;
static int k60_qrtr_lookup_sent;
static int k60_qrtr_server_sent;
static int k60_qrtr_dms_requested;
static uint16_t k60_qrtr_dms_transaction;
static void (*k60_modem_data_receiver)(uint32_t mux, const uint8_t *ip,
    uint32_t length, uint32_t ip_version);
static unsigned k60_modem_data_drops;

#define K60_QRTR_REPLY_MAX 32u
struct K60QrtrReply {
	uint32_t from_port, node, port, length;
	uint8_t data[K60_QRTR_MAX_PACKET];
};
static struct K60QrtrReply k60_qrtr_replies[K60_QRTR_REPLY_MAX];
static unsigned k60_qrtr_reply_head, k60_qrtr_reply_count;

static void
k60_qrtr_kick(void *context)
{
	(void)context;
	if (k60_qrtr_ipcc == NULL) {
		return;
	}
	__asm__ volatile("dmb oshst" ::: "memory");
	*(volatile uint32_t *)(k60_qrtr_ipcc + K60_MODEM_IPCC_SEND) =
	    (K60_MODEM_IPCC_CLIENT << 16) | K60_MODEM_IPCC_SIGNAL;
	__asm__ volatile("dsb sy" ::: "memory");
}

static void
k60_qrtr_state_cb(void *context, QcomGlinkChannel *channel, int up)
{
	(void)context;
	(void)channel;
	k60_qrtr_up = up != 0;
	printf("K60MODEM qrtr: channel %s\n", up ? "up" : "down");
}

static int
k60_qrtr_queue_reply(uint32_t from_port, uint32_t node, uint32_t port,
    const uint8_t *payload, uint32_t length)
{
	struct K60QrtrReply *reply;

	if (k60_qrtr_reply_count >= K60_QRTR_REPLY_MAX ||
	    length > K60_QRTR_MAX_PACKET) {
		return -1;
	}
	reply = &k60_qrtr_replies[(k60_qrtr_reply_head + k60_qrtr_reply_count) %
	    K60_QRTR_REPLY_MAX];
	reply->from_port = from_port;
	reply->node = node;
	reply->port = port;
	reply->length = length;
	for (uint32_t i = 0; i < length; ++i) {
		reply->data[i] = payload[i];
	}
	++k60_qrtr_reply_count;
	return 0;
}

static int
k60_qrtr_send_data_packet(uint32_t from_port, uint32_t node, uint32_t port,
    const uint8_t *payload, uint32_t length)
{
	uint8_t packet[K60_QRTR_HEADER_BYTES + K60_QRTR_MAX_PACKET];
	uint32_t bytes;

	bytes = k60_qrtr_build_data(packet, sizeof(packet), from_port, node, port,
	    payload, length);
	if (bytes == 0) {
		return K60QrtrBadArg;
	}
	return qcom_glink_send(&k60_qrtr_link, k60_qrtr_channel, packet, bytes);
}

static int
k60_qrtr_flush_replies(void)
{
	while (k60_qrtr_reply_count != 0) {
		struct K60QrtrReply *reply = &k60_qrtr_replies[k60_qrtr_reply_head];
		const int rc = k60_qrtr_send_data_packet(reply->from_port, reply->node,
		    reply->port, reply->data, reply->length);

		if (rc == QcomGlinkAgain) {
			return 0;   /* keep it queued and retry on the next poll */
		}
		if (rc != QcomGlinkOk) {
			return rc;
		}
		k60_qrtr_reply_head = (k60_qrtr_reply_head + 1u) % K60_QRTR_REPLY_MAX;
		--k60_qrtr_reply_count;
	}
	return 0;
}

/* The QcomBaseband bridge hands back QMI replies for the clients it owns.
 * Queue them under the port the bridge named; the next poll loop flushes
 * them through the same GLINK channel as the locator and DMS answers. */
static void
k60_baseband_send(uint32_t local_port, uint32_t node, uint32_t port,
    const void *message, uint32_t length)
{
	if (k60_qrtr_queue_reply(local_port, node, port, message, length) != 0) {
		printf("K60MODEM baseband: reply dropped port=%#x len=%u\n",
		    local_port, length);
	}
}

static void
k60_baseband_del_client(uint32_t port)
{
	printf("K60MODEM baseband: client port %#x released\n", port);
}

/* K60 has no IPA/GSI data path yet. The control bridge can still enumerate
 * and publish AppleBaseband; the PDP data plane reports ENETDOWN until the
 * IPA v5.1 adapter exists. */
int
coachz_modem_data_send(uint32_t mux, const uint8_t *ip, uint32_t length)
{
	(void)ip;
	if (k60_modem_data_drops++ == 0) {
		printf("K60MODEM baseband: no IPA data path, dropping mux %u len %u\n",
		    mux, length);
	}
	return -50;   /* ENETDOWN */
}

void
coachz_modem_data_receiver(void (*receiver)(uint32_t mux, const uint8_t *ip,
    uint32_t length, uint32_t ip_version))
{
	k60_modem_data_receiver = receiver;
	printf("K60MODEM baseband: data receiver %s\n",
	    receiver != NULL ? "registered" : "cleared");
}

static void
k60_qrtr_receive_cb(void *context, QcomGlinkChannel *channel, const uint8_t *data, uint32_t length)
{
	K60QrtrHeader header;
	const uint8_t *payload = NULL;

	(void)context;
	(void)channel;
	if (k60_qrtr_parse(data, length, &header, &payload) != K60QrtrOk) {
		return;
	}
	if (header.type == K60QrtrData) {
		if (header.to_port == K60_QRTR_LOCATOR_PORT) {
			uint8_t answer[K60_QRTR_MAX_PACKET];
			uint32_t bytes;

			++k60_qrtr_state.locator_requests;
			bytes = k60_qrtr_servloc_answer(payload, header.size, answer,
			    sizeof(answer));
			if (bytes == 0 ||
			    k60_qrtr_queue_reply(K60_QRTR_LOCATOR_PORT, header.from_node,
			    header.from_port, answer, bytes) != 0) {
				printf("K60MODEM qrtr: locator answer dropped (%u bytes)\n", bytes);
			}
		} else if (header.to_port == K60_QRTR_DMS_PORT &&
		    header.from_node == k60_qrtr_state.dms_node &&
		    header.from_port == k60_qrtr_state.dms_port) {
			char revision[sizeof(k60_qrtr_state.revision)];
			const int bytes = k60_qmi_dms_revision(payload, header.size,
			    k60_qrtr_state.dms_transaction, revision, sizeof(revision));

			if (bytes > 0) {
				for (int i = 0; i <= bytes; ++i) {
					k60_qrtr_state.revision[i] = revision[i];
				}
				k60_qrtr_state.revision_bytes = (uint32_t)bytes;
				k60_qrtr_state.dms_answered = 1;
				printf("K60MODEM qrtr: dms revision %s\n", revision);
			} else {
				++k60_qrtr_state.dms_errors;
			}
		} else if (header.to_port == K60_QRTR_DMS_PORT) {
			++k60_qrtr_state.dms_errors;
		} else {
			/* Ports owned by the QcomBaseband control bridge (CBQ_PORT_BASE
			 * and above). The bridge copies what it needs; unknown ports
			 * simply return zero. */
			(void)coachz_baseband_qrtr(header.to_port, header.from_node,
			    header.from_port, payload, header.size);
		}
	}
	if (header.type == K60QrtrNewServer && header.size == K60_QRTR_CONTROL_BYTES) {
		const uint32_t service = (uint32_t)payload[4] | (uint32_t)payload[5] << 8 |
		    (uint32_t)payload[6] << 16 | (uint32_t)payload[7] << 24;
		const uint32_t instance = (uint32_t)payload[8] | (uint32_t)payload[9] << 8 |
		    (uint32_t)payload[10] << 16 | (uint32_t)payload[11] << 24;
		const uint32_t node = (uint32_t)payload[12] | (uint32_t)payload[13] << 8 |
		    (uint32_t)payload[14] << 16 | (uint32_t)payload[15] << 24;
		const uint32_t port = (uint32_t)payload[16] | (uint32_t)payload[17] << 8 |
		    (uint32_t)payload[18] << 16 | (uint32_t)payload[19] << 24;

		printf("K60MODEM qrtr: service %u (%#x) instance %u node %u port %u\n",
		    service, service, instance, node, port);
		coachz_baseband_new_server(service, instance, node, port);
	}
	if (header.type == K60QrtrDelServer && header.size == K60_QRTR_CONTROL_BYTES) {
		const uint32_t service = (uint32_t)payload[4] | (uint32_t)payload[5] << 8 |
		    (uint32_t)payload[6] << 16 | (uint32_t)payload[7] << 24;
		const uint32_t node = (uint32_t)payload[12] | (uint32_t)payload[13] << 8 |
		    (uint32_t)payload[14] << 16 | (uint32_t)payload[15] << 24;
		const uint32_t port = (uint32_t)payload[16] | (uint32_t)payload[17] << 8 |
		    (uint32_t)payload[18] << 16 | (uint32_t)payload[19] << 24;

		printf("K60MODEM qrtr: service %u (%#x) removed node %u port %u\n",
		    service, service, node, port);
		coachz_baseband_del_server(service, node, port);
	}
	(void)k60_qrtr_note(&k60_qrtr_state, data, length);
}

/* SMP2P outbound item: the modem's boot firmware expects the AP's
 * "master-kernel" entry before PAS_AUTH_AND_RESET. Pong allocates item 428
 * (340 bytes), item 478 (32-byte GLINK descriptor) and item 479 (16 KiB TX
 * FIFO) after INIT_IMAGE and before MEM_SETUP; we do the same so a cold boot
 * starts from an AP-owned, fresh transport instead of whatever an Android
 * epoch left behind. */
static void
k60_smp2p_barrier(void)
{
	__asm__ volatile("dmb oshst" ::: "memory");
}

static void
k60_smp2p_init_out(volatile uint32_t *out)
{
	unsigned i;

	for (i = 0; i < K60_MODEM_SMP2P_ITEM_WORDS; i++) {
		out[i] = 0;
	}
	k60_smp2p_barrier();
	out[0] = K60_MODEM_SMP2P_MAGIC;
	out[2] = 0u | (uint32_t)1u << 16;  /* local pid 0, remote pid 1 */
	out[3] = 16u;                      /* total entries, valid entries 0 */
	k60_smp2p_barrier();
	out[1] = 1u | (1u << 8);           /* version 1, SSR ack feature */
	k60_smp2p_barrier();
}

static int
k60_smp2p_add_entry(volatile uint32_t *out, const char *name)
{
	const uint32_t valid = out[3] >> 16;
	volatile uint32_t *entry;
	unsigned i;

	if (valid >= 16u) {
		return -1;
	}
	entry = out + 5u + 5u * valid;
	for (i = 0; i < 4; i++) {
		entry[i] = 0;
	}
	for (i = 0; i < 16u && name[i] != '\0'; i++) {
		entry[i / 4u] |= (uint32_t)(uint8_t)name[i] << (8u * (i % 4u));
	}
	entry[4] = 0;
	k60_smp2p_barrier();
	out[3] = 16u | (valid + 1u) << 16;
	k60_smp2p_barrier();
	return (int)valid;
}

static int
k60_transport_item(K60Smem *smem, K60SmemPartition *partition, uint16_t id,
    uint32_t bytes, uint32_t *offset, uint32_t *size)
{
	int rc = k60_smem_alloc(smem, partition, id, bytes, offset, size);

	if (rc == K60SmemExists) {
		rc = k60_smem_find(smem, partition, id, offset, size);
	}
	if (rc != K60SmemOk) {
		return rc;
	}
	if (*size < bytes) {
		return K60SmemBadPartition;
	}
	return K60SmemOk;
}

/* ---- modem power: AOP QMP load_state and cx/mss/xo RPMh votes ---------- */

#define K60_MODEM_AOSS_BASE       0x0c300000u
#define K60_MODEM_AOSS_BYTES      0x00001000u
#define K60_MODEM_QMP_RAM_BYTES   0x00000400u
#define K60_MODEM_AOP_SEND        0x0cu

#define K60_MODEM_QMP_DESC_MAGIC          0x0u
#define K60_MODEM_QMP_DESC_VERSION        0x4u
#define K60_MODEM_QMP_DESC_UCORE_LINK     0x0cu
#define K60_MODEM_QMP_DESC_UCORE_LINK_ACK 0x10u
#define K60_MODEM_QMP_DESC_UCORE_CH       0x14u
#define K60_MODEM_QMP_DESC_UCORE_CH_ACK   0x18u
#define K60_MODEM_QMP_DESC_MCORE_LINK     0x24u
#define K60_MODEM_QMP_DESC_MCORE_LINK_ACK 0x28u
#define K60_MODEM_QMP_DESC_MCORE_CH       0x2cu
#define K60_MODEM_QMP_DESC_MCORE_CH_ACK   0x30u
#define K60_MODEM_QMP_DESC_MBOX_SIZE      0x34u
#define K60_MODEM_QMP_DESC_MBOX_OFFSET    0x38u
#define K60_MODEM_QMP_MAGIC               0x4d41494cu /* "MAIL" */
#define K60_MODEM_QMP_VERSION             1u
#define K60_MODEM_QMP_STATE_UP            0xffffu
#define K60_MODEM_QMP_MSG_BYTES           100u
#define K60_MODEM_QMP_WORDS               (K60_MODEM_QMP_MSG_BYTES / 4u)

#define K60_MODEM_RSC_DRV_CONTROL  0x00u
#define K60_MODEM_RSC_IRQ_STATUS   0x04u
#define K60_MODEM_RSC_IRQ_CLEAR    0x08u
#define K60_MODEM_RSC_CAPS         0x0cu
#define K60_MODEM_TCS_BASE         0xd00u
#define K60_MODEM_TCS_STRIDE       672u
#define K60_MODEM_TCS4             (K60_MODEM_TCS_BASE + 4u * K60_MODEM_TCS_STRIDE)
#define K60_MODEM_TCS3             (K60_MODEM_TCS_BASE + 3u * K60_MODEM_TCS_STRIDE)
#define K60_MODEM_RSC_MSGID        0x10108u
#define K60_MODEM_RSC_IRQ_DONE     (1u << 4)
#define K60_MODEM_RSC_CMD_DONE     0x10100u
#define K60_MODEM_RSC_CTRL_TCS     (1u << 4)

static uint32_t
k60_modem_rd32(const volatile uint8_t *base, size_t at)
{
	return *(volatile uint32_t *)(base + at);
}

static void
k60_modem_wr32(volatile uint8_t *base, size_t at, uint32_t value)
{
	*(volatile uint32_t *)(base + at) = value;
	/* Match PongPlatformResources::wr: do not let a posted MMIO write
	 * race the immediate control/IRQ readbacks below. */
	__asm__ volatile("dsb oshst" ::: "memory");
}

static void
k60_modem_fence(void)
{
	__asm__ volatile("dsb sy" ::: "memory");
}

static void
k60_modem_spin(void)
{
	__asm__ volatile("yield" ::: "memory");
}

static int
k60_modem_wait_word(const volatile uint8_t *base, size_t at, uint32_t mask,
    uint32_t value, unsigned tries)
{
	unsigned i;

	for (i = 0; i < tries; i++) {
		if ((k60_modem_rd32(base, at) & mask) == value) {
			return 0;
		}
		delay(10);
	}
	return -1;
}

static void
k60_modem_aop_kick(volatile uint8_t *ipcc)
{
	/* QCOM_IPCC_CLIENT_AOP 0 / QCOM_IPCC_SIGNAL_GLINK_QMP 0. */
	k60_modem_fence();
	*(volatile uint32_t *)(ipcc + K60_MODEM_AOP_SEND) = 0;
	k60_modem_fence();
}

static volatile uint8_t *
k60_modem_map(uint64_t physical, size_t bytes)
{
	vm_offset_t va = ml_io_map_unmappable((vm_offset_t)physical,
	    (vm_size_t)bytes, 0x7);

	return (volatile uint8_t *)(uintptr_t)va;
}

/* The QMP descriptor lives in the first 0x400 bytes of AOSS. Its message box
 * is a word offset plus a byte length; both are read back and bounds-checked
 * before any word is written. */
static int
k60_modem_qmp_open(volatile uint8_t *aoss, volatile uint8_t *ipcc, uint32_t *box_out)
{
	volatile uint8_t *d = aoss;
	const uint32_t box = k60_modem_rd32(d, K60_MODEM_QMP_DESC_MBOX_OFFSET);
	const uint32_t bytes = k60_modem_rd32(d, K60_MODEM_QMP_DESC_MBOX_SIZE);
	unsigned phase;

	if (k60_modem_rd32(d, K60_MODEM_QMP_DESC_MAGIC) != K60_MODEM_QMP_MAGIC ||
	    k60_modem_rd32(d, K60_MODEM_QMP_DESC_VERSION) != K60_MODEM_QMP_VERSION) {
		return -1;
	}
	if ((box & 3u) != 0 || box < 0x3cu ||
	    bytes < K60_MODEM_QMP_MSG_BYTES + 4u ||
	    bytes > K60_MODEM_QMP_RAM_BYTES || box > bytes ||
	    bytes - box < K60_MODEM_QMP_MSG_BYTES + 4u) {
		return -1;
	}
	*box_out = box;
	if (k60_modem_rd32(d, K60_MODEM_QMP_DESC_MCORE_LINK) == K60_MODEM_QMP_STATE_UP &&
	    k60_modem_rd32(d, K60_MODEM_QMP_DESC_MCORE_LINK_ACK) == K60_MODEM_QMP_STATE_UP &&
	    k60_modem_rd32(d, K60_MODEM_QMP_DESC_MCORE_CH) == K60_MODEM_QMP_STATE_UP &&
	    k60_modem_rd32(d, K60_MODEM_QMP_DESC_UCORE_CH) == K60_MODEM_QMP_STATE_UP &&
	    k60_modem_rd32(d, K60_MODEM_QMP_DESC_MCORE_CH_ACK) == K60_MODEM_QMP_STATE_UP) {
		return 0;
	}
	for (phase = 0; phase < 4; phase++) {
		if (k60_modem_rd32(d, K60_MODEM_QMP_DESC_MCORE_LINK) != K60_MODEM_QMP_STATE_UP ||
		    k60_modem_rd32(d, K60_MODEM_QMP_DESC_MCORE_LINK_ACK) != K60_MODEM_QMP_STATE_UP) {
			k60_modem_wr32(d, K60_MODEM_QMP_DESC_UCORE_LINK_ACK,
			    k60_modem_rd32(d, K60_MODEM_QMP_DESC_UCORE_LINK));
			k60_modem_wr32(d, K60_MODEM_QMP_DESC_MCORE_LINK, K60_MODEM_QMP_STATE_UP);
			k60_modem_fence();
			k60_modem_aop_kick(ipcc);
			if (k60_modem_wait_word(d, K60_MODEM_QMP_DESC_MCORE_LINK_ACK,
			    0xffffu, K60_MODEM_QMP_STATE_UP, 100000)) {
				continue;
			}
		}
		k60_modem_wr32(d, K60_MODEM_QMP_DESC_MCORE_CH, K60_MODEM_QMP_STATE_UP);
		k60_modem_fence();
		k60_modem_aop_kick(ipcc);
		if (k60_modem_wait_word(d, K60_MODEM_QMP_DESC_UCORE_CH,
		    0xffffu, K60_MODEM_QMP_STATE_UP, 100000)) {
			continue;
		}
		k60_modem_wr32(d, K60_MODEM_QMP_DESC_UCORE_CH_ACK, K60_MODEM_QMP_STATE_UP);
		k60_modem_fence();
		k60_modem_aop_kick(ipcc);
		if (k60_modem_wait_word(d, K60_MODEM_QMP_DESC_MCORE_CH_ACK,
		    0xffffu, K60_MODEM_QMP_STATE_UP, 100000)) {
			continue;
		}
		return 0;
	}
	return -1;
}

static int
k60_modem_qmp_load_state(volatile uint8_t *aoss, volatile uint8_t *ipcc, uint32_t box)
{
	volatile uint8_t *mailbox = aoss + box;
	static const char msg[] = "{class: image, res: load_state, name: modem, val: on}";
	uint32_t words[K60_MODEM_QMP_WORDS] = { 0 };
	const size_t n = sizeof(msg) - 1u;
	size_t i;
	unsigned w;

	if (n + 1u > K60_MODEM_QMP_MSG_BYTES) {
		return -1;
	}
	for (i = 0; i < n; i++) {
		words[i / 4u] |= (uint32_t)(uint8_t)msg[i] << (8u * (i % 4u));
	}
	if (k60_modem_wait_word(aoss, box, 0xffffffffu, 0, 100000)) {
		return -1;
	}
	for (w = 0; w < K60_MODEM_QMP_WORDS; w++) {
		k60_modem_wr32(mailbox, 4u + w * 4u, words[w]);
	}
	k60_modem_fence();
	k60_modem_wr32(mailbox, 0, K60_MODEM_QMP_MSG_BYTES);
	k60_modem_fence();
	k60_modem_aop_kick(ipcc);
	return k60_modem_wait_word(aoss, box, 0xffffffffu, 0, 100000);
}

static int
k60_modem_find_rail(volatile uint8_t *db, const char *name, uint32_t level,
    K60RpmhResource *res, uint32_t *index)
{
	int rc = k60_cmd_db_find((const uint8_t *)(const void *)db,
	    K60_CMD_DB_BYTES, name, res);

	if (rc != K60RpmhOk) {
		return rc;
	}
	return k60_rpmh_level_index(res, level, index);
}

static int
k60_modem_tcs_conflict(const volatile uint8_t *rsc, const K60RscLayout *l,
    uint32_t tcs, uint32_t capacity, uint32_t address)
{
	uint32_t enable = k60_modem_rd32(rsc, tcs + l->cmd_enable);
	uint32_t i;

	for (i = 0; i < capacity && i < 16u; i++) {
		if ((enable & (1u << i)) != 0 &&
		    k60_modem_rd32(rsc, tcs + (size_t)i * l->cmd_stride + l->cmd_addr) == address) {
			return -1;
		}
	}
	return 0;
}

/* One RPMh active-only command into TCS4, the sequence that powers the modem
 * rails on this board. The TCS trigger lives at RSC_DRV + 0xd00; completion
 * status and IRQ clear live at +0xd04 and +0xd08, not at the RSC DRV_ID page.
 * Readback happens after wait_for_cmpl/cmd_enable, matching Pong rawVote. */
static int
k60_modem_vote_tcs4(volatile uint8_t *rsc, const K60RscLayout *l,
    uint32_t address, uint32_t value, uint32_t capacity)
{
	const size_t base = K60_MODEM_TCS4;
	uint32_t control;
	uint32_t progressed = 0;
	unsigned i;
	int rc = -1;

	if (k60_modem_rd32(rsc, K60_MODEM_TCS3 + l->status) == 0 &&
	    k60_modem_tcs_conflict(rsc, l, K60_MODEM_TCS3, capacity, address)) {
		return -1;
	}
	k60_modem_wr32(rsc, K60_MODEM_TCS_BASE,
	    k60_modem_rd32(rsc, K60_MODEM_TCS_BASE) & ~K60_MODEM_RSC_CTRL_TCS);
	control = k60_modem_rd32(rsc, base + l->control) & ~(1u << 24);
	k60_modem_wr32(rsc, base + l->control, control);
	if (k60_modem_wait_word(rsc, base + l->control, 0xffffffffu, control, 1000)) {
		return -1;
	}
	control &= ~(1u << 16);
	k60_modem_wr32(rsc, base + l->control, control);
	if (k60_modem_wait_word(rsc, base + l->control, 0xffffffffu, control, 1000)) {
		return -1;
	}
	k60_modem_wr32(rsc, base + l->cmd_enable, 0);
	k60_modem_wr32(rsc, K60_MODEM_TCS_BASE + l->irq_clear, K60_MODEM_RSC_IRQ_DONE);
	if (k60_modem_wait_word(rsc, K60_MODEM_TCS_BASE + l->irq_status,
	    K60_MODEM_RSC_IRQ_DONE, 0, 1000)) {
		return -1;
	}
	k60_modem_wr32(rsc, base + l->cmd_msgid, K60_MODEM_RSC_MSGID);
	k60_modem_wr32(rsc, base + l->cmd_addr, address);
	k60_modem_wr32(rsc, base + l->cmd_data, value);
	k60_modem_wr32(rsc, base + l->wait_for_cmpl, 1);
	k60_modem_fence();
	k60_modem_wr32(rsc, base + l->cmd_enable, 1);
	if (k60_modem_rd32(rsc, base + l->cmd_addr) != address ||
	    k60_modem_rd32(rsc, base + l->cmd_data) != value) {
		goto cleanup;
	}
	k60_modem_wr32(rsc, base + l->control, 1u << 16);
	k60_modem_fence();
	if (k60_modem_wait_word(rsc, base + l->control, 0xffffffffu, 1u << 16, 1000)) {
		goto cleanup;
	}
	k60_modem_fence();
	k60_modem_wr32(rsc, base + l->control, (1u << 16) | (1u << 24));
	for (i = 0; i < 200000u; i++) {
		const uint32_t status = k60_modem_rd32(rsc, base + l->cmd_data + 4u);
		const uint32_t idle = k60_modem_rd32(rsc, base + l->status);

		if ((status & K60_MODEM_RSC_CMD_DONE) == K60_MODEM_RSC_CMD_DONE && idle &&
		    k60_modem_rd32(rsc, base + l->cmd_enable) == 1u &&
		    k60_modem_rd32(rsc, base + l->cmd_addr) == address &&
		    k60_modem_rd32(rsc, base + l->cmd_data) == value &&
		    (progressed || (k60_modem_rd32(rsc, K60_MODEM_TCS_BASE + l->irq_status) &
		    K60_MODEM_RSC_IRQ_DONE))) {
			rc = 0;
			break;
		}
		if ((status & K60_MODEM_RSC_CMD_DONE) != K60_MODEM_RSC_CMD_DONE || !idle) {
			progressed = 1;
		}
		if ((i & 0x0fu) == 0) {
			delay(10);
		} else {
			k60_modem_spin();
		}
	}
cleanup:
	k60_modem_wr32(rsc, base + l->cmd_enable, 0);
	k60_modem_wr32(rsc, K60_MODEM_TCS_BASE + l->irq_clear, K60_MODEM_RSC_IRQ_DONE);
	control = k60_modem_rd32(rsc, base + l->control) & ~(1u << 24);
	k60_modem_wr32(rsc, base + l->control, control);
	if (k60_modem_wait_word(rsc, base + l->control, 0xffffffffu, control, 1000)) {
		return -1;
	}
	k60_modem_fence();
	return rc;
}

/* Send AOP the modem load_state message, then vote the three rails Pong votes
 * before PAS starts: cx.lvl and mss.lvl at corner 384, xo.lvl at 3. */
int
k60_modem_rails_vote(void)
{
	volatile uint8_t *aoss = NULL, *ipcc = NULL, *db = NULL, *rsc = NULL;
	K60RpmhResource cx = { 0 }, mss = { 0 }, xo = { 0 };
	uint32_t cx_index = 0, mss_index = 0, box = 0;
	unsigned attempt;
	uint32_t drv, caps, version, capacity;
	K60RscLayout layout;
	const char *why = "aoss map";

	aoss = k60_modem_map(K60_MODEM_AOSS_BASE, K60_MODEM_AOSS_BYTES);
	if (aoss == NULL) {
		goto fail;
	}
	why = "ipcc map";
	ipcc = k60_modem_map(K60_MODEM_IPCC_BASE, 0x1000);
	if (ipcc == NULL) {
		goto fail;
	}
	why = "qmp open";
	/* qmp_open can spend up to 12 s in its four handshake phases; ten
	 * attempts bound the wait at about two minutes instead of two hours. */
	for (attempt = 0; attempt < 10u; attempt++) {
		if (k60_modem_qmp_open(aoss, ipcc, &box) == 0) {
			why = "qmp load_state";
			if (k60_modem_qmp_load_state(aoss, ipcc, box) == 0) {
				break;
			}
		}
		delay(100000);
	}
	if (attempt == 10u) {
		why = "qmp open/load_state";
		goto fail;
	}
	why = "cmd-db map";
	db = k60_modem_map(K60_CMD_DB_PHYS, K60_CMD_DB_BYTES);
	if (db == NULL) {
		goto fail;
	}
	why = "RSC map";
	rsc = k60_modem_map(K60_RSC_DRV2_PHYS, K60_RSC_BYTES);
	if (rsc == NULL) {
		goto fail;
	}
	drv = k60_modem_rd32(rsc, 0);
	caps = k60_modem_rd32(rsc, K60_MODEM_RSC_CAPS);
	version = (drv >> 16) & 0xffu;
	if (version != 2u) {
		why = "RSC version";
		goto fail;
	}
	layout = k60_rsc_layout(drv);
	capacity = (caps >> 27) & 0x1fu;
	if (((caps >> 12) & 0x3fu) < 8u || capacity < 1u) {
		why = "RSC caps";
		goto fail;
	}
	if (k60_modem_rd32(rsc, K60_MODEM_TCS4 + layout.status) == 0) {
		why = "TCS4 unavailable";
		goto fail;
	}
	if (k60_modem_find_rail(db, "cx.lvl", 384u, &cx, &cx_index) != K60RpmhOk) {
		why = "cx.lvl";
		goto fail;
	}
	if (k60_modem_find_rail(db, "mss.lvl", 384u, &mss, &mss_index) != K60RpmhOk) {
		why = "mss.lvl";
		goto fail;
	}
	/* Pong votes xo.lvl as the literal 3 and never converts it through the
	 * cmd-db level table (PongModemRuntime.cpp:159); the XOB resource has no
	 * level table, so an index conversion here would either fail or vote a
	 * different value than the proven path. */
	if (k60_cmd_db_find((const uint8_t *)(const void *)db, K60_CMD_DB_BYTES,
	    "xo.lvl", &xo) != K60RpmhOk) {
		why = "xo.lvl";
		goto fail;
	}
	why = "cx.lvl vote";
	if (k60_modem_vote_tcs4(rsc, &layout, cx.address, cx_index, capacity) != 0) {
		goto fail;
	}
	why = "mss.lvl vote";
	if (k60_modem_vote_tcs4(rsc, &layout, mss.address, mss_index, capacity) != 0) {
		goto fail;
	}
	why = "xo.lvl vote";
	if (k60_modem_vote_tcs4(rsc, &layout, xo.address, 3u, capacity) != 0) {
		goto fail;
	}
	printf("K60MODEM power ok cx=%#x/%u mss=%#x/%u xo=%#x/%u\n",
	    cx.address, cx_index, mss.address, mss_index, xo.address, 3u);
	return 0;

fail:
	printf("K60MODEM power failed: %s\n", why);
	return -1;
}

static int k60_qrtr_modem_ready(volatile uint8_t *smem, uint32_t offset,
    uint32_t bytes, uint32_t *seen);
static int k60_modem_glink_start(volatile uint8_t *window, uint32_t desc_offset,
    uint32_t desc_bytes, uint32_t tx_offset, uint32_t tx_bytes,
    uint32_t rx_offset, uint32_t rx_bytes);

int
k60_modem_transport_prepare(void)
{
	K60Smem smem;
	K60SmemPartition partition;
	const uint16_t ids[3] = { K60_MODEM_SMP2P_OURS, K60_MODEM_GLINK_DESC,
	    K60_MODEM_GLINK_OURS };
	const uint32_t bytes[3] = { K60_MODEM_SMP2P_ITEM_WORDS * 4u, 32u,
	    K60_MODEM_GLINK_TX_BYTES };
	uint32_t offsets[3] = { 0, 0, 0 }, sizes[3] = { 0, 0, 0 };
	uint32_t guard_offset = 0, guard_size = 0, guard_seen = 0;
	volatile uint8_t *window, *mutex;
	volatile uint32_t *out, *desc;
	unsigned i;
	int rc, locked = 0;

	window = (volatile uint8_t *)ml_io_map_unmappable(K60_MODEM_SMEM_BASE,
	    K60_MODEM_SMEM_BYTES, 0x7);
	if (window == NULL) {
		printf("K60MODEM transport: smem map failed at %#x\n",
		    K60_MODEM_SMEM_BASE);
		return -1;
	}
	smem.base = window;
	smem.size = K60_MODEM_SMEM_BYTES;
	rc = k60_smem_partition(&smem, 0, 1, &partition);
	if (rc != K60SmemOk) {
		printf("K60MODEM transport: no modem smem partition rc=%d\n", rc);
		return rc;
	}
	/* Pong refuses to reset a modem that still owns the inbound SMP2P
	 * block. Read the old 435 state before touching 428 or the GLINK
	 * descriptor so a stale modem is never silently overwritten. */
	if (k60_smem_find(&smem, &partition, K60_MODEM_SMP2P_THEIRS,
	    &guard_offset, &guard_size) == K60SmemOk &&
	    k60_qrtr_modem_ready(window, guard_offset, guard_size, &guard_seen)) {
		printf("K60MODEM transport: modem still owns smp2p entries=%u, refusing reset\n",
		    guard_seen);
		return -16;
	}
	/* The SMEM allocator is shared with the ADSP; take the TCSR SMEM
	 * mutex 0x1f43000 exactly as Pong does around item allocation. */
	mutex = (volatile uint8_t *)ml_io_map_unmappable(
	    K60_MODEM_SMEM_MUTEX_BASE, 0x1000, 0x7);
	if (mutex == NULL) {
		printf("K60MODEM transport: smem mutex map failed\n");
		return -1;
	}
	for (i = 0; i < 1000; i++) {
		*(volatile uint32_t *)mutex = 1;
		k60_modem_fence();
		if (*(volatile uint32_t *)mutex == 1u) {
			locked = 1;
			break;
		}
		delay(10);
	}
	if (!locked) {
		printf("K60MODEM transport: smem mutex timeout\n");
		return -1;
	}
	for (i = 0; i < 3; i++) {
		rc = k60_transport_item(&smem, &partition, ids[i], bytes[i],
		    &offsets[i], &sizes[i]);
		if (rc != K60SmemOk) {
			*(volatile uint32_t *)mutex = 0;
			k60_modem_fence();
			printf("K60MODEM transport: item %u unavailable rc=%d\n",
			    ids[i], rc);
			return rc;
		}
	}
	*(volatile uint32_t *)mutex = 0;
	k60_modem_fence();
	out = (volatile uint32_t *)(window + offsets[0]);
	k60_smp2p_init_out(out);
	if (k60_smp2p_add_entry(out, "master-kernel") < 0 ||
	    k60_smp2p_add_entry(out, "ipa") < 0) {
		printf("K60MODEM transport: smp2p entries full\n");
		return -1;
	}
	desc = (volatile uint32_t *)(window + offsets[1]);
	/* Only the AP-owned indices are reset; desc[0]/desc[3] belong to the
	 * remote and must stay intact so a live FIFO is never mistaken for fresh. */
	desc[1] = 0;
	desc[2] = 0;
	k60_smp2p_barrier();
	{
		uint32_t rx_offset = 0, rx_size = 0;

		if (k60_smem_find(&smem, &partition, K60_MODEM_GLINK_THEIRS,
		    &rx_offset, &rx_size) == K60SmemOk) {
			k60_qrtr_ipcc = (volatile uint8_t *)ml_io_map_unmappable(
			    K60_MODEM_IPCC_BASE, 0x1000, 0x7);
			if (k60_qrtr_ipcc == NULL) {
				printf("K60MODEM transport: ipcc map failed\n");
				return -1;
			}
			rc = k60_modem_glink_start(window, offsets[1], sizes[1],
			    offsets[2], sizes[2], rx_offset, rx_size);
			if (rc != 0) {
				printf("K60MODEM transport: glink init rc=%d\n", rc);
				return rc;
			}
		} else {
			printf("K60MODEM transport: remote glink fifo absent, defer IPCRTR\n");
		}
	}
	printf("K60MODEM transport ok smp2p=%#x/%u desc=%#x/%u tx=%#x/%u\n",
	    offsets[0], sizes[0], offsets[1], sizes[1], offsets[2], sizes[2]);
	return 0;
}

/* True when the modem's SMP2P block says the modem is up and not fatal. */
static int
k60_qrtr_modem_ready(volatile uint8_t *smem, uint32_t offset, uint32_t bytes, uint32_t *seen)
{
	volatile uint32_t *words = (volatile uint32_t *)(smem + offset);
	uint32_t count, total, valid, i, word;

	if (bytes < 20 || words[0] != K60_MODEM_SMP2P_MAGIC || (words[1] & 0xffu) != 1u) {
		return 0;
	}
	if (words[2] != 1u) {   /* local processor id: 1 is the modem */
		return 0;
	}
	count = words[3];
	total = count & 0xffffu;
	valid = count >> 16;
	if (total > 16 || valid > total || 20u + valid * 20u > bytes) {
		return 0;
	}
	*seen = valid;
	for (i = 0; i < valid; i++) {
		const volatile uint32_t *entry = words + 5 + i * 5;
		const uint32_t state = entry[4];
		const uint32_t name[4] = {entry[0], entry[1], entry[2], entry[3]};
		static const char wanted[16] = "slave-kernel";
		int same = 1;
		unsigned b;

		for (word = 0; word < 4; word++) {
			for (b = 0; b < 4; b++) {
				if ((uint8_t)(name[word] >> (b * 8)) != (uint8_t)wanted[word * 4 + b]) {
					same = 0;
				}
			}
		}
		if (same) {
			return (state & 2u) != 0 && (state & 1u) == 0;
		}
	}
	return 0;
}

/* Read-only guard used by k60_modem_bring_up before it copies an image or
 * touches PAS. Pong refuses a stale modem at item 435 before PAS_INIT_IMAGE. */
int
k60_modem_transport_stale(void)
{
	K60Smem smem;
	K60SmemPartition partition;
	uint32_t offset = 0, size = 0, seen = 0;
	volatile uint8_t *window;
	int rc;

	window = (volatile uint8_t *)ml_io_map_unmappable(K60_MODEM_SMEM_BASE,
	    K60_MODEM_SMEM_BYTES, 0x7);
	if (window == NULL) {
		printf("K60MODEM stale check: smem map failed\n");
		return -1;
	}
	smem.base = window;
	smem.size = K60_MODEM_SMEM_BYTES;
	rc = k60_smem_partition(&smem, 0, 1, &partition);
	if (rc != K60SmemOk) {
		printf("K60MODEM stale check: no modem smem partition rc=%d\n", rc);
		return -1;
	}
	rc = k60_smem_find(&smem, &partition, K60_MODEM_SMP2P_THEIRS, &offset, &size);
	if (rc == K60SmemOk && k60_qrtr_modem_ready(window, offset, size, &seen)) {
		printf("K60MODEM stale check: modem still owns smp2p entries=%u, refusing reset\n", seen);
		return -16;
	}
	return 0;
}

/* Adopt the AP-owned GLINK pair and open IPCRTR as the initiator. Pong does
 * this after PAS_INIT_IMAGE and before PAS_MEM_SETUP, not after AUTH. */
static int
k60_modem_glink_start(volatile uint8_t *window, uint32_t desc_offset,
    uint32_t desc_bytes, uint32_t tx_offset, uint32_t tx_bytes,
    uint32_t rx_offset, uint32_t rx_bytes)
{
	volatile uint32_t *desc;
	QcomGlinkFifo tx, rx;
	const QcomGlinkClient callbacks = {k60_qrtr_state_cb, k60_qrtr_receive_cb};
	int rc;

	if (desc_bytes != 32 || tx_bytes < 1024 || rx_bytes < 1024) {
		printf("K60MODEM glink: geometry wrong desc=%u tx=%u rx=%u\n",
		    desc_bytes, tx_bytes, rx_bytes);
		return -1;
	}
	desc = (volatile uint32_t *)(window + desc_offset);
	/* The AP-owned indices are cleared by transport_prepare after the item
	 * 435 stale check; this function no longer pretends to gate freshness. */
	tx.head = &desc[1];
	tx.tail = &desc[0];
	tx.data = (volatile uint8_t *)(window + tx_offset);
	tx.length = tx_bytes;
	rx.head = &desc[3];
	rx.tail = &desc[2];
	rx.data = (volatile uint8_t *)(window + rx_offset);
	rx.length = rx_bytes;
	rc = qcom_glink_adopt(&k60_qrtr_link, tx, rx, k60_qrtr_kick, NULL);
	if (rc != QcomGlinkOk) {
		printf("K60MODEM glink: adopt rc=%d\n", rc);
		return rc;
	}
	k60_qrtr_channel = qcom_glink_channel(&k60_qrtr_link, "IPCRTR",
	    K60_QRTR_INTENT_SIZE, K60_QRTR_INTENT_COUNT, k60_qrtr_intents,
	    &callbacks, NULL, 1);
	if (k60_qrtr_channel == NULL) {
		printf("K60MODEM glink: no channel slot for IPCRTR\n");
		return -1;
	}
	k60_qrtr_glink_ready = 1;
	printf("K60MODEM glink: IPCRTR opened as initiator\n");
	return 0;
}

int
k60_modem_qrtr_probe(void)
{
	K60Smem smem;
	K60SmemPartition partition;
	uint32_t offsets[4] = {0, 0, 0, 0}, sizes[4] = {0, 0, 0, 0};
	const uint32_t items[4] = {K60_MODEM_GLINK_DESC, K60_MODEM_GLINK_OURS,
	    K60_MODEM_GLINK_THEIRS, K60_MODEM_SMP2P_THEIRS};
	volatile uint8_t *window;
	volatile uint32_t *desc;
	QcomGlinkFifo tx, rx;
	const QcomGlinkClient callbacks = {k60_qrtr_state_cb, k60_qrtr_receive_cb};
	uint32_t i, seen = 0;
	int enabled = 0, rc;

	if (!PE_parse_boot_argn("pong_modem", &enabled, sizeof(enabled)) || enabled < 2) {
		return 0;   /* default: not one byte is touched */
	}
	window = (volatile uint8_t *)ml_io_map_unmappable(K60_MODEM_SMEM_BASE,
	    K60_MODEM_SMEM_BYTES, 0x7);
	if (window == NULL) {
		printf("K60MODEM qrtr: smem map failed at %#x\n", K60_MODEM_SMEM_BASE);
		return -1;
	}
	k60_qrtr_ipcc = (volatile uint8_t *)ml_io_map_unmappable(K60_MODEM_IPCC_BASE, 0x1000, 0x7);
	if (k60_qrtr_ipcc == NULL) {
		printf("K60MODEM qrtr: ipcc map failed at %#x\n", K60_MODEM_IPCC_BASE);
		return -1;
	}
	smem.base = window;
	smem.size = K60_MODEM_SMEM_BYTES;
	rc = k60_smem_partition(&smem, 0, 1, &partition);
	if (rc != K60SmemOk) {
		printf("K60MODEM qrtr: no modem smem partition rc=%d\n", rc);
		return -1;
	}
	/* 478/479 are AP-owned and must exist now. 480 and 435 are created by
	 * the modem during its own boot; wait for both instead of failing the
	 * cold boot before the readiness poll. */
	for (i = 0; i < 2; i++) {
		rc = k60_smem_find(&smem, &partition, (uint16_t)items[i], &offsets[i], &sizes[i]);
		if (rc != K60SmemOk) {
			printf("K60MODEM qrtr: smem item %u missing rc=%d\n", items[i], rc);
			return -1;
		}
	}
	for (i = 0; i < K60_QRTR_READY_POLLS; i++) {
		if (sizes[2] == 0) {
			(void)k60_smem_find(&smem, &partition, (uint16_t)items[2],
			    &offsets[2], &sizes[2]);
		}
		rc = k60_smem_find(&smem, &partition, (uint16_t)items[3],
		    &offsets[3], &sizes[3]);
		if (rc == K60SmemOk &&
		    k60_qrtr_modem_ready(window, offsets[3], sizes[3], &seen) &&
		    sizes[2] != 0) {
			break;
		}
		delay(K60_QRTR_POLL_US);
	}
	if (i == K60_QRTR_READY_POLLS) {
		printf("K60MODEM qrtr: modem not ready after %u ms (smp2p items=%u)\n",
		    K60_QRTR_READY_POLLS * K60_QRTR_POLL_US / 1000u, seen);
		return -2;
	}
	if (sizes[2] == 0) {
		printf("K60MODEM qrtr: remote glink fifo item %u missing after %u ms\n",
		    items[2], K60_QRTR_READY_POLLS * K60_QRTR_POLL_US / 1000u);
		return -2;
	}
	printf("K60MODEM qrtr: glink desc=%#x/%u ours=%#x/%u theirs=%#x/%u\n",
	    offsets[0], sizes[0], offsets[1], sizes[1], offsets[2], sizes[2]);
	printf("K60MODEM qrtr: modem ready (smp2p items=%u)\n", seen);
	if (!k60_qrtr_glink_ready) {
		if (sizes[0] != 32 || sizes[1] < 1024 || sizes[2] < 1024) {
			printf("K60MODEM qrtr: glink geometry wrong desc=%u ours=%u theirs=%u\n",
			    sizes[0], sizes[1], sizes[2]);
			return -1;
		}
		desc = (volatile uint32_t *)(window + offsets[0]);
		/* A live Android epoch owns these indices; we never reset them. A
		 * fresh epoch has our head and its tail at zero, which is what we adopt. */
		if (desc[1] != 0 || desc[2] != 0) {
			printf("K60MODEM qrtr: glink fifo not fresh (our_head=%u their_tail=%u), not adopted\n",
			    desc[1], desc[2]);
			return -1;
		}
		tx.head = &desc[1];
		tx.tail = &desc[0];
		tx.data = (volatile uint8_t *)(window + offsets[1]);
		tx.length = sizes[1];
		rx.head = &desc[3];
		rx.tail = &desc[2];
		rx.data = (volatile uint8_t *)(window + offsets[2]);
		rx.length = sizes[2];
		rc = qcom_glink_adopt(&k60_qrtr_link, tx, rx, k60_qrtr_kick, NULL);
		if (rc != QcomGlinkOk) {
			printf("K60MODEM qrtr: glink adopt rc=%d\n", rc);
			return -1;
		}
		k60_qrtr_channel = qcom_glink_channel(&k60_qrtr_link, "IPCRTR",
		    K60_QRTR_INTENT_SIZE, K60_QRTR_INTENT_COUNT, k60_qrtr_intents,
		    &callbacks, NULL, 1);
		if (k60_qrtr_channel == NULL) {
			printf("K60MODEM qrtr: no channel slot for IPCRTR\n");
			return -1;
		}
	} else {
		printf("K60MODEM qrtr: GLINK already opened by transport\n");
	}
	printf("K60MODEM qrtr: opening IPCRTR as initiator\n");
	printf("K60MODEM baseband: bridge %s\n",
	    coachz_baseband_enabled() ? "enabled" : "disabled");
	coachz_baseband_configure(k60_baseband_send, k60_baseband_del_client);
	for (i = 0; i < K60_QRTR_POLLS; i++) {
		const int polls = qcom_glink_poll(&k60_qrtr_link);

		if (polls < 0) {
			/* QcomGlinkCorrupt leaves the offending message at the head of the
			 * RX ring (receive_one peeks, never advances, and stop() keeps the
			 * FIFO). Snapshot it so a single flight identifies the branch. */
			const QcomGlinkFifo *rx = &k60_qrtr_link.rx;
			uint32_t avail = rx->data != NULL ? qcom_glink_rx_avail(rx) : 0u;
			uint32_t head = rx->head != NULL ? *rx->head : 0u;
			uint32_t tail = rx->tail != NULL ? *rx->tail : 0u;
			uint8_t m[8] = {0};

			/* rx_peek() reads from the tail; head is the modem's write
			 * index, so sampling there shows unused ring bytes (k30 did
			 * exactly that and printed cmd=0 p1=0 p2=0). */
			for (uint32_t b = 0; b < 8u && b < avail && rx->data != NULL; ++b) {
				m[b] = rx->data[(tail + b) % rx->length];
			}
			printf("K60MODEM qrtr: glink poll rc=%d at %u rx avail=%u head=%u tail=%u cmd=%#x p1=%#x p2=%#x\n",
			    polls, i, avail, head, tail, (unsigned)(m[0] | (m[1] << 8)),
			    (unsigned)(m[2] | (m[3] << 8)),
			    (unsigned)(m[4] | (m[5] << 8) | (m[6] << 16) | ((unsigned)m[7] << 24)));
			return polls;
		}
		coachz_baseband_poll();
		if (i != 0u && i % 500u == 0u) {
			/* QcomBaseband defers publication when IOResources is not ready;
			 * retry once a second instead of latching the first failure. */
			coachz_baseband_configure(k60_baseband_send, k60_baseband_del_client);
			coachz_baseband_report(i / 500u);
		}
		if (k60_qrtr_up && !k60_qrtr_hello_sent) {
			uint8_t packet[K60_QRTR_LOOKUP_BYTES];

			if (k60_qrtr_build_hello(packet, sizeof(packet)) != 0) {
				const int send_rc = qcom_glink_send(&k60_qrtr_link,
				    k60_qrtr_channel, packet, K60_QRTR_LOOKUP_BYTES);

				if (send_rc == QcomGlinkOk) {
					k60_qrtr_hello_sent = 1;
					printf("K60MODEM qrtr: sent hello from node %u port %#x\n",
					    K60_QRTR_AP_NODE, K60_QRTR_CONTROL_PORT);
				} else if (send_rc != QcomGlinkAgain) {
					printf("K60MODEM qrtr: hello send rc=%d\n", send_rc);
					return send_rc;
				}
			}
		}
		if (k60_qrtr_hello_sent && k60_qrtr_state.hello_acks != 0 &&
		    !k60_qrtr_server_sent) {
			uint8_t packet[K60_QRTR_LOOKUP_BYTES];
			uint32_t to_node = k60_qrtr_state.remote_node;

			if (to_node == K60_QRTR_CONTROL_PORT || to_node == K60_QRTR_AP_NODE) {
				to_node = K60_QRTR_BROADCAST_NODE;
			}
			if (k60_qrtr_build_new_server(packet, sizeof(packet),
			    K60_QRTR_SERVLOC_SERVICE, K60_QRTR_SERVLOC_INSTANCE,
			    to_node, K60_QRTR_LOCATOR_PORT) != 0) {
				const int send_rc = qcom_glink_send(&k60_qrtr_link,
				    k60_qrtr_channel, packet, K60_QRTR_LOOKUP_BYTES);

				if (send_rc == QcomGlinkOk) {
					k60_qrtr_server_sent = 1;
					printf("K60MODEM qrtr: announced servloc service %u instance %#x port %#x\n",
					    K60_QRTR_SERVLOC_SERVICE, K60_QRTR_SERVLOC_INSTANCE,
					    K60_QRTR_LOCATOR_PORT);
				} else if (send_rc != QcomGlinkAgain) {
					printf("K60MODEM qrtr: servloc announce rc=%d\n", send_rc);
					return send_rc;
				}
			}
		}
		if (k60_qrtr_hello_sent && k60_qrtr_state.hello_acks != 0 &&
		    !k60_qrtr_lookup_sent) {
			uint8_t packet[K60_QRTR_LOOKUP_BYTES];
			uint32_t to_node = k60_qrtr_state.remote_node;

			if (to_node == K60_QRTR_CONTROL_PORT || to_node == K60_QRTR_AP_NODE) {
				to_node = K60_QRTR_BROADCAST_NODE;
			}
			if (k60_qrtr_build_lookup(packet, sizeof(packet), to_node) != 0) {
				const int send_rc = qcom_glink_send(&k60_qrtr_link,
				    k60_qrtr_channel, packet, K60_QRTR_LOOKUP_BYTES);

				if (send_rc == QcomGlinkOk) {
					k60_qrtr_lookup_sent = 1;
					printf("K60MODEM qrtr: sent new_lookup (0x0a) to node %u\n",
					    to_node);
				} else if (send_rc != QcomGlinkAgain) {
					printf("K60MODEM qrtr: lookup send rc=%d\n", send_rc);
					return send_rc;
				}
			}
		}
		if (k60_qrtr_lookup_sent && k60_qrtr_state.dms_found &&
		    !k60_qrtr_dms_requested) {
			uint8_t query[K60_QMI_HEADER];
			uint16_t transaction = ++k60_qrtr_dms_transaction;

			if (transaction == 0) {
				transaction = ++k60_qrtr_dms_transaction;
			}
			if (k60_qmi_build_dms_revision(query, sizeof(query), transaction) != 0) {
				k60_qrtr_state.dms_transaction = transaction;
				rc = k60_qrtr_send_data_packet(K60_QRTR_DMS_PORT,
				    k60_qrtr_state.dms_node, k60_qrtr_state.dms_port,
				    query, sizeof(query));
				if (rc == QcomGlinkOk) {
					k60_qrtr_dms_requested = 1;
					k60_qrtr_state.dms_sent = 1;
					printf("K60MODEM qrtr: sent dms get_revision to node %u port %u txn %u\n",
					    k60_qrtr_state.dms_node, k60_qrtr_state.dms_port,
					    transaction);
				} else if (rc != QcomGlinkAgain) {
					printf("K60MODEM qrtr: dms send rc=%d\n", rc);
					return rc;
				}
			}
		}
		rc = k60_qrtr_flush_replies();
		if (rc != 0) {
			printf("K60MODEM qrtr: reply send rc=%d at %u\n", rc, i);
			return rc;
		}
		if (k60_qrtr_lookup_sent && k60_qrtr_state.dms_answered &&
		    k60_qrtr_verdict(&k60_qrtr_state)) {
			break;
		}
		delay(K60_QRTR_POLL_US);
	}
	printf("K60MODEM qrtr: verdict %s services=%u node0=%u wanted=%u malformed=%u locator=%u dms=%s polls=%u\n",
	    k60_qrtr_verdict(&k60_qrtr_state) ? "ok" : "no reply",
	    k60_qrtr_state.services, k60_qrtr_state.from_node0, k60_qrtr_state.wanted,
	    k60_qrtr_state.malformed, k60_qrtr_state.locator_requests,
	    k60_qrtr_state.dms_answered ? k60_qrtr_state.revision : "none", i);
	if (!k60_qrtr_verdict(&k60_qrtr_state)) {
		return -2;
	}
	if (!k60_qrtr_state.dms_answered) {
		printf("K60MODEM qrtr: dms revision missing after %u ms (errors=%u)\n",
		    K60_QRTR_POLLS * K60_QRTR_POLL_US / 1000u,
		    k60_qrtr_state.dms_errors);
		return -2;
	}
	return 0;
}

#endif /* K60_HOST_TEST */
