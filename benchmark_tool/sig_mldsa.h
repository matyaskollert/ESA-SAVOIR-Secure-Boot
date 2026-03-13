/*
 * sig_mldsa.h — ML-DSA (NIST FIPS 204 / Dilithium) signature module.
 *
 * Supports two parameter sets selected at runtime:
 *   ML_DSA_44  sig=2420 B  pub=1312 B  (wolfSSL level 2)
 *   ML_DSA_65  sig=3309 B  pub=1952 B  (wolfSSL level 3)
 *
 * Keys are stored as raw binary files.
 *
 * wolfSSL config required: HAVE_DILITHIUM, WOLFSSL_WC_DILITHIUM.
 */

#ifndef BENCHMARK_SIG_MLDSA_H
#define BENCHMARK_SIG_MLDSA_H

#include "sig_algo.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    ML_DSA_44 = 2,
    ML_DSA_65 = 3,
} ml_dsa_level_t;

/*
 * Return a sig_algo_t descriptor for the requested ML-DSA parameter set.
 * The returned pointer is valid for the lifetime of the process.
 * Returns NULL for an invalid level.
 */
const sig_algo_t* sig_mldsa_get(ml_dsa_level_t level);

#ifdef __cplusplus
}
#endif

#endif /* BENCHMARK_SIG_MLDSA_H */
