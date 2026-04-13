/*
 * sig_ecdsa.h — ECDSA-P256 + SHA-256 signature module (host benchmark tool).
 *
 * Keys are stored as raw DER files:
 *   private key : PKCS#8 DER (ECPrivateKey wrapped in PrivateKeyInfo)
 *   public  key : SubjectPublicKeyInfo DER (91 bytes for P-256)
 *
 * wolfSSL config required: HAVE_ECC (default in most builds).
 */

#ifndef BENCHMARK_SIG_ECDSA_H
#define BENCHMARK_SIG_ECDSA_H

#include "sig_algo.h"

#ifdef __cplusplus
extern "C" {
#endif

// Descriptor — pass to the generic benchmark runner.
extern const sig_algo_t sig_ecdsa;

#ifdef __cplusplus
}
#endif

#endif /* BENCHMARK_SIG_ECDSA_H */
