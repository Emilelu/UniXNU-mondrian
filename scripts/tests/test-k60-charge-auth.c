/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test for the K60 charge-auth state machine. No kernel, no GLINK: the
 * fake crypto and the manually built replies pin the protocol decisions. */
#include <stdio.h>
#include <string.h>
#include "K60ChargeAuth.h"

static unsigned checks, failures;
static void check(const char *name, unsigned got, unsigned want)
{
    ++checks;
    if (got != want) { ++failures; printf("FAIL %s: got %u want %u\n", name, got, want); }
}
static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}
static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 |
        (uint32_t)p[3] << 24;
}
/* Scalar reply: property at +12 (the receive contract), value at +16. */
static uint32_t reply(uint8_t *out, uint32_t opcode, uint32_t property, uint32_t value)
{
    memset(out, 0, K60_CHARGE_REQUEST_BYTES);
    put32(out, 32778); put32(out + 4, 1); put32(out + 8, opcode);
    put32(out + 12, property); put32(out + 16, value);
    return 24;
}
static uint32_t reply_result(uint8_t *out, uint32_t opcode, uint32_t property, int32_t result)
{
    memset(out, 0, K60_CHARGE_REQUEST_BYTES);
    put32(out, 32778); put32(out + 4, 1); put32(out + 8, opcode);
    put32(out + 12, property); put32(out + 20, (uint32_t)result);
    return 24;
}
static uint32_t reply_digest(uint8_t *out, uint32_t opcode, uint32_t property)
{
    memset(out, 0, K60_CHARGE_REQUEST_BYTES);
    put32(out, 32778); put32(out + 4, 1); put32(out + 8, opcode);
    put32(out + 12, property); memset(out + 16, 0xa5, 32);
    return 48;
}
static void fake_random(void *p, uint32_t bytes) { memset(p, 0x5a, bytes); }
static void fake_hmac(const uint8_t *key, uint32_t key_bytes, const uint8_t *msg,
    uint32_t msg_bytes, uint8_t out[32])
{
    (void)key; (void)key_bytes; (void)msg; (void)msg_bytes;
    memset(out, 0xa5, 32);
}

