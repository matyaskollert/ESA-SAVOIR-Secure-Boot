/*
 * sig_rsa.c — RSA-PSS + SHA-256, host benchmark tool.
 *
 * Supports two key sizes selected at runtime via sig_rsa_get():
 *   RSA_3072  sig=384 B  pub=~423 B (SubjectPublicKeyInfo DER)
 *   RSA_4096  sig=512 B  pub=~550 B (SubjectPublicKeyInfo DER)
 *
 * Key storage: DER files.
 *   Private key : PKCS#1 DER  (wc_RsaKeyToDer / wc_RsaPrivateKeyDecode)
 *   Public  key : SubjectPublicKeyInfo DER  (wc_RsaPublicKeyDecode)
 *
 * Signing   : wc_RsaPSS_Sign_ex (hash=SHA-256, mgf=MGF1-SHA256, salt=MAX)
 * Verifying : wc_RsaPSS_Verify_ex + wc_RsaPSS_CheckPadding_ex
 *
 * wolfSSL config required: WC_RSA_PSS, !NO_RSA (default).
 */

#include "sig_rsa.h"
#include "io_utils.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <wolfssl/options.h>
#include <wolfssl/wolfcrypt/rsa.h>
#include <wolfssl/wolfcrypt/sha256.h>
#include <wolfssl/wolfcrypt/asn_public.h>
#include <wolfssl/wolfcrypt/random.h>
#include <wolfssl/wolfcrypt/error-crypt.h>

typedef struct
{
	int key_bits;
	int sig_bytes;
	const char* name;
} rsa_info_t;

static const rsa_info_t s_info[2] = {
    {3072, 384, "RSA-3072-PSS"},
    {4096, 512, "RSA-4096-PSS"},
};

typedef struct
{
	RsaKey key;
	int key_inited;
	WC_RNG rng;
	int rng_inited;
	const rsa_info_t* info;
} rsa_ctx_t;

static sig_ctx_t* rsa_alloc_3072(void)
{
	rsa_ctx_t* context = (rsa_ctx_t*)calloc(1, sizeof(rsa_ctx_t));
	if (context)
		context->info = &s_info[0];
	return (sig_ctx_t*)context;
}

static sig_ctx_t* rsa_alloc_4096(void)
{
	rsa_ctx_t* context = (rsa_ctx_t*)calloc(1, sizeof(rsa_ctx_t));
	if (context)
		context->info = &s_info[1];
	return (sig_ctx_t*)context;
}

static void rsa_free(sig_ctx_t* ctx)
{
	rsa_ctx_t* context = (rsa_ctx_t*)ctx;
	if (!context)
		return;
	if (context->key_inited)
		wc_FreeRsaKey(&context->key);
	if (context->rng_inited)
		wc_FreeRng(&context->rng);
	free(context);
}

static int rsa_generate_keys(sig_ctx_t* ctx, const char* priv_path, const char* pub_path)
{
	rsa_ctx_t* context = (rsa_ctx_t*)ctx;
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

	result_code = wc_InitRsaKey(&context->key, NULL);
	if (result_code != 0)
	{
		fprintf(stderr, "wc_InitRsaKey: %d\n", result_code);
		return result_code;
	}
	context->key_inited = 1;

	result_code = wc_MakeRsaKey(&context->key, context->info->key_bits, 65537, &context->rng);
	if (result_code != 0)
	{
		fprintf(stderr, "wc_MakeRsaKey: %d\n", result_code);
		return result_code;
	}

	// Export private key as PKCS#1 DER
	uint8_t* priv_der = (uint8_t*)malloc(5000);
	if (!priv_der)
		return -1;
	int priv_len = wc_RsaKeyToDer(&context->key, priv_der, 5000);
	if (priv_len <= 0)
	{
		free(priv_der);
		fprintf(stderr, "wc_RsaKeyToDer: %d\n", priv_len);
		return -1;
	}

	// Export public key as SubjectPublicKeyInfo DER
	uint8_t* pub_der = (uint8_t*)malloc(700);
	if (!pub_der)
	{
		free(priv_der);
		return -1;
	}
	int pub_len = wc_RsaKeyToPublicDer(&context->key, pub_der, 700);
	if (pub_len <= 0)
	{
		free(priv_der);
		free(pub_der);
		fprintf(stderr, "wc_RsaKeyToPublicDer: %d\n", pub_len);
		return -1;
	}

	int write_status = io_write_file(priv_path, priv_der, (size_t)priv_len);
	if (write_status == 0)
		write_status = io_write_file(pub_path, pub_der, (size_t)pub_len);

	free(priv_der);
	free(pub_der);

	if (write_status != 0)
		return write_status;
	printf("    Private key : %s  (%d bytes)\n", priv_path, priv_len);
	printf("    Public key  : %s  (%d bytes DER)\n", pub_path, pub_len);
	return 0;
}

