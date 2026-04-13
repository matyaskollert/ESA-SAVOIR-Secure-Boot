/*
 * crypto.h
 *
 *  Created on: Jan 26, 2026
 *      Author: Matyas
 *
 * Define POST_QUANTUM (compiler flag or in project settings) to select
 * ML-DSA signature verification instead of ECDSA-P256.
 *
 * Supported configurations
 * ──────────────────────────────────────────────────────────────────────
 *  POST_QUANTUM undefined  → ECDSA-P256 + SHA-256  (wolfSSL ECC)
 *  POST_QUANTUM defined    → ML-DSA-44  (wolfSSL WC Dilithium, level 2)
 *
 * When switching algorithms you must also:
 *  1. Replace pubKey[] in crypto.c with the key matching your algorithm.
 *  2. For ML-DSA: add POST_QUANTUM to wolfSSL.I-CUBE-wolfSSL_conf.h
 *     (or via project C defines) so that HAVE_DILITHIUM etc. are set.
 */

#ifndef INC_CRYPTO_H_
#define INC_CRYPTO_H_

#include <wolfssl/wolfcrypt/sha256.h>

#ifdef POST_QUANTUM
#include <wolfssl/wolfcrypt/dilithium.h>
/* Raw public-key sizes for each ML-DSA parameter set. */
#define ML_DSA_44_PUB_KEY_SIZE   DILITHIUM_LEVEL2_PUB_KEY_SIZE   /* 1312 bytes */
#define ML_DSA_65_PUB_KEY_SIZE   DILITHIUM_LEVEL3_PUB_KEY_SIZE   /* 1952 bytes */
/* Active parameter set — change to 3 for ML-DSA-65 (and update pubKey[]). */
#ifndef ML_DSA_LEVEL
#define ML_DSA_LEVEL  2
#endif
#endif /* POST_QUANTUM */

/**
 * Compute the SHA-256 digest of @p buffer.
 * @note  Not called internally by verifySignature() when POST_QUANTUM is
 *        defined — ML-DSA performs its own internal hashing.
 */
byte* hash(const byte* buffer, uint32_t bufferSize);

/**
 * Verify the digital signature over @p buffer.
 *
 * @param buffer      Pointer to the signed data region (header without CRC
 *                    + image data, with signature field zeroed).
 * @param bufferSize  Length of @p buffer in bytes.
 * @param signature   Pointer to the 4096-byte signature field in the header.
 *                    Only the first SIG_SIZE bytes are algorithmically
 *                    significant; the rest is padding.
 * @return  1 on valid signature, 0 on failure.
 */
int16_t verifySignature(const byte* buffer, uint32_t bufferSize, const byte* signature);

#endif /* INC_CRYPTO_H_ */