int main(void)
{
    const K60ChargeCrypto crypto = {fake_random, fake_hmac};
    K60ChargeAuth a;
    uint8_t out[K60_CHARGE_REQUEST_BYTES], in[K60_CHARGE_REQUEST_BYTES];
    uint32_t n;

    k60_charge_auth_init(&a, &crypto);
    check("init_enabled", a.enabled, 1);
    check("init_state", a.state, K60ChargeIdle);
    check("init_gauges", a.gauges, 1);
    k60_charge_auth_set_gauges(&a, 2);
    check("dual_gauges", a.gauges, 2);
    check("wait_idle", k60_charge_auth_wait_ms(&a, 0), 0);

    k60_charge_auth_observe(&a, 1, 5, 100);
    check("non_pd_stays_idle", a.state, K60ChargeIdle);
    k60_charge_auth_observe(&a, 1, 6, 1000);
    check("pd_online", a.online, 1);
    check("pd_state", a.state, K60ChargeGaugeCheck);
    check("pd_generation", a.generation, 1);

    n = k60_charge_auth_next(&a, 1000, out);
    check("gauge_check_bytes", n, 24);
    check("gauge_check_owner", get32(out), 32778);
    check("gauge_check_opcode", get32(out + 8), 0x50);
    check("gauge_check_property", get32(out + 16), 3);

    /* The first gauge is authentic: the machine moves to the second gauge. */
    n = reply(in, 0x50, 3, 1);
    check("gauge_ack_consumed", k60_charge_auth_receive(&a, in, n, 1010), 1);
    check("gauge_ack_slave", a.slave, 1);
    check("gauge_ack_state", a.state, K60ChargeGaugeCheck);
    check("gauge_ack_verified", a.gauge_verified, 1);
    check("gauge_wait", k60_charge_auth_wait_ms(&a, 1010), 500);
    n = k60_charge_auth_next(&a, 1510, out);
    check("slave_check_property", get32(out + 16), 0xa5);
    n = reply(in, 0x50, 0xa5, 1);
    check("slave_ack", k60_charge_auth_receive(&a, in, n, 1511), 1);
    check("slave_verified", a.gauge_verified, 3);
    check("adapter_state", a.state, K60ChargeAdapterCheck);
    check("adapter_wait", k60_charge_auth_wait_ms(&a, 1511), 500);

    n = k60_charge_auth_next(&a, 2011, out);
    check("adapter_svid_bytes", n, 24);
    check("adapter_svid_property", get32(out + 16), 0x17);
    n = reply(in, 0x50, 0x17, 0x2717);
    check("adapter_svid_ack", k60_charge_auth_receive(&a, in, n, 2011), 1);
    check("adapter_pdo_state", a.state, K60ChargeAdapterCheck);
    n = k60_charge_auth_next(&a, 2012, out);
    check("adapter_pdo_property", get32(out + 16), 0x19);
    n = reply(in, 0x50, 0x19, 0);
    check("adapter_pdo_ack", k60_charge_auth_receive(&a, in, n, 2012), 1);
    check("adapter_pdo_diag", a.state, K60ChargeDiagnostics);

    /* SVID mismatch goes straight to diagnostics with result 0. */
    k60_charge_auth_init(&a, &crypto);
    k60_charge_auth_set_gauges(&a, 2);
    k60_charge_auth_observe(&a, 1, 6, 3000);
    (void)k60_charge_auth_next(&a, 3000, out);
    (void)reply(in, 0x50, 3, 1);
    (void)k60_charge_auth_receive(&a, in, 24, 3001);
    (void)k60_charge_auth_next(&a, 3501, out);
    (void)reply(in, 0x50, 0xa5, 1);
    (void)k60_charge_auth_receive(&a, in, 24, 3502);
    (void)k60_charge_auth_next(&a, 4002, out);
    (void)reply(in, 0x50, 0x17, 0x1234);
    (void)k60_charge_auth_receive(&a, in, 24, 4003);
    check("svid_mismatch_diag", a.state, K60ChargeDiagnostics);
    check("svid_mismatch_result", a.result, 0);

    /* A fresh gauge challenge: digest, mark, then the second gauge. */
    k60_charge_auth_init(&a, &crypto);
    k60_charge_auth_set_gauges(&a, 2);
    k60_charge_auth_observe(&a, 1, 6, 5000);
    (void)k60_charge_auth_next(&a, 5000, out);
    (void)reply(in, 0x50, 3, 0);
    check("gauge_zero_ack", k60_charge_auth_receive(&a, in, 24, 5001), 1);
    check("gauge_challenge_state", a.state, K60ChargeGaugeChallenge);
    n = k60_charge_auth_next(&a, 5001, out);
    check("challenge_bytes", n, 52);
    check("challenge_opcode", get32(out + 8), 0x51);
    check("challenge_property", get32(out + 12), 1);
    check("challenge_random", out[16], 0x5a);
    check("challenge_slave", out[48], 0);
    check("challenge_tries", a.tries, 1);
    (void)reply(in, 0x51, 1, 0);
    check("challenge_ack", k60_charge_auth_receive(&a, in, 24, 5002), 1);
    check("digest_wait", k60_charge_auth_wait_ms(&a, 5002), 1400);
    n = k60_charge_auth_next(&a, 6402, out);
    check("digest_bytes", n, 52);
    check("digest_opcode", get32(out + 8), 0x50);
    (void)reply_digest(in, 0x50, 1);
    check("digest_ack", k60_charge_auth_receive(&a, in, 48, 6403), 1);
    check("digest_mark_state", a.state, K60ChargeGaugeMark);
    n = k60_charge_auth_next(&a, 6403, out);
    check("mark_bytes", n, 24);
    check("mark_property", get32(out + 16), 3);
    (void)reply(in, 0x51, 3, 1);
    (void)k60_charge_auth_receive(&a, in, 24, 6404);
    check("second_gauge_state", a.state, K60ChargeGaugeCheck);
    check("second_gauge_slave", a.slave, 1);
    check("second_gauge_verified", a.gauge_verified, 1);

    /* The K60 pack has one gauge: the first ack goes straight to the adapter. */
    k60_charge_auth_init(&a, &crypto);
    check("single_default", a.gauges, 1);
    k60_charge_auth_observe(&a, 1, 6, 8000);
    check("single_state", a.state, K60ChargeGaugeCheck);
    (void)k60_charge_auth_next(&a, 8000, out);
    (void)reply(in, 0x50, 3, 1);
    (void)k60_charge_auth_receive(&a, in, 24, 8001);
    check("single_adapter", a.state, K60ChargeAdapterCheck);
    check("single_verified", a.gauge_verified, 1);
    check("single_wait", k60_charge_auth_wait_ms(&a, 8001), 500);

    /* A timeout retries the challenge after 200 ms; reconnect cancels a pending
     * exchange and swallows its late reply. */
    k60_charge_auth_init(&a, &crypto);
    k60_charge_auth_observe(&a, 1, 6, 7000);
    (void)k60_charge_auth_next(&a, 7000, out);
    (void)reply(in, 0x50, 3, 0);
    (void)k60_charge_auth_receive(&a, in, 24, 7001);
    (void)k60_charge_auth_next(&a, 7001, out);
    k60_charge_auth_timeout(&a, 7002);
    check("timeout_count", a.timeouts, 1);
    check("timeout_retry_state", a.state, K60ChargeGaugeChallenge);
    check("timeout_retry_due", a.due_ms, 7202);
    check("timeout_wait", k60_charge_auth_wait_ms(&a, 7002), 200);
    check("timeout_before_due", k60_charge_auth_next(&a, 7201, out), 0);
    check("timeout_at_due", k60_charge_auth_next(&a, 7202, out), 52);

    k60_charge_auth_reconnect(&a, 7300);
    check("reconnect_cancelled", a.cancelled, 1);
    check("reconnect_pending", a.pending, 1);
    check("reconnect_offline", a.online, 0);
    (void)reply(in, 0x51, 1, 0);
    check("reconnect_swallows", k60_charge_auth_receive(&a, in, 24, 7301), 1);
    check("reconnect_clears_pending", a.pending, 0);
    check("reconnect_clears_cancelled", a.cancelled, 0);

    /* A reply for another property is not consumed, and a short reply to a
     * 52-byte get is a protocol error. */
    k60_charge_auth_init(&a, &crypto);
    k60_charge_auth_observe(&a, 1, 6, 9000);
    (void)k60_charge_auth_next(&a, 9000, out);
    (void)reply(in, 0x50, 4, 1);
    check("wrong_property_ignored", k60_charge_auth_receive(&a, in, 24, 9001), 0);
    check("wrong_property_pending", a.pending, 1);
    k60_charge_auth_timeout(&a, 9002);
    check("wrong_property_timeout", a.state, K60ChargeGaugeChallenge);
    (void)k60_charge_auth_next(&a, 9202, out);
    (void)reply(in, 0x51, 1, 0);
    (void)k60_charge_auth_receive(&a, in, 24, 9203);
    (void)k60_charge_auth_next(&a, 10603, out);
    (void)reply(in, 0x50, 1, 0);
    check("short_get_rejected", k60_charge_auth_receive(&a, in, 24, 10604), 1);
    check("short_get_result", a.last_result, -61);
    check("short_get_retry", a.state, K60ChargeGaugeChallenge);

    /* Ten unusable gauge replies exhaust the retry budget. */
    k60_charge_auth_init(&a, &crypto);
    k60_charge_auth_observe(&a, 1, 6, 12000);
    (void)k60_charge_auth_next(&a, 12000, out);
    (void)reply(in, 0x50, 3, 0);
    (void)k60_charge_auth_receive(&a, in, 24, 12001);
    {
        uint64_t now = 12001;
        for (unsigned i = 0; i < 10; ++i) {
            (void)k60_charge_auth_next(&a, now, out);
            k60_charge_auth_timeout(&a, now + 1);
            now = a.due_ms;
        }
    }
    check("retry_exhausted_diag", a.state, K60ChargeDiagnostics);
    check("retry_exhausted_result", a.last_result, -60);
    check("retry_exhausted_count", a.retries, 9);
    check("retry_exhausted_tries", a.tries, 10);

    /* Diagnostics reads 18 properties and ends Done on success. */
    k60_charge_auth_init(&a, &crypto);
    k60_charge_auth_observe(&a, 1, 6, 14000);
    (void)k60_charge_auth_next(&a, 14000, out);
    (void)reply(in, 0x50, 3, 1);
    (void)k60_charge_auth_receive(&a, in, 24, 14001);
    (void)k60_charge_auth_next(&a, 14501, out);
    (void)reply(in, 0x50, 0x17, 0x1234);
    (void)k60_charge_auth_receive(&a, in, 24, 14502);
    check("diag_after_svid", a.state, K60ChargeDiagnostics);
    (void)k60_charge_auth_next(&a, 15000, out);
    (void)reply_result(in, 0x50, out[16], -5);
    check("diag_error_ack", k60_charge_auth_receive(&a, in, 24, 15001), 1);
    check("diag_error_bit", (a.diagnostic_valid >> 0) & 1u, 0);
    check("diag_error_errors", a.errors, 1);
    for (unsigned i = 1; i < K60ChargeDiagnosticCount; ++i) {
        (void)k60_charge_auth_next(&a, 15001 + i, out);
        (void)reply(in, 0x50, out[16], 7);
        (void)k60_charge_auth_receive(&a, in, 24, 15001 + i);
    }
    check("diag_done_next", k60_charge_auth_next(&a, 16000, out), 0);
    check("diag_done_state", a.state, K60ChargeDone);
    check("diag_done_valid", a.diagnostic_valid, ((1u << K60ChargeDiagnosticCount) - 1u) & ~1u);

    printf("%s %u checks (%u failure%s)\n", failures ? "TESTS FAILED" : "TESTS OK",
        checks, failures, failures == 1 ? "" : "s");
    return failures ? 1 : 0;
}
