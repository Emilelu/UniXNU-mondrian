/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/*
 * K60ModemSysmon.h - the lifecycle exchange the modem's SysMon service
 *                    expects from the application processor.
 *
 * Pong only ever receives replies on the modem link
 * (PongModemSysmon.h: sysmonModemServer/sysmonModemReceive parse a QMI
 * RESPONSE for message 0x25 and match the transaction), and it sends the
 * events from sysmonPoll(): a QRTR request on port 0x103 to the peer that
 * announced service 43, instance 0x1202 for the modem and 0x1402 for the
 * ADSP. The state enum follows the native SSCTL order: 1 is
 * AFTER_POWERUP and 3 is AFTER_SHUTDOWN.
 *
 * The wire layout is the one PongModemSysmon.h:sysmonSend() builds:
 *   0..6   QMI v1 header, message 0x25, request
 *   7      TLV 1, a named string: one length byte then the characters
 *   +      TLV 2, four bytes of state
 *   +      TLV 3, four bytes echoing the transaction
 *   +      TLV 0x10, four zero bytes
 * A reply is a response (byte 0 = 1) for the same message and transaction
 * with TLV 2 = <u16 error><u16 code>: zero error is the ACK Pong waits for.
 */
#ifndef K60_MODEM_SYSMON_H
#define K60_MODEM_SYSMON_H

#include <stddef.h>
#include <stdint.h>

#define K60_SYSMON_SERVICE       0x43u
#define K60_SYSMON_MODEM_INSTANCE 0x1202u
#define K60_SYSMON_ADSP_INSTANCE 0x1402u
#define K60_SYSMON_PORT          0x103u
#define K60_SYSMON_MESSAGE       0x25u
#define K60_SYSMON_STATE_AFTER_POWERUP  1u
#define K60_SYSMON_STATE_AFTER_SHUTDOWN 3u
#define K60_SYSMON_NAME_MAX      32u
#define K60_SYSMON_MAX_BYTES     64u

/* Builds one lifecycle request. Returns the bytes written, or 0 when the
 * name does not fit or the buffer cannot hold the whole message. */
size_t k60_sysmon_build_event(uint8_t *out, size_t capacity,
    uint16_t transaction, const char *name, uint32_t state);

/* Returns 0 for an ACK, the refusal code for a refusal (48 argument, 71
 * unsupported, ...), -1 when the bytes are not a reply to this request. */
int k60_sysmon_parse_reply(const void *bytes, size_t length,
    uint16_t transaction, uint16_t *code_out);

#endif /* K60_MODEM_SYSMON_H */
