/*
 * sig_rsa.h — RSA-2048-PSS + SHA-256 signature module (host benchmark tool).
 *
 * Keys are stored as DER files:
 *   private key : PKCS#8 DER
 *   public  key : SubjectPublicKeyInfo DER (~294 bytes for RSA-2048)
 *
 * wolfSSL config required: WC_RSA_PSS, !NO_RSA (default in most builds).
 */

#ifndef BENCHMARK_SIG_RSA_H
#define BENCHMARK_SIG_RSA_H

#include "sig_algo.h"

#ifdef __cplusplus
extern "C" {
#endif

extern const sig_algo_t sig_rsa;

#ifdef __cplusplus
}
#endif

#endif /* BENCHMARK_SIG_RSA_H */
