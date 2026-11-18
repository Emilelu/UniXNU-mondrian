/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* IPA service 0x31 QMI messages over QRTR.

 * The handshake shape is Pong's: references/pong-baseband/PongModemWan.h:76-97
 * builds the INIT_DRIVER request from the modem SRAM window, :138-181 answers
 * the requests the modem sends to the AP's registered port, and :382-420
 * publishes INIT_COMPLETE once the uC reports ready.  The AP sends INIT_DRIVER
 * (0x21), answers INDICATION_REGISTER (0x20), DRIVER_INIT_COMPLETE (0x35),
 * CONFIGURATION (0x27), the filter-installed notification (0x24) and extended
 * rules (0x23), then sends INIT_COMPLETE (0x22) as a QMI indication.
 *
 * Only the message plumbing lives here: the SRAM base is a parameter, and
 * service discovery, timing, the filter rule table and the GSI rings stay in
 * the transport and runtime layers.  All fields are little endian, as libqmi
 * defines them, and the seven byte QMI header's length counts the TLVs only.
 */
#ifndef K60_IPA_QMI_H
#define K60_IPA_QMI_H

#include <stddef.h>
#include <stdint.h>

#define K60_IPA_QMI_SERVICE             49u     /* 0x31, IPA */
#define K60_IPA_QMI_INSTANCE_AP         0x101u
#define K60_IPA_QMI_INSTANCE_MODEM      0x201u
#define K60_IPA_QMI_HOST_PORT           0x122u  /* AP's registered service port */
#define K60_IPA_QMI_CLIENT_PORT         0x123u  /* AP's client port */

#define K60_IPA_QMI_INIT_DRIVER         0x21u
#define K60_IPA_QMI_INIT_COMPLETE       0x22u
#define K60_IPA_QMI_RULES               0x23u
#define K60_IPA_QMI_FILTER_INSTALLED    0x24u
#define K60_IPA_QMI_CONFIGURATION       0x27u
#define K60_IPA_QMI_INDICATION_REGISTER 0x20u
#define K60_IPA_QMI_DRIVER_INIT_COMPLETE 0x35u

#define K60_IPA_QMI_TLV_RESULT          0x02u
#define K60_IPA_QMI_TLV_DRIVER_STATUS   0x01u
#define K60_IPA_QMI_TLV_RULES           0x11u
#define K60_IPA_QMI_MAX_RULES           64u
#define K60_IPA_QMI_HEADER_BYTES        7u
#define K60_IPA_QMI_INIT_DRIVER_BYTES   154u
#define K60_IPA_QMI_SIMPLE_BYTES        14u     /* header plus result TLV */
#define K60_IPA_QMI_RULES_BYTES         (14u + 3u + 1u + 4u * K60_IPA_QMI_MAX_RULES)

enum {
	K60IpaQmiOk = 0,
	K60IpaQmiBadArgument = -1,
	K60IpaQmiTooLong = -2,
	K60IpaQmiMalformed = -3,
};

enum {
	K60IpaQmiKindUnknown = 0,
	K60IpaQmiKindIndicationRegister = 1,
	K60IpaQmiKindDriverInitComplete,
	K60IpaQmiKindConfiguration,
	K60IpaQmiKindFilterInstalled,
	K60IpaQmiKindRules,
};

/* INIT_DRIVER request with the seventeen SRAM window TLVs Pong sends
 * (0x10..0x22).  restricted_base is the modem SRAM base the offsets apply to.
 * Returns the message length, or 0 when the buffer is too small. */
size_t k60_ipa_qmi_build_init_driver(uint8_t *out, size_t capacity,
    uint16_t transaction, uint32_t restricted_base);
/* INIT_COMPLETE indication: type 4, message 0x22, result TLV 2 = success. */
size_t k60_ipa_qmi_build_init_complete(uint8_t *out, size_t capacity);
/* Response to one modem request.  A nonzero result is sent as 1, the QMI
 * failure code, with error as the error code.  rule_ids adds TLV 0x11 for a
 * RULES request, which the native stack answers with the accepted ids. */
size_t k60_ipa_qmi_build_response(uint8_t *out, size_t capacity,
    uint16_t transaction, uint16_t message, uint16_t result, uint16_t error,
    const uint32_t *rule_ids, size_t rule_count);
/* Response to INIT_DRIVER: type 2, same transaction and message, result TLV 2
 * of four bytes.  Returns 0 when it matches. */
int k60_ipa_qmi_parse_response(const uint8_t *data, size_t bytes,
    uint16_t transaction, uint16_t message, uint16_t *result, uint16_t *error);
/* Classifies one request the modem sends to the AP's registered port.  The
 * transaction and message id are returned; a malformed header or a response
 * yields a negative value, an unknown message id yields KindUnknown. */
int k60_ipa_qmi_classify(const uint8_t *data, size_t bytes,
    uint16_t *transaction, uint16_t *message);
/* DRIVER_INIT_COMPLETE (0x35): TLV 1, one byte. */
int k60_ipa_qmi_driver_status(const uint8_t *data, size_t bytes, uint8_t *status);
/* RULES (0x23): TLV 0x11, one count byte then count little endian ids. */
int k60_ipa_qmi_rules(const uint8_t *data, size_t bytes, uint32_t *ids,
    size_t capacity, size_t *count);

#endif