static int rsa_load_keys(sig_ctx_t* ctx, const char* priv_path, const char* pub_path)
{
	rsa_ctx_t* context = (rsa_ctx_t*)ctx;
	int result_code;

	if (context->key_inited)
	{
		wc_FreeRsaKey(&context->key);
		context->key_inited = 0;
	}
	result_code = wc_InitRsaKey(&context->key, NULL);
	if (result_code != 0)
	{
		fprintf(stderr, "wc_InitRsaKey: %d\n", result_code);
		return result_code;
	}
	context->key_inited = 1;

	if (priv_path)
	{
		uint8_t* file_buffer = NULL;
		size_t buffer_length = 0;
		if (io_read_file(priv_path, &file_buffer, &buffer_length) != 0)
			return -1;
		word32 decode_index = 0;
		result_code         = wc_RsaPrivateKeyDecode(file_buffer, &decode_index, &context->key,
		                                             (word32)buffer_length);
		free(file_buffer);
		if (result_code != 0)
		{
			fprintf(stderr, "wc_RsaPrivateKeyDecode: %d\n", result_code);
			return result_code;
		}
	}

	if (pub_path)
	{
		uint8_t* file_buffer = NULL;
		size_t buffer_length = 0;
		if (io_read_file(pub_path, &file_buffer, &buffer_length) != 0)
			return -1;
		word32 decode_index = 0;
		result_code =
		    wc_RsaPublicKeyDecode(file_buffer, &decode_index, &context->key, (word32)buffer_length);
		free(file_buffer);
		if (result_code != 0)
		{
			fprintf(stderr, "wc_RsaPublicKeyDecode: %d\n", result_code);
			return result_code;
		}
	}

	return 0;
}

static int rsa_sign(sig_ctx_t* ctx, const uint8_t* msg, size_t msg_len, uint8_t* sig_out,
                    size_t* sig_written)
{
	rsa_ctx_t* context = (rsa_ctx_t*)ctx;
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

	// SHA-256 digest
	uint8_t digest[WC_SHA256_DIGEST_SIZE];
	wc_Sha256 sha;
	wc_InitSha256(&sha);
	wc_Sha256Update(&sha, msg, (word32)msg_len);
	wc_Sha256Final(&sha, digest);
	wc_Sha256Free(&sha);

	// RSA-PSS sign: hash=SHA-256, mgf=MGF1-SHA256, saltLen=WC_SHA256_DIGEST_SIZE
	result_code = wc_RsaPSS_Sign_ex(
	    digest, WC_SHA256_DIGEST_SIZE, sig_out, (word32)context->info->sig_bytes,
	    WC_HASH_TYPE_SHA256, WC_MGF1SHA256, WC_SHA256_DIGEST_SIZE, &context->key, &context->rng);
	if (result_code != context->info->sig_bytes)
	{
		fprintf(stderr, "wc_RsaPSS_Sign: %d\n", result_code);
		return (result_code < 0) ? result_code : -1;
	}

	*sig_written = (size_t)context->info->sig_bytes;
	return 0;
}

static int rsa_verify(sig_ctx_t* ctx, const uint8_t* msg, size_t msg_len, const uint8_t* sig,
                      size_t sig_len)
{
	rsa_ctx_t* context = (rsa_ctx_t*)ctx;

	uint8_t digest[WC_SHA256_DIGEST_SIZE];
	wc_Sha256 sha;
	wc_InitSha256(&sha);
	wc_Sha256Update(&sha, msg, (word32)msg_len);
	wc_Sha256Final(&sha, digest);
	wc_Sha256Free(&sha);

	uint8_t dec_buf[512];  // max size for RSA-4096

	int result_code = wc_RsaPSS_Verify_ex((byte*)sig, (word32)sig_len, dec_buf, sizeof(dec_buf),
	                                      WC_HASH_TYPE_SHA256, WC_MGF1SHA256, WC_SHA256_DIGEST_SIZE,
	                                      &context->key);
	if (result_code < 0)
	{
		fprintf(stderr, "wc_RsaPSS_Verify_ex: %d\n", result_code);
		return 0;
	}

	result_code =
	    wc_RsaPSS_CheckPadding_ex(digest, WC_SHA256_DIGEST_SIZE, dec_buf, (word32)result_code,
	                              WC_HASH_TYPE_SHA256, WC_SHA256_DIGEST_SIZE, 0);
	if (result_code != 0)
	{
		fprintf(stderr, "wc_RsaPSS_CheckPadding_ex: %d\n", result_code);
		return 0;
	}
	return 1;
}

static const sig_algo_t s_algo_3072 = {
    .name          = "RSA-3072-PSS",
    .key_extension = ".der",
    .sig_len       = 384,
    .alloc         = rsa_alloc_3072,
    .free_ctx      = rsa_free,
    .generate_keys = rsa_generate_keys,
    .load_keys     = rsa_load_keys,
    .sign          = rsa_sign,
    .verify        = rsa_verify,
};

static const sig_algo_t s_algo_4096 = {
    .name          = "RSA-4096-PSS",
    .key_extension = ".der",
    .sig_len       = 512,
    .alloc         = rsa_alloc_4096,
    .free_ctx      = rsa_free,
    .generate_keys = rsa_generate_keys,
    .load_keys     = rsa_load_keys,
    .sign          = rsa_sign,
    .verify        = rsa_verify,
};

const sig_algo_t* sig_rsa_get(rsa_bits_t bits)
{
	switch (bits)
	{
	case RSA_3072:
		return &s_algo_3072;
	case RSA_4096:
		return &s_algo_4096;
	default:
		return NULL;
	}
}
