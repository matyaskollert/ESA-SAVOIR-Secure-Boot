/*
 * sig_algo.h
 *
 * Abstract signature-algorithm interface used internally by benchmark.c.
 * Each sig_*.c file defines exactly one instance of sig_algo_t named g_algo,
 * guarded by #if BENCHMARK_ALGO == ALGO_* so that only the active algorithm
 * contributes symbols to the link.
 */

#ifndef INC_SIG_ALGO_H_
#define INC_SIG_ALGO_H_

#include <stdint.h>
#include <wolfssl/wolfcrypt/types.h>

typedef struct
{
	// Human-readable name printed in benchmark output.
	const char* name;

	/**
     * Import the public key and initialise any algorithm state.
     * Called once before the benchmark loop.
     * @return 0 on success, non-zero on failure.
     */
	int16_t (*init)(void);

	/**
     * Verify a digital signature.
     * @param msg      Pointer to the signed data (header without CRC + image).
     * @param msg_len  Length of signed data in bytes.
     * @param sig      Pointer to the raw signature bytes from the image header.
     * @param sig_len  Algorithm-specific signature length (from g_algo.sig_len).
     * @return  1 = valid, 0 = invalid / error.
     */
	int16_t (*verify)(const byte* msg, uint32_t msg_len, const byte* sig, uint32_t sig_len);

	// Release any resources acquired by init(). Called after the loop.
	void (*cleanup)(void);

	// Expected signature length in bytes for this algorithm.
	uint32_t sig_len;
} sig_algo_t;

// Provided by whichever sig_*.c file is compiled for the active algorithm.
extern const sig_algo_t g_algo;

#endif /* INC_SIG_ALGO_H_ */
