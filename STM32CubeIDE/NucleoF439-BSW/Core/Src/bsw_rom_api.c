/*
 * bsw_rom_api.c
 *
 *  Created on: May 4, 2026
 *      Author: Matyas
 *
 * Instantiates the BSW ROM API table at the fixed Flash address 0x08000200.
 *
 * The table contains function pointers into BSW code (verifySignature, hash)
 * so that any post-boot application can call these services — including
 * signature verification against the BSW's own embedded public keys —
 * without needing to link wolfSSL or hold any key material itself.
 *
 * The public keys embedded in crypto.c remain exclusively in the immutable BSW.
 */

#include "bsw_rom_api.h"
#include "crypto.h"

/**
 * The ROM API table instance.
 *
 * Placed in section ".rom_api" which the linker script fixes at 0x08000200.
 * Declared const so the compiler keeps it in Flash (read-only data).
 * KEEP() in the linker script prevents the linker from discarding it as
 * "unused" even though no BSW code calls it through the table.
 */
const bsw_rom_api_t g_bsw_rom_api
    __attribute__((section(".rom_api"), used)) =
{
    .verifySignature = verifySignature,
    .hash            = hash,
    .reserved        = { NULL, NULL, NULL, NULL, NULL, NULL },
};
