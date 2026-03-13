/*
 * sig_algo.h — Abstract signature-algorithm interface for the host benchmark tool.
 *
 * Each sig_*.c file implements this interface for one algorithm family.
 * All algorithms support key generation, key load/save, signing, and verification.
 *
 * wolfcrypt is used for all cryptographic operations.
 */

#ifndef BENCHMARK_SIG_ALGO_H
#define BENCHMARK_SIG_ALGO_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Opaque handle passed to every operation.
 * The implementation allocates and fills this in sig_*_alloc().
 */
typedef struct sig_ctx sig_ctx_t;

typedef struct {
    // Human-readable algorithm name used in output and filenames.
    const char* name;

    // File extension for persistent key files: ".pem" or ".bin".
    const char* key_extension;

    // Expected raw signature length in bytes.
    uint32_t sig_len;

    /**
     * Allocate and return a fresh, uninitialised context.
     * Returns NULL on allocation failure.
     */
    sig_ctx_t* (*alloc)(void);

    /**
     * Free a context previously returned by alloc().
     * Safe to call with ctx == NULL.
     */
    void (*free_ctx)(sig_ctx_t* ctx);

    /**
     * Generate a new key pair and write the raw bytes to disk.
     *
     * @param ctx          Algorithm context (must be allocated, not yet loaded).
     * @param priv_path    File path for the private key.
     * @param pub_path     File path for the public key.
     * @return 0 on success, negative on failure.
     */
    int (*generate_keys)(sig_ctx_t* ctx,
                         const char* priv_path, const char* pub_path);

    /**
     * Load an existing key pair from disk into ctx.
     * Pass NULL for a path to skip loading that half.
     *
     * @return 0 on success, negative on failure.
     */
    int (*load_keys)(sig_ctx_t* ctx,
                     const char* priv_path, const char* pub_path);

    /**
     * Sign a message.
     *
     * @param ctx       Algorithm context with private key loaded.
     * @param msg       Message bytes.
     * @param msg_len   Message length.
     * @param sig_out   Output buffer; caller must allocate at least sig_len bytes.
     * @param sig_written  Set to the number of bytes actually written.
     * @return 0 on success, negative on failure.
     */
    int (*sign)(sig_ctx_t* ctx,
                const uint8_t* msg, size_t msg_len,
                uint8_t* sig_out, size_t* sig_written);

    /**
     * Verify a signature.
     *
     * @param ctx       Algorithm context with public key loaded.
     * @param msg       Message bytes.
     * @param msg_len   Message length.
     * @param sig       Signature bytes.
     * @param sig_len   Signature length.
     * @return 1 = valid, 0 = invalid, negative = error.
     */
    int (*verify)(sig_ctx_t* ctx,
                  const uint8_t* msg, size_t msg_len,
                  const uint8_t* sig, size_t sig_len);
} sig_algo_t;

#ifdef __cplusplus
}
#endif

#endif /* BENCHMARK_SIG_ALGO_H */
