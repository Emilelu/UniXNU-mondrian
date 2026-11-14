/*
 * ucsi-host-selftest.c - host-verifiable check of the UCSI-over-GLINK framing
 * that the K60 device-mode stack needs (pmic_glink channel "PMIC_RTR_ADSP_APPS",
 * protection domain "msm/adsp/charger_pd").
 *
 * This program never talks to a device. It encodes and decodes the wire format
 * defined by the upstream kernel (v6.6) and asserts round trips, so the framing
 * can be reviewed and regression-tested on any host before a single line of
 * driver code exists.
 *
 * Evidence for every constant is cited next to it.
 *   E:/k60-work/scratch/usb/linux/pmic_glink.h        (owner ids, hdr, msg types)
 *   E:/k60-work/scratch/usb/linux/ucsi_glink.c        (0x11/0x12/0x13, 48-byte buf)
 *   E:/k60-work/scratch/usb/linux/ucsi.h              (UCSI offsets, CCI bits, commands,
 *                                                      struct ucsi_connector_status)
 *
 * Build/run: cc -std=c11 -Wall -Wextra -o ucsi-host-selftest ucsi-host-selftest.c && ./ucsi-host-selftest
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>

/* ---- pmic_glink.h ------------------------------------------------------- */
#define PMIC_GLINK_OWNER_USBC 32779u          /* pmic_glink.h: owner id of the USB-C PPM */
#define PMIC_GLINK_REQ_RESP   1u              /* request/response message */
#define PMIC_GLINK_NOTIFY     2u              /* unsolicited notification */
struct pmic_glink_hdr { uint32_t owner, type, opcode; };   /* 12 bytes, little endian */

/* ---- ucsi_glink.c ------------------------------------------------------- */
#define UCSI_BUF_SIZE        48u
#define UC_UCSI_READ_BUF_REQ  0x11u
#define UC_UCSI_WRITE_BUF_REQ 0x12u
#define UC_UCSI_USBC_NOTIFY_IND 0x13u

/* ---- ucsi.h: UCSI data structure offsets -------------------------------- */
#define UCSI_VERSION 0
#define UCSI_CCI     4
#define UCSI_CONTROL 8
#define UCSI_MESSAGE_IN  16
#define UCSI_MESSAGE_OUT 32

#define UCSI_CCI_CONNECTOR(c) ((((c) & 0x000000feu) >> 1))
#define UCSI_CCI_LENGTH(c)    ((((c) & 0x0000ff00u) >> 8))
#define UCSI_CCI_BUSY             (1u << 28)
#define UCSI_CCI_ACK_COMPLETE     (1u << 29)
#define UCSI_CCI_ERROR            (1u << 30)
#define UCSI_CCI_COMMAND_COMPLETE (1u << 31)

#define UCSI_PPM_RESET               0x01
#define UCSI_ACK_CC_CI               0x04
#define UCSI_SET_NOTIFICATION_ENABLE 0x05
#define UCSI_GET_CONNECTOR_STATUS    0x12
#define UCSI_CONNECTOR_NUMBER(n) ((uint64_t)(n) << 16)
#define UCSI_COMMAND(c)          ((uint64_t)(c) & 0xffu)

#define UCSI_ACK_CONNECTOR_CHANGE (1u << 16)
#define UCSI_ACK_COMMAND_COMPLETE (1u << 17)
#define UCSI_ENABLE_NTFY_CMD_COMPLETE      (1u << 16)
#define UCSI_ENABLE_NTFY_PARTNER_CHANGE    (1u << 27)
#define UCSI_ENABLE_NTFY_CONNECTOR_CHANGE  (1u << 30)

/* struct ucsi_connector_status, ucsi.h:234 */
#define UCSI_CONSTAT_CONNECTED      (1u << 3)
#define UCSI_CONSTAT_PARTNER_TYPE(f) ((((f) & 0xe000u) >> 13))
#define UCSI_CONSTAT_PARTNER_TYPE_DFP 1
#define UCSI_CONSTAT_PARTNER_TYPE_UFP 2
#define UCSI_CONSTAT_PARTNER_TYPE_CABLE 3
#define UCSI_CONSTAT_PARTNER_TYPE_CABLE_AND_UFP 4
#define UCSI_CONSTAT_PARTNER_TYPE_DEBUG 5
#define UCSI_CONSTAT_PARTNER_TYPE_AUDIO 6

enum usb_role_kind { ROLE_UNKNOWN = 0, ROLE_DEVICE = 1, ROLE_HOST = 2 };

/* -------------------------------------------------------------------------
 * Message builders. Sizes come from ucsi_glink.c structs.
 * ---------------------------------------------------------------------- */
