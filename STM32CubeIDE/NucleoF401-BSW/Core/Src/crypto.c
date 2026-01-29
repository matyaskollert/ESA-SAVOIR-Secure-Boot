/*
 * crypto.c
 *
 *  Created on: Jan 26, 2026
 *      Author: Matyas
 */

#include "crypto.h"
#include <wolfssl/wolfcrypt/asn_public.h>
#include <wolfssl/wolfcrypt/ecc.h>

const byte pubKey[] = {
		0x30, 0x59, 0x30, 0x13, 0x06, 0x07, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x02,
		0x01, 0x06, 0x08, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x03, 0x01, 0x07, 0x03,
		0x42, 0x00, 0x04, 0x61, 0x57, 0xcb, 0x35, 0xae, 0x44, 0x7f, 0xd9, 0xdc,
		0x8b, 0xf0, 0xd2, 0x06, 0xf0, 0xf6, 0x42, 0x90, 0xcd, 0xfe, 0xf3, 0x66,
		0xca, 0xe6, 0xae, 0xe8, 0x10, 0xdc, 0x2d, 0x51, 0xee, 0xa8, 0xe6, 0xbe,
		0xc9, 0x54, 0xa1, 0x3e, 0x81, 0x49, 0xb5, 0x74, 0x65, 0x14, 0xb5, 0x04,
		0x14, 0x32, 0x3f, 0xb8, 0xe5, 0x16, 0x6d, 0xb8, 0x53, 0xe8, 0x29, 0x56,
		0x1e, 0xf3, 0x33, 0x78, 0x22, 0xcd, 0xb6
};

byte hashDigest[WC_SHA256_DIGEST_SIZE];
Sha256 sha;

void printSha256(const uint8_t *digest) {
    for (int i = 0; i < WC_SHA256_DIGEST_SIZE; i++) {
        printf("%02x", digest[i]);
    }
    printf("\n");
}

byte* hash(const byte* buffer, uint32_t size) {


	wc_InitSha256(&sha);

	wc_Sha256Update(&sha, buffer, size);  /*can be called again
	                                          and again*/
	wc_Sha256Final(&sha, hashDigest);

	printSha256(hashDigest);

	return hashDigest;
}

int verifySignature(const byte* signature, word32 signatureLength) {
	ecc_key eccKey;
	word32 inOutIdx = 0;
	int ret, verified = 0;

	ret = wc_EccPublicKeyDecode(pubKey, &inOutIdx, &eccKey, sizeof(pubKey));
	ret = wc_ecc_set_curve(&eccKey, 32, ECC_SECP256R1);
	
	// Debug: Print signature
	printf("Signature (%u bytes): ", signatureLength);
	for (int i = 0; i < signatureLength; i++) {
		printf("%02x", signature[i]);
	}
	printf("\r\n");
	
	ret = wc_ecc_verify_hash(signature, signatureLength, hashDigest, WC_SHA256_DIGEST_SIZE,
	&verified, &eccKey);
	
	printf("wc_ecc_verify_hash returned: %d\r\n", ret);
	printf("verified flag: %d\r\n", verified);
	
	wc_ecc_free(&eccKey);
	if ( ret != 0 ) {
		printf("Error performing verification\r\n");
		return 0;
	} else if ( verified == 0 ) {
	    printf("The signature is invalid\r\n");
	    return 0;
	}
	return 1;
}
