/*
 * sig_rsa.h — RSA-PSS + SHA-256 signature module (host benchmark tool).
 *
 * Supports two key sizes selected at runtime:
 *   RSA_3072  sig=384 B  pub=~423 B (SubjectPublicKeyInfo DER)
 *   RSA_4096  sig=512 B  pub=~550 B (SubjectPublicKeyInfo DER)
 *
 * Keys are stored as DER files:
 *   private key : PKCS#1 DER
 *   public  key : SubjectPublicKeyInfo DER
 *
 * wolfSSL config required: WC_RSA_PSS, !NO_RSA (default in most builds).
 */

#ifndef BENCHMARK_SIG_RSA_H
#define BENCHMARK_SIG_RSA_H

#include "sig_algo.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    RSA_3072 = 3072,
    RSA_4096 = 4096,
} rsa_bits_t;

/*
 * Return a sig_algo_t descriptor for the requested RSA key size.
 * The returned pointer is valid for the lifetime of the process.
 * Returns NULL for an unsupported key size.
 */
const sig_algo_t* sig_rsa_get(rsa_bits_t bits);


#ifdef __cplusplus
}
#endif

#endif /* BENCHMARK_SIG_RSA_H */
