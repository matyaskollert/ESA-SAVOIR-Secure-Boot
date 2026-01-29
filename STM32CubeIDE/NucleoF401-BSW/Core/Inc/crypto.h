/*
 * crypto.h
 *
 *  Created on: Jan 26, 2026
 *      Author: Matyas
 */

#ifndef INC_CRYPTO_H_
#define INC_CRYPTO_H_

#include <wolfssl/wolfcrypt/sha256.h>

byte* hash(const byte* buffer, uint32_t bufferSize);

int verifySignature(const byte* signature, word32 signatureLength);

#endif /* INC_CRYPTO_H_ */
