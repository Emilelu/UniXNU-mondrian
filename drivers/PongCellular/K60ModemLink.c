/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* The modem's GLINK edge, read-only: adopt the two SMEM FIFOs the modem and
 * the APSS share, answer the channel the modem opens for QRTR ("IPCRTR", the
 * DT's qcom,glink-channels), send one HELLO and one NEW_LOOKUP, and fold the
 * NEW_SERVER replies into K60ModemQrtr's table. Nothing here writes a modem
 * partition, an EFS item or an NV item: the only bytes written are on the
 * GLINK ring, which is the transport itself.
 *
 * Layout facts, all from the live DT (docs/research/cellular/02-DT-TRUTH.md):
 *   smem  0x80900000 + 0x200000   qcom,smem
 *   ipcc  0x0ed18000              mboxes = <&ipcc 2 0>
 *   glink edge qcom,remote-pid = <1>, transport "smem"
 *   channel "IPCRTR", intents 0x800x5 0x2000x3 0x4400x2
 * SMEM item ids 478/479/480 (descriptor, our queue, its queue) and 435 (the
 * modem's SMP2P state) are the modem transport's, not the ADSP's: the ADSP
 * used 428/435 on its own partition, so this file reads its own partition
 * (host 0 <-> remote 1) and never touches the DSP's.
 *
 * Every line starts with K60MODEM, and the whole probe is inert unless
 * pong_modem is set to 2 or more. */
#include "K60ModemQrtr.h"
#include "K60Smem.h"
#include "QcomGlink.h"

#ifndef K60_HOST_TEST

#include <pexpert/pexpert.h>
#include <sys/systm.h>

/* osfmk/arm/machine_routines.h:703 (same declaration K60AdspBoot.c uses). */
extern vm_offset_t ml_io_map_unmappable(vm_offset_t phys, vm_size_t size, uint32_t flags);
extern void delay(int microseconds);

#define K60_MODEM_SMEM_BASE      0x80900000u
#define K60_MODEM_SMEM_BYTES     0x00200000u
#define K60_MODEM_IPCC_BASE      0x0ed18000u
#define K60_MODEM_IPCC_CLIENT    2u
#define K60_MODEM_IPCC_SIGNAL    0u
#define K60_MODEM_IPCC_SEND      0x0cu

#define K60_MODEM_SMP2P_THEIRS   435u
#define K60_MODEM_GLINK_DESC     478u
#define K60_MODEM_GLINK_OURS     479u
#define K60_MODEM_GLINK_THEIRS   480u
#define K60_MODEM_SMP2P_MAGIC    0x504d5324u

/* Our receive intents: the DT asks for three groups (0x800x5, 0x2000x3,
 * 0x4400x2); QcomGlink carries one group per channel, so pick the largest
 * size and the largest count that fit its limits (4 local intents). */
#define K60_QRTR_INTENT_SIZE     0x4400u
#define K60_QRTR_INTENT_COUNT    4u
#define K60_QRTR_POLL_US         2000
#define K60_QRTR_POLLS           500    /* one second of polling at most */

static QcomGlink k60_qrtr_link;
static QcomGlinkChannel *k60_qrtr_channel;
static uint8_t k60_qrtr_intents[K60_QRTR_INTENT_COUNT * K60_QRTR_INTENT_SIZE];
static K60QrtrState k60_qrtr_state;
static volatile uint8_t *k60_qrtr_ipcc;
static int k60_qrtr_up;
static int k60_qrtr_sent;

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

static void
k60_qrtr_receive_cb(void *context, QcomGlinkChannel *channel, const uint8_t *data, uint32_t length)
{
	K60QrtrHeader header;
	const uint8_t *payload = NULL;

	(void)context;
	(void)channel;
	if (k60_qrtr_parse(data, length, &header, &payload) == K60QrtrOk &&
	    header.type == K60QrtrNewServer && header.size == K60_QRTR_CONTROL_BYTES) {
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
	}
	(void)k60_qrtr_note(&k60_qrtr_state, data, length);
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
	    K60_MODEM_SMEM_BYTES, 0x2);
	if (window == NULL) {
		printf("K60MODEM qrtr: smem map failed at %#x\n", K60_MODEM_SMEM_BASE);
		return -1;
	}
	k60_qrtr_ipcc = (volatile uint8_t *)ml_io_map_unmappable(K60_MODEM_IPCC_BASE, 0x1000, 0x2);
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
	for (i = 0; i < 4; i++) {
		rc = k60_smem_find(&smem, &partition, (uint16_t)items[i], &offsets[i], &sizes[i]);
		if (rc != K60SmemOk) {
			printf("K60MODEM qrtr: smem item %u missing rc=%d\n", items[i], rc);
			return -1;
		}
	}
	printf("K60MODEM qrtr: glink desc=%#x/%u ours=%#x/%u theirs=%#x/%u\n",
	    offsets[0], sizes[0], offsets[1], sizes[1], offsets[2], sizes[2]);
	if (!k60_qrtr_modem_ready(window, offsets[3], sizes[3], &seen)) {
		printf("K60MODEM qrtr: modem not ready (smp2p items=%u state=%#x)\n",
		    seen, seen != 0 ? ((volatile uint32_t *)(window + offsets[3]))[4] : 0);
		return 0;
	}
	if (sizes[0] != 32 || sizes[1] < 1024 || sizes[2] < 1024) {
		printf("K60MODEM qrtr: glink geometry wrong desc=%u ours=%u theirs=%u\n",
		    sizes[0], sizes[1], sizes[2]);
		return -1;
	}
	desc = (volatile uint32_t *)(window + offsets[0]);
	/* A live Android epoch owns these indices; we never reset them. A fresh
	 * epoch has our head and its tail at zero, which is what we adopt. */
	if (desc[1] != 0 || desc[2] != 0) {
		printf("K60MODEM qrtr: glink fifo not fresh (our_head=%u their_tail=%u), not adopted\n",
		    desc[1], desc[2]);
		return 0;
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
	    K60_QRTR_INTENT_SIZE, K60_QRTR_INTENT_COUNT, k60_qrtr_intents, &callbacks, NULL, 0);
	if (k60_qrtr_channel == NULL) {
		printf("K60MODEM qrtr: no channel slot for IPCRTR\n");
		return -1;
	}
	printf("K60MODEM qrtr: waiting for the modem to open IPCRTR\n");
	for (i = 0; i < K60_QRTR_POLLS; i++) {
		const int polls = qcom_glink_poll(&k60_qrtr_link);

		if (polls < 0) {
			printf("K60MODEM qrtr: glink poll rc=%d at %u\n", polls, i);
			return polls;
		}
		if (k60_qrtr_up && !k60_qrtr_sent) {
			uint8_t packet[K60_QRTR_LOOKUP_BYTES];

			if (k60_qrtr_build_hello(packet, sizeof(packet), K60_QRTR_FIRST_PORT) != 0) {
				(void)qcom_glink_send(&k60_qrtr_link, k60_qrtr_channel, packet,
				    K60_QRTR_LOOKUP_BYTES);
			}
			if (k60_qrtr_build_lookup(packet, sizeof(packet), K60_QRTR_FIRST_PORT) != 0) {
				(void)qcom_glink_send(&k60_qrtr_link, k60_qrtr_channel, packet,
				    K60_QRTR_LOOKUP_BYTES);
			}
			k60_qrtr_sent = 1;
			printf("K60MODEM qrtr: sent hello and new_lookup (0x0a) from port %#x\n",
			    K60_QRTR_FIRST_PORT);
		}
		if (k60_qrtr_sent && k60_qrtr_state.services != 0 && i > 60) {
			break;
		}
		delay(K60_QRTR_POLL_US);
	}
	printf("K60MODEM qrtr: verdict %s services=%u node0=%u wanted=%u malformed=%u polls=%u\n",
	    k60_qrtr_verdict(&k60_qrtr_state) ? "ok" : "no reply",
	    k60_qrtr_state.services, k60_qrtr_state.from_node0, k60_qrtr_state.wanted,
	    k60_qrtr_state.malformed, i);
	return k60_qrtr_verdict(&k60_qrtr_state) ? 0 : -2;
}

#endif /* K60_HOST_TEST */
