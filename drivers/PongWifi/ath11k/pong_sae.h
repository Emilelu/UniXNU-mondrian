/* SAE (WPA3) authentication framing for the Pong station.
 *
 * WPA3-Personal replaces open-system authentication with SAE, Simultaneous Authentication of Equals
 * (IEEE 802.11-2020 12.4): the station sends an Authentication frame with algorithm 3 and transaction
 * sequence 1 that carries a commit scalar and element, and the access point answers with its own commit.
 * The legacy station path in this tree sends open-system authentication only, so before weeks go into a
 * supplicant the cheapest question is whether the firmware's management transmit path carries a frame of
 * SAE size at all. This unit builds that frame's body and nothing else: the payload is deterministic
 * filler, not key agreement, and a transmitted frame proves framing and transport, not SAE.
 *
 * The commit size follows the group: group 19 (P-256) is a 32-byte scalar plus a 64-byte element, group 20
 * (P-384) a 48-byte scalar plus a 96-byte element, so the commit body is 102 and 150 bytes respectively. Sizes from 802.11-2020 12.4.7.1 and the commit field
 * layout of the same section. No kernel header, so the host test compiles it (scripts/tests/test-pong-sae.py). */
#ifndef PONG_SAE_H
#define PONG_SAE_H

#include <stdint.h>

#define PONG_SAE_ALG 3         /* WLAN_AUTH_SAE: the algorithm number in the authentication header */
#define PONG_SAE_SEQ_COMMIT 1  /* WLAN_AUTH_SAE_COMMIT: the transaction sequence of the station's first frame */
#define PONG_SAE_BODY_HEADER 6 /* algorithm (2) + transaction sequence (2) + status (2) */

#define PONG_SAE_GROUP_19 19   /* P-256 */
#define PONG_SAE_GROUP_20 20   /* P-384 */

#define PONG_SAE_MAX_BODY 256  /* the largest body this unit builds: group 20 */

/* Length of the commit body for a group, or 0 when the group is not one this unit knows. */
unsigned pong_sae_commit_body_len(unsigned group);

/* Writes the commit body and returns its length; 0 when the group is unknown or the buffer is too small. */
unsigned pong_sae_commit_body(uint8_t *out, unsigned capacity, unsigned group);

#endif
