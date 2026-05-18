/*
 * sig_ecdsa.c — ECDSA-P256 + SHA-256, host benchmark tool.
 *
 * Key storage: raw DER files.
 *   Private key : PKCS#8 DER  (wc_EccKeyToDer / wc_EccPrivateKeyDecode)
 *   Public  key : SubjectPublicKeyInfo DER, 91 bytes
 *                 (wc_EccPublicKeyToDer / wc_EccPublicKeyDecode)
 *
 * Signing   : SHA-256 hash → wc_ecc_sign_hash (DER-encoded output)
 * Verifying : SHA-256 hash → wc_ecc_verify_hash
 *
 * wolfSSL config required: HAVE_ECC (default).
 */

#include "sig_ecdsa.h"
#include "io_utils.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <wolfssl/options.h>
#include <wolfssl/wolfcrypt/ecc.h>
#include <wolfssl/wolfcrypt/sha256.h>
#include <wolfssl/wolfcrypt/asn_public.h>
#include <wolfssl/wolfcrypt/random.h>
#include <wolfssl/wolfcrypt/error-crypt.h>

typedef struct
{
	ecc_key key;
	int key_inited;
	WC_RNG rng;
	int rng_inited;
} ecdsa_ctx_t;

static sig_ctx_t* ecdsa_alloc(void)
{
	ecdsa_ctx_t* context = (ecdsa_ctx_t*)calloc(1, sizeof(ecdsa_ctx_t));
	return (sig_ctx_t*)context;
}

static void ecdsa_free(sig_ctx_t* ctx)
{
	ecdsa_ctx_t* context = (ecdsa_ctx_t*)ctx;
	if (!context)
		return;
	if (context->key_inited)
		wc_ecc_free(&context->key);
	if (context->rng_inited)
		wc_FreeRng(&context->rng);
	free(context);
}

static int ecdsa_generate_keys(sig_ctx_t* ctx, const char* priv_path, const char* pub_path)
{
	ecdsa_ctx_t* context = (ecdsa_ctx_t*)ctx;
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

	result_code = wc_ecc_init(&context->key);
	if (result_code != 0)
	{
		fprintf(stderr, "wc_ecc_init: %d\n", result_code);
		return result_code;
	}
	context->key_inited = 1;

	result_code = wc_ecc_make_key(&context->rng, 32, &context->key);  // 32 bytes -> P-256
	if (result_code != 0)
	{
		fprintf(stderr, "wc_ecc_make_key: %d\n", result_code);
		return result_code;
	}

	// Export private key as PKCS#8 DER
	uint8_t priv_der[256];
	int priv_len = wc_EccKeyToDer(&context->key, priv_der, sizeof(priv_der));
	if (priv_len <= 0)
	{
		fprintf(stderr, "wc_EccKeyToDer: %d\n", priv_len);
		return -1;
	}

	// Export public key as SubjectPublicKeyInfo DER
	uint8_t pub_der[128];
	int pub_len = wc_EccPublicKeyToDer(&context->key, pub_der, sizeof(pub_der), 1);
	if (pub_len <= 0)
	{
		fprintf(stderr, "wc_EccPublicKeyToDer: %d\n", pub_len);
		return -1;
	}

	if (io_write_file(priv_path, priv_der, (size_t)priv_len) != 0)
		return -1;
	if (io_write_file(pub_path, pub_der, (size_t)pub_len) != 0)
		return -1;

	printf("    Private key : %s  (%d bytes)\n", priv_path, priv_len);
	printf("    Public key  : %s  (%d bytes DER)\n", pub_path, pub_len);
	return 0;
}

