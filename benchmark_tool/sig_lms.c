/*
 * sig_lms.c — LMS-SHA256-M32-H5 / LMOTS-SHA256-N32-W8, host benchmark tool.
 *
 * Parameter set:
 *   Single HSS level, WC_LMS_PARM_L1_H5_W8
 *   Public key  : 60 bytes
 *   Signature   : ~1292 bytes
 *   Key capacity: 2^5 = 32 one-time signatures per key pair.
 *
 * LMS is STATEFUL — private key state is updated and written back after
 * every sign() call so that one-time keys are never reused.
 *
 * wolfSSL config required: WOLFSSL_HAVE_LMS.
 *
 * wolfcrypt LMS key write callback stores the private key state.
 * We use a file-backed callback approach, matching wolfSSL's intended API.
 */

#include "sig_lms.h"
#include "io_utils.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <wolfssl/options.h>
#include <wolfssl/wolfcrypt/lms.h>
#include <wolfssl/wolfcrypt/wc_lms.h>
#include <wolfssl/wolfcrypt/random.h>
#include <wolfssl/wolfcrypt/error-crypt.h>

#define LMS_PUB_SIZE   60U
#define LMS_SIG_SIZE   1296U   // L1/H5/W8: actual computed length

typedef struct {
    char priv_path[512];
} lms_write_state_t;

static int lms_write_cb(const byte* priv, word32 priv_len,
                        void* context)
{
    lms_write_state_t* st = (lms_write_state_t*)context;
    if (io_write_file(st->priv_path, priv, (size_t)priv_len) != 0)
        return WC_LMS_RC_WRITE_FAIL;
    return WC_LMS_RC_SAVED_TO_NV_MEMORY;
}

static int lms_read_cb(byte* priv, word32 priv_len, void* context)
{
    lms_write_state_t* write_state = (lms_write_state_t*)context;
    uint8_t* private_key_buffer = NULL;
    size_t private_key_len = 0;
    if (io_read_file(write_state->priv_path, &private_key_buffer, &private_key_len) != 0)
        return WC_LMS_RC_READ_FAIL;

    if (private_key_len < (size_t)priv_len)
    {
        free(private_key_buffer);
        return WC_LMS_RC_READ_FAIL;
    }

    memcpy(priv, private_key_buffer, (size_t)priv_len);
    free(private_key_buffer);
    return WC_LMS_RC_READ_TO_MEMORY;
}

typedef struct {
    LmsKey key;
    int key_inited;
    WC_RNG rng;
    int rng_inited;
    lms_write_state_t ws;          // write-state holds priv_path for callback
} lms_ctx_t;

static sig_ctx_t* lms_alloc(void)
{
    lms_ctx_t* context = (lms_ctx_t*)calloc(1, sizeof(lms_ctx_t));
    return (sig_ctx_t*)context;
}

static void lms_free(sig_ctx_t* ctx)
{
    lms_ctx_t* context = (lms_ctx_t*)ctx;
    if (!context)
        return;
    if (context->key_inited)
        wc_LmsKey_Free(&context->key);
    if (context->rng_inited)
        wc_FreeRng(&context->rng);
    free(context);
}

/* Initialise a fresh key object with our parameter set.
 * for_load=0 → keygen path: only write_cb is registered (MakeKey must not
 *                            call read_cb, as the file doesn't exist yet).
 * for_load=1 → load path:   both write_cb and read_cb are registered so
 *                            wc_LmsKey_Reload can read the saved state. */
static int lms_init_key(lms_ctx_t* context, int for_load)
{
    int result_code = wc_LmsKey_Init(&context->key, NULL, INVALID_DEVID);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_LmsKey_Init: %d\n", result_code);
        return result_code;
    }
    context->key_inited = 1;

    result_code = wc_LmsKey_SetLmsParm(&context->key, WC_LMS_PARM_L1_H5_W8);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_LmsKey_SetLmsParm: %d\n", result_code);
        return result_code;
    }

    // Always register write-back callback so key state is persisted after sign
    result_code = wc_LmsKey_SetWriteCb(&context->key, lms_write_cb);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_LmsKey_SetWriteCb: %d\n", result_code);
        return result_code;
    }

    if (for_load)
    {
        /* Read callback is only needed for wc_LmsKey_Reload (load path).
         * Setting it during MakeKey causes wolfSSL to call it internally
         * before the full key has been written, triggering IO_FAILED_E. */
        result_code = wc_LmsKey_SetReadCb(&context->key, lms_read_cb);
        if (result_code != 0)
        {
            fprintf(stderr, "wc_LmsKey_SetReadCb: %d\n", result_code);
            return result_code;
        }
    }

    // Bind the write-state context (holds priv_path) to both callbacks
    result_code = wc_LmsKey_SetContext(&context->key, &context->ws);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_LmsKey_SetContext: %d\n", result_code);
        return result_code;
    }

    return 0;
}

