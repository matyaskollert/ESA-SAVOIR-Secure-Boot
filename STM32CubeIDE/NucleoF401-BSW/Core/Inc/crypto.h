/*
 * crypto.h
 *
 *  Created on: Jan 26, 2026
 *      Author: Matyas
 */

#ifndef INC_CRYPTO_H_
#define INC_CRYPTO_H_

#include <wolfssl/wolfcrypt/sha256.h>

byte* hash(const byte* buffer, uint32_t size);

int verify(const byte* signature, const byte* hsh, word32 sigLen);

#endif /* INC_CRYPTO_H_ */
