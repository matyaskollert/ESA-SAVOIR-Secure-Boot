/*
 * sig_lms.c  —  LMS-SHA256-M32-H5 / LMOTS-SHA256-N32-W8 benchmark
 *
 * Parameter set summary
 * ─────────────────────
 *   LMS  :  LMS_SHA256_M32_H5   tree height=5, n=32 (SHA-256/256)
 *   OTS  :  LMOTS_SHA256_N32_W8 Winternitz param w=8  (p=34 chain elements)
 *   Public key  : 60 bytes  (4-byte type + 4-byte L + 32-byte T[1] + 20 extra)
 *                 (verify exact size via wc_LmsKey_GetPubLen after SetParameters)
 *   Signature   : ~1292 bytes  (fits within the 4096-byte image sig field)
 *   Key-pair capacity: 2^5 = 32 one-time signatures per key pair
 *
 * For longer-lived keys, consider H=10 (1024 OTS) or an HSS two-level tree.
 *
 * wolfSSL config required:  WOLFSSL_HAVE_LMS
 *
 * Key update workflow
 * ───────────────────
 * 1. Generate an LMS key pair with wolfSSL or an external LMS tool.
 * 2. Export the raw public key (60 bytes for H5/N32).
 * 3. Paste it into pubKey[] below.
 *
 * LMS parameter constants used (wolfSSL wc_lms.h):
 *   WC_LMS_PARM_SHA256_M32_H5       — LMS tree: SHA-256/256, height 5
 *   WC_LMS_PARM_LMOTS_SHA256_N32_W8 — OTS: SHA-256/256, w=8
 * Adjust to WC_LMS_PARM_SHA256_M32_H10 / _H15 / _H20 for larger key caps.
 */

#include "benchmark.h"
#if BENCHMARK_ALGO == ALGO_LMS

#include "sig_algo.h"
#include <wolfssl/wolfcrypt/lms.h>
#include <wolfssl/wolfcrypt/wc_lms.h>
#include <stdio.h>

/* Raw public key size for LMS-SHA256-M32-H5 (type+L+T1 = 60 bytes in RFC 8554
 * single-tree format).  Confirm with wc_LmsKey_GetPubLen() if in doubt.    */
#define LMS_PUB_SIZE  60U

/* Signature size for LMS-SHA256-M32-H5 / LMOTS-SHA256-N32-W8:
 *   [q(4)] + [OTS type(4) + C(32) + y_0..y_33 (34×32=1088)] + [auth_1..5 (5×32=160)]
 *   = 4 + 4 + 32 + 1088 + 160 = 1288 bytes
 * Actual wolfSSL output for L1/H5/W8 is 1296 bytes (includes 8-byte HSS header). */
#define LMS_SIG_SIZE  1296U

// TODO: Replace with your raw LMS public key (LMS_PUB_SIZE bytes).
static const byte pubKey[LMS_PUB_SIZE] = {
	0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00, 0x04,
	0xef, 0x6d, 0x91, 0x76, 0x72, 0x4b, 0xd9, 0xd6, 0x56, 0x30, 0xd7, 0xa0,
	0x49, 0x7d, 0x34, 0x20, 0x33, 0x48, 0x0a, 0x57, 0xa4, 0xa2, 0x9e, 0xf4,
	0xca, 0x75, 0x5d, 0xda, 0xa8, 0x9c, 0xbd, 0xca, 0x83, 0x77, 0xb2, 0x2d,
	0xc4, 0xbe, 0x7d, 0x9c, 0x2b, 0x45, 0x4b, 0x1b, 0x8a, 0xe2, 0x27, 0x38
};

static LmsKey lmsKey;

static int16_t algo_init(void)
{
    int ret = wc_LmsKey_Init(&lmsKey, NULL, INVALID_DEVID);
    if (ret != 0) { printf("wc_LmsKey_Init: %d\r\n", ret); return ret; }

    // Single HSS level (levels=1), LMS tree type, OTS type.
    // Note: wc_LmsKey_SetParameters signature is (key, levels, lm_type, ots_type).
    ret = wc_LmsKey_SetLmsParm(&lmsKey, WC_LMS_PARM_L1_H5_W8);
    if (ret != 0)
    {
        printf("wc_LmsKey_SetParameters: %d\r\n", ret);
        wc_LmsKey_Free(&lmsKey);
        return ret;
    }

    // Note: wc_LmsKey_ImportPubRaw signature is (key, in, inLen).
    ret = wc_LmsKey_ImportPubRaw(&lmsKey, pubKey, LMS_PUB_SIZE);
    if (ret != 0)
    {
        printf("wc_LmsKey_ImportPubRaw: %d\r\n", ret);
        wc_LmsKey_Free(&lmsKey);
        return ret;
    }
    return 0;
}

static int16_t algo_verify(const byte* msg, uint32_t msgLen,
                           const byte* sig, uint32_t sigLen)
{
    int ret = wc_LmsKey_Verify(&lmsKey, sig, sigLen, msg, (int)msgLen);
    if (ret != 0) { printf("wc_LmsKey_Verify: %d\r\n", ret); return 0; }
    return 1;
}

static void algo_cleanup(void)
{
    wc_LmsKey_Free(&lmsKey);
}

const sig_algo_t g_algo = {
    .name    = "LMS-SHA256-H5-W8",
    .init    = algo_init,
    .verify  = algo_verify,
    .cleanup = algo_cleanup,
    .sig_len = LMS_SIG_SIZE
};

#endif // BENCHMARK_ALGO == ALGO_LMS
