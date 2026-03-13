/*
 * sig_ecdsa.c  —  ECDSA-P256 + SHA-256 benchmark implementation
 *
 * wolfSSL config: HAVE_ECC (enabled by default in wolfSSL builds).
 *
 * Key update workflow
 * ───────────────────
 * 1. Generate / export the ECDSA-P256 public key:
 *      python uploader/pem_to_c_array.py keys/public_key_<ts>.pem
 * 2. Paste the printed byte array into pubKeyDer[] below.
 *    The DER SubjectPublicKeyInfo for P-256 is always 91 bytes.
 */

#include "benchmark.h"
#if BENCHMARK_ALGO == ALGO_ECDSA

#include "sig_algo.h"
#include <wolfssl/wolfcrypt/ecc.h>
#include <wolfssl/wolfcrypt/asn_public.h>
#include <wolfssl/wolfcrypt/sha256.h>
#include <stdio.h>

/* DER-encoded SubjectPublicKeyInfo for ECDSA-P256 (91 bytes).
 * Replace with output of:  python pem_to_c_array.py keys/public_key_<ts>.pem */
static const byte pubKeyDer[] = {
	0x30, 0x59, 0x30, 0x13, 0x06, 0x07, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x02,
	0x01, 0x06, 0x08, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x03, 0x01, 0x07, 0x03,
	0x42, 0x00, 0x04, 0xa3, 0xed, 0xaa, 0x6c, 0x6e, 0x70, 0x64, 0x53, 0x34,
	0xe2, 0x91, 0xed, 0xe2, 0x3d, 0xe9, 0xef, 0xd2, 0xd6, 0x8b, 0x8d, 0xad,
	0xde, 0x0b, 0xb6, 0x13, 0x7a, 0xf7, 0x77, 0xfe, 0xda, 0x85, 0x67, 0x4f,
	0x70, 0x51, 0xb3, 0x9b, 0x39, 0x02, 0x83, 0x1f, 0xf2, 0x42, 0x5f, 0x19,
	0x92, 0x59, 0x37, 0x37, 0x86, 0x6d, 0xb7, 0x95, 0xb2, 0x2e, 0xac, 0xed,
	0x11, 0xb8, 0x42, 0xc8, 0xbd, 0x6a, 0xb0
};

static ecc_key eccKey;

static int16_t algo_init(void)
{
    word32 idx = 0;
    int ret = wc_ecc_init(&eccKey);
    if (ret != 0) { printf("wc_ecc_init: %d\r\n", ret); return ret; }

    ret = wc_EccPublicKeyDecode(pubKeyDer, &idx, &eccKey, sizeof(pubKeyDer));
    if (ret != 0)
    {
        printf("wc_EccPublicKeyDecode: %d\r\n", ret);
        wc_ecc_free(&eccKey);
        return ret;
    }
    return 0;
}

static int16_t algo_verify(const byte* msg, uint32_t msgLen,
                           const byte* sig, uint32_t sigLen)
{
    // Hash the message with SHA-256.
    byte digest[WC_SHA256_DIGEST_SIZE];
    Sha256 sha;
    wc_InitSha256(&sha);
    wc_Sha256Update(&sha, msg, msgLen);
    wc_Sha256Final(&sha, digest);

    // Read the actual DER signature length from the ASN.1 SEQUENCE tag/length.
    if (sig[0] != 0x30)
    {
        printf("ECDSA: unexpected sig tag 0x%02x\r\n", sig[0]);
        return 0;
    }
    word32 derLen = (word32)sig[1] + 2U;  // tag(1) + len(1) + payload
    if (derLen > sigLen) derLen = sigLen;

    int verified = 0;
    int ret = wc_ecc_verify_hash(sig, derLen, digest, WC_SHA256_DIGEST_SIZE,
                                 &verified, &eccKey);
    if (ret != 0) { printf("wc_ecc_verify_hash: %d\r\n", ret); return 0; }
    return (int16_t)verified;
}

static void algo_cleanup(void)
{
    wc_ecc_free(&eccKey);
}

const sig_algo_t g_algo = {
    .name    = "ECDSA-P256",
    .init    = algo_init,
    .verify  = algo_verify,
    .cleanup = algo_cleanup,
    // Max DER-encoded ECDSA-P256 signature: 2 + 2*(2+33) = 72 bytes.
    .sig_len = 72U
};

#endif // BENCHMARK_ALGO == ALGO_ECDSA