static int lms_generate_keys(sig_ctx_t* ctx,
                             const char* priv_path, const char* pub_path)
{
    lms_ctx_t* context = (lms_ctx_t*)ctx;
    int result_code;

    if (!context->rng_inited)
    {
        result_code = wc_InitRng(&context->rng);
        if (result_code != 0)
        {
            fprintf(stderr, "wc_InitRng: %d\n", result_code);
            return result_code;
        }
        context->rng_inited = 1;
    }

    if (context->key_inited)
    {
        wc_LmsKey_Free(&context->key);
        context->key_inited = 0;
    }

    // Store priv_path in write-state before initialising, so the callback fires correctly
    strncpy(context->ws.priv_path, priv_path, sizeof(context->ws.priv_path) - 1);

    // Key generation does not need the read callback.
    result_code = lms_init_key(context, 0);
    if (result_code != 0)
        return result_code;

    result_code = wc_LmsKey_MakeKey(&context->key, &context->rng);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_LmsKey_MakeKey: %d\n", result_code);
        return result_code;
    }

    // Export public key
    uint8_t public_key_buffer[LMS_PUB_SIZE];
    word32 public_key_len = LMS_PUB_SIZE;
    result_code = wc_LmsKey_ExportPubRaw(&context->key, public_key_buffer, &public_key_len);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_LmsKey_ExportPubRaw: %d\n", result_code);
        return result_code;
    }

    if (io_write_file(pub_path, public_key_buffer, (size_t)public_key_len) != 0)
        return -1;

    printf("    Private key : %s  (stateful, written by callback)\n", priv_path);
    printf("    Public key  : %s  (%u bytes)\n", pub_path, public_key_len);
    return 0;
}

static int lms_load_keys(sig_ctx_t* ctx,
                         const char* priv_path, const char* pub_path)
{
    lms_ctx_t* context = (lms_ctx_t*)ctx;
    int result_code;

    if (context->key_inited)
    {
        wc_LmsKey_Free(&context->key);
        context->key_inited = 0;
    }

    if (priv_path)
        strncpy(context->ws.priv_path, priv_path, sizeof(context->ws.priv_path) - 1);

    // Key reload needs the read callback so wolfSSL can restore state.
    result_code = lms_init_key(context, 1);
    if (result_code != 0)
        return result_code;

    if (priv_path)
    {
        /* wc_LmsKey_Reload queries the key size then calls lms_read_cb to
         * fill the private key buffer — no ImportPrivRaw function exists. */
        result_code = wc_LmsKey_Reload(&context->key);
        if (result_code != 0)
        {
            fprintf(stderr, "wc_LmsKey_Reload: %d\n", result_code);
            return result_code;
        }
    }

    if (pub_path)
    {
        uint8_t* file_buffer = NULL;
        size_t buffer_length = 0;
        if (io_read_file(pub_path, &file_buffer, &buffer_length) != 0)
            return -1;
        result_code = wc_LmsKey_ImportPubRaw(&context->key, file_buffer,
                                             (word32)buffer_length);
        free(file_buffer);
        if (result_code != 0)
        {
            fprintf(stderr, "wc_LmsKey_ImportPubRaw: %d\n", result_code);
            return result_code;
        }
    }

    return 0;
}

static int lms_sign(sig_ctx_t* ctx,
                    const uint8_t* msg, size_t msg_len,
                    uint8_t* sig_out, size_t* sig_written)
{
    lms_ctx_t* context = (lms_ctx_t*)ctx;

    word32 signature_len = LMS_SIG_SIZE;
    int result_code = wc_LmsKey_Sign(&context->key, sig_out, &signature_len,
                                     (byte*)msg, (word32)msg_len);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_LmsKey_Sign: %d\n", result_code);
        return result_code;
    }

    *sig_written = (size_t)signature_len;
    return 0;
}

static int lms_verify(sig_ctx_t* ctx,
                      const uint8_t* msg, size_t msg_len,
                      const uint8_t* sig, size_t sig_len)
{
    lms_ctx_t* context = (lms_ctx_t*)ctx;

    int result_code = wc_LmsKey_Verify(&context->key,
                                       (byte*)sig, (word32)sig_len,
                                       (byte*)msg, (word32)msg_len);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_LmsKey_Verify: %d\n", result_code);
        return 0;
    }
    return 1;
}

const sig_algo_t sig_lms = {
    .name          = "LMS-SHA256-H5-W8",
    .key_extension = ".bin",
    .sig_len       = LMS_SIG_SIZE,
    .alloc         = lms_alloc,
    .free_ctx      = lms_free,
    .generate_keys = lms_generate_keys,
    .load_keys     = lms_load_keys,
    .sign          = lms_sign,
    .verify        = lms_verify,
};
