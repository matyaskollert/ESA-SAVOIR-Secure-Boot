/*
 * sig_mldsa.c — ML-DSA (NIST FIPS 204 / Dilithium), host benchmark tool.
 *
 * Three parameter sets, selected at runtime via sig_mldsa_get():
 *   ML_DSA_44  level=2  sig=2420 B  pub=1312 B  priv=2528 B
 *   ML_DSA_65  level=3  sig=3309 B  pub=1952 B  priv=4000 B
 *
 * Keys are raw binary files (no PEM encoding).
 *
 * wolfSSL config required:
 *   HAVE_DILITHIUM
 *   WOLFSSL_WC_DILITHIUM
 *   (remove WOLFSSL_DILITHIUM_NO_SIGN for host tool — we need signing)
 */

#include "sig_mldsa.h"
#include "io_utils.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <wolfssl/options.h>
#include <wolfssl/wolfcrypt/dilithium.h>
#include <wolfssl/wolfcrypt/random.h>
#include <wolfssl/wolfcrypt/error-crypt.h>

typedef struct {
    const char* name;
    int level;       // wolfSSL dilithium level: 2 or 3
    uint32_t sig_size;
    word32 pub_size;
    word32 priv_size;
} mldsa_info_t;

static const mldsa_info_t s_info[2] = {
    { "ML-DSA-44", 2, DILITHIUM_LEVEL2_SIG_SIZE,
      DILITHIUM_LEVEL2_PUB_KEY_SIZE, DILITHIUM_LEVEL2_PRV_KEY_SIZE },
    { "ML-DSA-65", 3, DILITHIUM_LEVEL3_SIG_SIZE,
      DILITHIUM_LEVEL3_PUB_KEY_SIZE, DILITHIUM_LEVEL3_PRV_KEY_SIZE },
};

typedef struct {
    dilithium_key key;
    int key_inited;
    WC_RNG rng;
    int rng_inited;
    const mldsa_info_t* info;
} mldsa_ctx_t;

static sig_ctx_t* mldsa_alloc_44(void)
{
    mldsa_ctx_t* context = (mldsa_ctx_t*)calloc(1, sizeof(mldsa_ctx_t));
    if (context)
        context->info = &s_info[0];
    return (sig_ctx_t*)context;
}

static sig_ctx_t* mldsa_alloc_65(void)
{
    mldsa_ctx_t* context = (mldsa_ctx_t*)calloc(1, sizeof(mldsa_ctx_t));
    if (context)
        context->info = &s_info[1];
    return (sig_ctx_t*)context;
}

static void mldsa_free(sig_ctx_t* ctx)
{
    mldsa_ctx_t* context = (mldsa_ctx_t*)ctx;
    if (!context)
        return;
    if (context->key_inited)
        wc_dilithium_free(&context->key);
    if (context->rng_inited)
        wc_FreeRng(&context->rng);
    free(context);
}

static int mldsa_generate_keys(sig_ctx_t* ctx,
                               const char* priv_path, const char* pub_path)
{
    mldsa_ctx_t* context = (mldsa_ctx_t*)ctx;
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

    result_code = wc_dilithium_init(&context->key);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_dilithium_init: %d\n", result_code);
        return result_code;
    }
    context->key_inited = 1;

    result_code = wc_dilithium_set_level(&context->key, context->info->level);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_dilithium_set_level: %d\n", result_code);
        return result_code;
    }

    result_code = wc_dilithium_make_key(&context->key, &context->rng);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_dilithium_make_key: %d\n", result_code);
        return result_code;
    }

    // Export private key raw bytes
    uint8_t* private_key_buffer = (uint8_t*)malloc(context->info->priv_size);
    uint8_t* public_key_buffer = (uint8_t*)malloc(context->info->pub_size);
    if (!private_key_buffer || !public_key_buffer)
    {
        free(private_key_buffer);
        free(public_key_buffer);
        return -1;
    }

    word32 private_key_len = context->info->priv_size;
    word32 public_key_len = context->info->pub_size;

    result_code = wc_dilithium_export_key(&context->key,
                                          private_key_buffer, &private_key_len,
                                          public_key_buffer, &public_key_len);
    if (result_code != 0)
    {
        free(private_key_buffer);
        free(public_key_buffer);
        fprintf(stderr, "wc_dilithium_export_key: %d\n", result_code);
        return result_code;
    }

    int write_status = io_write_file(priv_path, private_key_buffer, private_key_len);
    if (write_status == 0)
        write_status = io_write_file(pub_path, public_key_buffer, public_key_len);

    free(private_key_buffer);
    free(public_key_buffer);
    if (write_status != 0)
        return write_status;

    printf("    Private key : %s  (%u bytes)\n", priv_path, private_key_len);
    printf("    Public key  : %s  (%u bytes)\n", pub_path, public_key_len);
    return 0;
}