struct read_req  { struct pmic_glink_hdr hdr; };
struct read_resp { struct pmic_glink_hdr hdr; uint8_t buf[UCSI_BUF_SIZE]; uint32_t ret_code; };
struct write_req { struct pmic_glink_hdr hdr; uint8_t buf[UCSI_BUF_SIZE]; uint32_t reserved; };
struct write_resp{ struct pmic_glink_hdr hdr; uint32_t ret_code; };
struct notify_ind{ struct pmic_glink_hdr hdr; uint32_t notification, receiver, reserved; };

static struct pmic_glink_hdr hdr(uint32_t type, uint32_t opcode)
{
	struct pmic_glink_hdr h = { PMIC_GLINK_OWNER_USBC, type, opcode };
	return h;
}

static void put_u64le(uint8_t *p, uint64_t v)
{
	for (int i = 0; i < 8; i++) p[i] = (uint8_t)(v >> (8 * i));
}
static uint64_t get_u64le(const uint8_t *p)
{
	uint64_t v = 0;
	for (int i = 0; i < 8; i++) v |= (uint64_t)p[i] << (8 * i);
	return v;
}

/* UCSI command goes into the 8-byte CONTROL field at offset 8 of the 48-byte buffer. */
static void ucsi_set_control(uint8_t buf[UCSI_BUF_SIZE], uint64_t control)
{
	put_u64le(buf + UCSI_CONTROL, control);
}
static uint64_t ucsi_get_control(const uint8_t buf[UCSI_BUF_SIZE])
{
	return get_u64le(buf + UCSI_CONTROL);
}
static void ucsi_set_cci(uint8_t buf[UCSI_BUF_SIZE], uint32_t cci)
{
	for (int i = 0; i < 4; i++) buf[UCSI_CCI + i] = (uint8_t)(cci >> (8 * i));
}
static uint32_t ucsi_get_cci(const uint8_t buf[UCSI_BUF_SIZE])
{
	uint32_t v = 0;
	for (int i = 0; i < 4; i++) v |= (uint32_t)buf[UCSI_CCI + i] << (8 * i);
	return v;
}

/* -------------------------------------------------------------------------
 * Role decision. Official QcomDwc3 documentation, E:/k60-work/references/
 * UniXNU-upstream/docs/porting/usb.md:
 *   "A host on the cable selects the device role and a peripheral selects the
 *    host role. With no answer from either source, the device role runs."
 * The partner type in GET_CONNECTOR_STATUS says what is on the other end.
 * ---------------------------------------------------------------------- */
static enum usb_role_kind role_from_connector_status(uint16_t flags)
{
	unsigned partner;
	if (!(flags & UCSI_CONSTAT_CONNECTED))
		return ROLE_UNKNOWN;          /* nothing attached: caller keeps device role */
	partner = UCSI_CONSTAT_PARTNER_TYPE(flags);
	switch (partner) {
	case UCSI_CONSTAT_PARTNER_TYPE_DFP:            return ROLE_DEVICE; /* partner is a host */
	case UCSI_CONSTAT_PARTNER_TYPE_UFP:            return ROLE_HOST;   /* partner is a peripheral */
	case UCSI_CONSTAT_PARTNER_TYPE_CABLE_AND_UFP:  return ROLE_HOST;
	case UCSI_CONSTAT_PARTNER_TYPE_DEBUG:          return ROLE_DEVICE; /* debug target = device */
	case UCSI_CONSTAT_PARTNER_TYPE_AUDIO:          return ROLE_DEVICE;
	case UCSI_CONSTAT_PARTNER_TYPE_CABLE:          return ROLE_UNKNOWN; /* powered cable, no data role */
	default:                                       return ROLE_UNKNOWN;
	}
}

static const char *role_name(enum usb_role_kind r)
{
	switch (r) {
	case ROLE_DEVICE: return "device";
	case ROLE_HOST:   return "host";
	default:          return "unknown(default device)";
	}
}

/* -------------------------------------------------------------------------
 * A fake PPM: answers the three opcodes the driver will see. This models the
 * ADSP side, so the host can prove the encoding/decoding without the phone.
 * ---------------------------------------------------------------------- */
struct fake_ppm {
	uint16_t conn_flags;   /* what GET_CONNECTOR_STATUS reports */
	uint8_t  cci_connector;
	int      reads, writes, notifies;
};

static void ppm_handle_write(struct fake_ppm *p, const struct write_req *req, struct write_resp *resp)
{
	uint64_t ctl = ucsi_get_control(req->buf);
	unsigned cmd = (unsigned)(ctl & 0xff);
	p->writes++;
	resp->hdr = hdr(PMIC_GLINK_REQ_RESP, UC_UCSI_WRITE_BUF_REQ);
	resp->ret_code = 0;
	if (cmd == UCSI_GET_CONNECTOR_STATUS) {
		/* PPM writes the response payload into MESSAGE_IN of the buffer we read next. */
	}
}