static int ecdsa_load_keys(sig_ctx_t* ctx, const char* priv_path, const char* pub_path)
{
	ecdsa_ctx_t* context = (ecdsa_ctx_t*)ctx;
	int result_code;

	if (context->key_inited)
	{
		wc_ecc_free(&context->key);
		context->key_inited = 0;
	}
	result_code = wc_ecc_init(&context->key);
	if (result_code != 0)
	{
		fprintf(stderr, "wc_ecc_init: %d\n", result_code);
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
		result_code         = wc_EccPrivateKeyDecode(file_buffer, &decode_index, &context->key,
		                                             (word32)buffer_length);
		free(file_buffer);
		if (result_code != 0)
		{
			fprintf(stderr, "wc_EccPrivateKeyDecode: %d\n", result_code);
			return result_code;
		}
		// The SEC1 DER produced by wc_EccKeyToDer embeds the public key, so
		// it is already imported above. Loading the SPKI pub file on top would
		// overwrite the key type to ECC_PUBLICKEY and lose the private scalar.
		return 0;
	}

	if (pub_path)
	{
		uint8_t* file_buffer = NULL;
		size_t buffer_length = 0;
		if (io_read_file(pub_path, &file_buffer, &buffer_length) != 0)
			return -1;
		word32 decode_index = 0;
		result_code =
		    wc_EccPublicKeyDecode(file_buffer, &decode_index, &context->key, (word32)buffer_length);
		free(file_buffer);
		if (result_code != 0)
		{
			fprintf(stderr, "wc_EccPublicKeyDecode: %d\n", result_code);
			return result_code;
		}
	}

	return 0;
}

static int ecdsa_sign(sig_ctx_t* ctx, const uint8_t* msg, size_t msg_len, uint8_t* sig_out,
                      size_t* sig_written)
{
	ecdsa_ctx_t* context = (ecdsa_ctx_t*)ctx;
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

	// Associate the RNG with the key. Required when the key was loaded from
	// DER rather than freshly generated (wc_ecc_make_key does this implicitly).
	wc_ecc_set_rng(&context->key, &context->rng);

	// SHA-256 digest
	uint8_t digest[WC_SHA256_DIGEST_SIZE];
	wc_Sha256 sha;
	wc_InitSha256(&sha);
	wc_Sha256Update(&sha, msg, (word32)msg_len);
	wc_Sha256Final(&sha, digest);
	wc_Sha256Free(&sha);

	// DER-encoded ECDSA signature; max 72 bytes for P-256
	word32 sig_len = 72;
	result_code = wc_ecc_sign_hash(digest, WC_SHA256_DIGEST_SIZE, sig_out, &sig_len, &context->rng,
	                               &context->key);
	if (result_code != 0)
	{
		fprintf(stderr, "wc_ecc_sign_hash: %d\n", result_code);
		return result_code;
	}

	*sig_written = (size_t)sig_len;
	return 0;
}

static int ecdsa_verify(sig_ctx_t* ctx, const uint8_t* msg, size_t msg_len, const uint8_t* sig,
                        size_t sig_len)
{
	ecdsa_ctx_t* context = (ecdsa_ctx_t*)ctx;

	uint8_t digest[WC_SHA256_DIGEST_SIZE];
	wc_Sha256 sha;
	wc_InitSha256(&sha);
	wc_Sha256Update(&sha, msg, (word32)msg_len);
	wc_Sha256Final(&sha, digest);
	wc_Sha256Free(&sha);

	// Determine actual DER length from ASN.1 SEQUENCE tag
	word32 der_len = (word32)sig_len;
	if (sig_len >= 2 && sig[0] == 0x30)
		der_len = (word32)sig[1] + 2u;
	if (der_len > (word32)sig_len)
		der_len = (word32)sig_len;

	int verified = 0;
	int result_code =
	    wc_ecc_verify_hash(sig, der_len, digest, WC_SHA256_DIGEST_SIZE, &verified, &context->key);
	if (result_code != 0)
	{
		fprintf(stderr, "wc_ecc_verify_hash: %d\n", result_code);
		return result_code;
	}
	return verified;
}

const sig_algo_t sig_ecdsa = {
    .name          = "ECDSA-P256",
    .key_extension = ".der",
    .sig_len       = 72U,
    .alloc         = ecdsa_alloc,
    .free_ctx      = ecdsa_free,
    .generate_keys = ecdsa_generate_keys,
    .load_keys     = ecdsa_load_keys,
    .sign          = ecdsa_sign,
    .verify        = ecdsa_verify,
};
