/*
 * bsw_rom_api.h  —  BSW ROM API: a fixed-address function table in BSW Flash.
 *
 * The BSW is stored starting at 0x08000000 and is write-protected (immutable).
 * At offset 0x200 (after the Cortex-M4 vector table, which ends at ~0x1B8),
 * the BSW places a small struct of function pointers — the ROM API table.
 *
 * Any project running after the BSW (e.g. the ASW) can call BSW services —
 * including digital signature verification with the BSW's own public keys —
 * simply by dereferencing this fixed address. The ASW does not need to
 * include wolfSSL or define any key material itself.
 *
 * Usage (ASW or any post-boot component):
 * ─────────────────────────────────────────────────────────────────────────
 *   #include "bsw_rom_api.h"
 *
 *   // Verify a dynamically loaded component
 *   int16_t ok = BSW_ROM_API->verifySignature(buffer, size, signature);
 *
 * ─────────────────────────────────────────────────────────────────────────
 *
 * Layout in BSW Flash (sector 0, 0x08000000 - 0x08003FFF):
 *
 *   0x08000000  ISR vector table   (max ~0x1B8 bytes for STM32F439)
 *   0x08000200  bsw_rom_api_t      (this table, placed by BSW linker script)
 *   0x08000210  .text continues …
 */

#ifndef BSP_INC_BSW_ROM_API_H_
#define BSP_INC_BSW_ROM_API_H_

#include <stdint.h>
#include <wolfssl/wolfcrypt/types.h>   /* byte, word32 */

/** Absolute Flash address where the BSW ROM API table lives. */
#define BSW_ROM_API_ADDRESS  0x08000200U

/**
 * BSW ROM API table.
 *
 * All function pointers use the same signatures as the corresponding
 * functions in NucleoF439-BSP/Inc/crypto.h so that call sites are
 * identical whether calling via ROM API or a direct link.
 *
 * Unused slots are reserved as NULL for future expansion without
 * breaking binary compatibility.
 */
typedef struct {
    /**
     * Verify a digital signature (ECDSA-P256 / ML-DSA-65 / Hybrid).
     * Compile-time scheme is fixed by BSW's build flags — the same
     * scheme is used for all verification calls through this API.
     *
     * @param buffer      Signed data (signature field zeroed).
     * @param bufferSize  Length of @p buffer in bytes.
     * @param signature   Raw signature bytes (4096-byte field).
     * @return 1 on success, 0 on failure.
     */
    int16_t (*verifySignature)(const byte *buffer, uint32_t bufferSize,
                               const byte *signature);

    /**
     * Compute the SHA-256 digest of @p buffer and print it.
     *
     * @param buffer      Data to hash.
     * @param bufferSize  Length of @p buffer in bytes.
     * @return Pointer to 32-byte digest buffer, or NULL on error.
     */
    byte *(*hash)(const byte *buffer, uint32_t bufferSize);

    /** Reserved for future entries — must be NULL. */
    void *reserved[6];
} bsw_rom_api_t;

/**
 * Dereference the ROM API table directly from BSW Flash.
 *
 * Example:
 *   int16_t ok = BSW_ROM_API->verifySignature(buf, len, sig);
 */
#define BSW_ROM_API  ((const bsw_rom_api_t *)(BSW_ROM_API_ADDRESS))

#endif /* BSP_INC_BSW_ROM_API_H_ */
