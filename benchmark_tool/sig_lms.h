/*
 * sig_lms.h — LMS-SHA256-M32-H5 / LMOTS-SHA256-N32-W8 signature module.
 *
 * Parameter set:
 *   Single HSS level, LMS-SHA256-M32-H5, LMOTS-SHA256-N32-W8.
 *   Public key  : 60 bytes
 *   Signature   : ~1292 bytes (fits within the 4096-byte SIGNATURE_FIELD)
 *   Key capacity: 2^5 = 32 one-time signatures per key pair.
 *
 * LMS is STATEFUL — each signing consumes one one-time key.
 * The updated private key state is written back to disk after every sign().
 *
 * Keys are stored as raw binary files.
 *
 * wolfSSL config required: WOLFSSL_HAVE_LMS.
 */

#ifndef BENCHMARK_SIG_LMS_H
#define BENCHMARK_SIG_LMS_H

#include "sig_algo.h"

#ifdef __cplusplus
extern "C" {
#endif

extern const sig_algo_t sig_lms;

#ifdef __cplusplus
}
#endif

#endif /* BENCHMARK_SIG_LMS_H */
