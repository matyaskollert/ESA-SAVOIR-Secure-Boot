/*
 * benchmark.h
 *
 * Digital-signature benchmark for the NucleoF439.
 *
 * ── HOW TO SWITCH ALGORITHMS ─────────────────────────────────────────────
 * Edit the #define BENCHMARK_ALGO line below, OR set BENCHMARK_ALGO as a
 * compiler -D flag in:
 *   IDE → Project → Properties → C/C++ Build → Settings →
 *         MCU GCC Compiler → Preprocessor → Defined symbols
 *
 * All sig_*.c files may remain in the project; #if guards ensure only the
 * active algorithm compiles and links.
 *
 * ── ALGORITHM TABLE ──────────────────────────────────────────────────────
 *  ALGO_ECDSA       ECDSA-P256 + SHA-256          sig: ~72 B   pub: 91 B
 *  ALGO_RSA_3072    RSA-3072-PSS + SHA-256         sig: 384 B   pub: ~423 B
 *  ALGO_RSA_4096    RSA-4096-PSS + SHA-256         sig: 512 B   pub: ~550 B
 *  ALGO_ML_DSA_44   ML-DSA-44  (Dilithium L2)     sig: 2420 B  pub: 1312 B
 *  ALGO_ML_DSA_65   ML-DSA-65  (Dilithium L3)     sig: 3309 B  pub: 1952 B
 *  ALGO_LMS         LMS-SHA256-M32-H5/OTS-N32-W8  sig: ~1292 B pub:   60 B
 *
 * † ML-DSA-87 signature (4595 B) exceeds the current 4096-byte signature
 *   field in image_header_t. Increase signature[] to at least 4627 bytes
 *   and regenerate the image before benchmarking ML-DSA-87.
 *
 * ── WOLFSSL COMPILE DEFINES REQUIRED PER ALGORITHM ───────────────────────
 *  ECDSA:     HAVE_ECC                            (wolfSSL default)
 *  RSA:       WC_RSA_PSS, !NO_RSA                (wolfSSL default)
 *  ML-DSA:    HAVE_DILITHIUM, WOLFSSL_DILITHIUM_NO_SIGN
 *  LMS:       WOLFSSL_HAVE_LMS
 * ─────────────────────────────────────────────────────────────────────────
 */

#ifndef INC_BENCHMARK_H_
#define INC_BENCHMARK_H_

#define ALGO_ECDSA 1
#define ALGO_RSA_3072 2
#define ALGO_RSA_4096 3
#define ALGO_ML_DSA_44 4
#define ALGO_ML_DSA_65 5
#define ALGO_LMS 6

// SHOULD be overridden via a -D compiler flag without editing this file.
#ifndef BENCHMARK_ALGO
#define BENCHMARK_ALGO ALGO_ECDSA
#endif

// Compile-time guard against invalid values.
#if BENCHMARK_ALGO < ALGO_ECDSA || BENCHMARK_ALGO > ALGO_LMS
#error "BENCHMARK_ALGO must be one of ALGO_ECDSA..ALGO_LMS (1..6)"
#endif

// Number of verify() calls to average over.
#ifndef BENCHMARK_ITERATIONS
#define BENCHMARK_ITERATIONS 3
#endif

/**
 * Load the MAIN image from SLOT_A_FLASH_ADDRESS into RAM, zero its signature
 * field, then verify the signature BENCHMARK_ITERATIONS times using the
 * algorithm selected by BENCHMARK_ALGO.  Timing and pass/fail results are
 * printed over UART (printf).
 */
void benchmarkRun(void);

#endif /* INC_BENCHMARK_H_ */