static int mldsa_load_keys(sig_ctx_t* ctx,
                           const char* priv_path, const char* pub_path)
{
    mldsa_ctx_t* context = (mldsa_ctx_t*)ctx;
    int result_code;

    if (context->key_inited)
    {
        wc_dilithium_free(&context->key);
        context->key_inited = 0;
    }
    result_code = wc_dilithium_init(&context->key);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_dilithium_init: %d\n", result_code);
        return result_code;
    }
    context->key_inited = 1;

    result_code = wc_dilithium_set_level(&context->key, context->info->level);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_dilithium_set_level: %d\n", result_code);
        return result_code;
    }

    if (priv_path)
    {
        uint8_t* file_buffer = NULL;
        size_t buffer_length = 0;
        if (io_read_file(priv_path, &file_buffer, &buffer_length) != 0)
            return -1;
        result_code = wc_dilithium_import_private(file_buffer, (word32)buffer_length,
                                                  &context->key);
        free(file_buffer);
        if (result_code != 0)
        {
            fprintf(stderr, "wc_dilithium_import_private: %d\n", result_code);
            return result_code;
        }
    }

    if (pub_path)
    {
        uint8_t* file_buffer = NULL;
        size_t buffer_length = 0;
        if (io_read_file(pub_path, &file_buffer, &buffer_length) != 0)
            return -1;
        result_code = wc_dilithium_import_public(file_buffer, (word32)buffer_length,
                                                 &context->key);
        free(file_buffer);
        if (result_code != 0)
        {
            fprintf(stderr, "wc_dilithium_import_public: %d\n", result_code);
            return result_code;
        }
    }

    return 0;
}

static int mldsa_sign(sig_ctx_t* ctx,
                      const uint8_t* msg, size_t msg_len,
                      uint8_t* sig_out, size_t* sig_written)
{
    mldsa_ctx_t* context = (mldsa_ctx_t*)ctx;
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

    word32 signature_len = context->info->sig_size;
    result_code = wc_dilithium_sign_msg(msg, (word32)msg_len,
                                        sig_out, &signature_len,
                                        &context->key, &context->rng);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_dilithium_sign_msg: %d\n", result_code);
        return result_code;
    }

    *sig_written = (size_t)signature_len;
    return 0;
}

static int mldsa_verify(sig_ctx_t* ctx,
                        const uint8_t* msg, size_t msg_len,
                        const uint8_t* sig, size_t sig_len)
{
    mldsa_ctx_t* context = (mldsa_ctx_t*)ctx;

    int verified = 0;
    int result_code = wc_dilithium_verify_msg(sig, (word32)sig_len,
                                              msg, (word32)msg_len,
                                              &verified, &context->key);
    if (result_code != 0)
    {
        fprintf(stderr, "wc_dilithium_verify_msg: %d\n", result_code);
        return result_code;
    }
    return verified;
}

static const sig_algo_t s_algo_44 = {
    .name          = "ML-DSA-44",
    .key_extension = ".bin",
    .sig_len       = DILITHIUM_LEVEL2_SIG_SIZE,
    .alloc         = mldsa_alloc_44,
    .free_ctx      = mldsa_free,
    .generate_keys = mldsa_generate_keys,
    .load_keys     = mldsa_load_keys,
    .sign          = mldsa_sign,
    .verify        = mldsa_verify,
};

static const sig_algo_t s_algo_65 = {
    .name          = "ML-DSA-65",
    .key_extension = ".bin",
    .sig_len       = DILITHIUM_LEVEL3_SIG_SIZE,
    .alloc         = mldsa_alloc_65,
    .free_ctx      = mldsa_free,
    .generate_keys = mldsa_generate_keys,
    .load_keys     = mldsa_load_keys,
    .sign          = mldsa_sign,
    .verify        = mldsa_verify,
};

const sig_algo_t* sig_mldsa_get(ml_dsa_level_t level)
{
    switch (level)
    {
        case ML_DSA_44:
            return &s_algo_44;
        case ML_DSA_65:
            return &s_algo_65;
        default:
            return NULL;
    }
}