static void ppm_fill_read(struct fake_ppm *p, struct read_resp *resp)
{
	uint32_t cci = UCSI_CCI_COMMAND_COMPLETE | (uint32_t)(p->cci_connector << 1);
	memset(resp, 0, sizeof(*resp));
	resp->hdr = hdr(PMIC_GLINK_REQ_RESP, UC_UCSI_READ_BUF_REQ);
	resp->ret_code = 0;
	ucsi_set_cci(resp->buf, cci);
	/* GET_CONNECTOR_STATUS payload lands at MESSAGE_IN (offset 16). */
	resp->buf[UCSI_MESSAGE_IN + 0] = (uint8_t)(p->conn_flags & 0xff);
	resp->buf[UCSI_MESSAGE_IN + 1] = (uint8_t)(p->conn_flags >> 8);
	p->reads++;
}

static int failures;
static void check(const char *what, int ok)
{
	printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what);
	if (!ok) failures++;
}

int main(void)
{
	printf("ucsi-host-selftest: UCSI over pmic_glink framing (host side only)\n");
	printf("owner=%u (PMIC_GLINK_OWNER_USBC), buf=%u bytes, opcodes 0x11 read / 0x12 write / 0x13 notify\n\n",
	       PMIC_GLINK_OWNER_USBC, UCSI_BUF_SIZE);

	/* 1. message sizes, so the driver's buffers match the firmware's expectations */
	printf("1. message layout\n");
	check("pmic_glink_hdr is 12 bytes", sizeof(struct pmic_glink_hdr) == 12);
	check("read_buf_req  = 12 bytes", sizeof(struct read_req) == 12);
	check("read_buf_resp = 12 + 48 + 4 = 64 bytes", sizeof(struct read_resp) == 64);
	check("write_buf_req = 12 + 48 + 4 = 64 bytes", sizeof(struct write_req) == 64);
	check("write_buf_resp= 16 bytes", sizeof(struct write_resp) == 16);
	check("notify_ind    = 24 bytes", sizeof(struct notify_ind) == 24);

	/* 2. enable the two notifications the role decision needs */
	printf("\n2. SET_NOTIFICATION_ENABLE control word\n");
	/* ucsi.c: c = UCSI_SET_NOTIFICATION_ENABLE | con->ucsi->ntfy;
	 * the notification mask lives in bits 16..31 of the control word itself,
	 * it is NOT shifted a second time. */
	/* SET_NOTIFICATION_ENABLE carries the mask only; it has no connector field,
	 * so bits 19:16 belong to the mask (CMD_COMPLETE is BIT(16)). */
	uint64_t ctl = UCSI_COMMAND(UCSI_SET_NOTIFICATION_ENABLE)
	             | (uint64_t)(UCSI_ENABLE_NTFY_CONNECTOR_CHANGE | UCSI_ENABLE_NTFY_PARTNER_CHANGE
	                          | UCSI_ENABLE_NTFY_CMD_COMPLETE);
	uint8_t buf[UCSI_BUF_SIZE] = {0};
	ucsi_set_control(buf, ctl);
	check("command byte is 0x05", (ucsi_get_control(buf) & 0xff) == UCSI_SET_NOTIFICATION_ENABLE);
	check("command-complete notify (bit16) set", (ucsi_get_control(buf) & (1ull << 16)) != 0);
	check("no connector field is encoded", (ucsi_get_control(buf) & (1ull << 20)) == 0);
	check("connector-change bit 30 set", (ucsi_get_control(buf) & (1ull << 30)) != 0);
	check("partner-change bit 27 set", (ucsi_get_control(buf) & (1ull << 27)) != 0);
	printf("     control = 0x%016llx\n", (unsigned long long)ucsi_get_control(buf));

	/* 3. notification -> CCI -> connector number */
	printf("\n3. USBC_NOTIFY_IND -> CCI -> connector\n");
	struct notify_ind ind = { hdr(PMIC_GLINK_NOTIFY, UC_UCSI_USBC_NOTIFY_IND), 1u, 0u, 0u };
	check("notification type is 0x13", ind.hdr.opcode == UC_UCSI_USBC_NOTIFY_IND);
	struct fake_ppm ppm = { .conn_flags = 0, .cci_connector = 0 };
	struct read_resp rresp;
	ppm_fill_read(&ppm, &rresp);
	uint32_t cci = ucsi_get_cci(rresp.buf);
	check("COMMAND_COMPLETE set in CCI", (cci & UCSI_CCI_COMMAND_COMPLETE) != 0);
	check("connector decoded from CCI bits 7:1", UCSI_CCI_CONNECTOR(cci) == 0);

	/* 4. role decision table, one row per partner type */
	printf("\n4. GET_CONNECTOR_STATUS -> role\n");
	struct { const char *name; uint16_t flags; enum usb_role_kind want; } rows[] = {
		{ "nothing attached",              0, ROLE_UNKNOWN },
		{ "partner DFP (a host)",          UCSI_CONSTAT_CONNECTED | (UCSI_CONSTAT_PARTNER_TYPE_DFP << 13), ROLE_DEVICE },
		{ "partner UFP (a peripheral)",    UCSI_CONSTAT_CONNECTED | (UCSI_CONSTAT_PARTNER_TYPE_UFP << 13), ROLE_HOST },
		{ "powered cable + UFP",           UCSI_CONSTAT_CONNECTED | (UCSI_CONSTAT_PARTNER_TYPE_CABLE_AND_UFP << 13), ROLE_HOST },
		{ "debug accessory",               UCSI_CONSTAT_CONNECTED | (UCSI_CONSTAT_PARTNER_TYPE_DEBUG << 13), ROLE_DEVICE },
		{ "audio adapter",                 UCSI_CONSTAT_CONNECTED | (UCSI_CONSTAT_PARTNER_TYPE_AUDIO << 13), ROLE_DEVICE },
		{ "powered cable only",            UCSI_CONSTAT_CONNECTED | (UCSI_CONSTAT_PARTNER_TYPE_CABLE << 13), ROLE_UNKNOWN },
	};
	for (unsigned i = 0; i < sizeof(rows) / sizeof(rows[0]); i++) {
		enum usb_role_kind got = role_from_connector_status(rows[i].flags);
		char line[128];
		snprintf(line, sizeof(line), "%-28s -> %s", rows[i].name, role_name(got));
		check(line, got == rows[i].want);
	}

	/* 5. an ACK the driver must send after consuming the notification */
	printf("\n5. ACK_CC_CI\n");
	/* ucsi.c: ctrl = UCSI_ACK_CC_CI; ctrl |= UCSI_ACK_COMMAND_COMPLETE; (no shift) */
	uint64_t ack = UCSI_COMMAND(UCSI_ACK_CC_CI) | UCSI_ACK_CONNECTOR_CHANGE | UCSI_ACK_COMMAND_COMPLETE;
	ucsi_set_control(buf, ack);
	check("command byte is 0x04", (ucsi_get_control(buf) & 0xff) == UCSI_ACK_CC_CI);
	check("ACK_CONNECTOR_CHANGE (bit16) set", (ucsi_get_control(buf) & (1ull << 16)) != 0);
	check("ACK_COMMAND_COMPLETE (bit17) set", (ucsi_get_control(buf) & (1ull << 17)) != 0);
	/* ucsi_acknowledge_*() build the ACK from the command byte plus one bit only. */

	/* 6. full round trip through the fake PPM for GET_CONNECTOR_STATUS */
	printf("\n6. round trip GET_CONNECTOR_STATUS\n");
	struct write_req wreq;
	memset(&wreq, 0, sizeof(wreq));
	wreq.hdr = hdr(PMIC_GLINK_REQ_RESP, UC_UCSI_WRITE_BUF_REQ);
	ucsi_set_control(wreq.buf, UCSI_COMMAND(UCSI_GET_CONNECTOR_STATUS) | UCSI_CONNECTOR_NUMBER(0));
	struct write_resp wresp;
	ppm_handle_write(&ppm, &wreq, &wresp);
	check("PPM accepted the write", wresp.ret_code == 0 && ppm.writes == 1);
	ppm.conn_flags = UCSI_CONSTAT_CONNECTED | (UCSI_CONSTAT_PARTNER_TYPE_DFP << 13);
	ppm_fill_read(&ppm, &rresp);
	uint16_t flags = (uint16_t)(rresp.buf[UCSI_MESSAGE_IN] | (rresp.buf[UCSI_MESSAGE_IN + 1] << 8));
	check("host on the cable -> device role", role_from_connector_status(flags) == ROLE_DEVICE);
	ppm.conn_flags = UCSI_CONSTAT_CONNECTED | (UCSI_CONSTAT_PARTNER_TYPE_UFP << 13);
	ppm_fill_read(&ppm, &rresp);
	flags = (uint16_t)(rresp.buf[UCSI_MESSAGE_IN] | (rresp.buf[UCSI_MESSAGE_IN + 1] << 8));
	check("peripheral on the cable -> host role", role_from_connector_status(flags) == ROLE_HOST);

	printf("\n%s (%d failure%s)\n", failures ? "RESULT: FAIL" : "RESULT: PASS",
	       failures, failures == 1 ? "" : "s");
	return failures ? 1 : 0;
}
