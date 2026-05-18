/*
 * image.h
 *
 * Application image layout, header parsing, CRC validation, digital-
 * signature verification, and RAM loading for the BSW.
 *
 * Flash layout of one image slot (128 KB):
 *   [0x0000 .. 0x0003]   CRC-32 (covers bytes [0x0004 .. IMAGE_OFFSET + imageSize - 1])
 *   [0x0004 .. 0x0005]   imageMagic  (IMAGE_MAGIC = 0xABCD)
 *   [0x0006 .. 0x0007]   imageVersion
 *   [0x0008 .. 0x000B]   imageSize   (application code size in bytes)
 *   [0x000C .. 0x100B]   signature[] (4096-byte field; unused bytes are zeroed)
 *   [IMAGE_OFFSET ..]    Application code (Cortex-M4 vector table + .text)
 *
 * The signed region is bytes [IMAGE_HEADER_DS_OFFSET .. IMAGE_OFFSET + imageSize - 1]
 * with the signature[] field zeroed, exactly matching how the uploader creates
 * the signature.
 *
 *  Created on: Dec 15, 2025
 *      Author: Matyas
 */

#ifndef INC_IMAGE_H_
#define INC_IMAGE_H_

#include <stdint.h>
#include "flash.h"

/* =========================================================================
 * Constants
 * ========================================================================= */

/** Magic value that identifies a valid image header. */
#define IMAGE_MAGIC 0xABCD

/** SRAM destination address where an image is loaded before execution. */
#define BOOT_RAM_ADDRESS 0x20008000

/**
 * Byte offset from the slot base address to the start of the application
 * code (= total header region size including the 4096-byte signature field).
 */
#define IMAGE_OFFSET 0x1400U

/**
 * Byte offset of the signature[] field within image_header_t.
 * Equals sizeof(crc) + sizeof(imageMagic) + sizeof(imageVersion) + sizeof(imageSize) = 12.
 * Used to zero the signature before computing or verifying the digest.
 */
#define IMAGE_HEADER_DS_OFFSET 12U

/* =========================================================================
 * Image header structure
 *
 * Stored at the base address of each flash slot.  All fields are packed
 * (no padding) so that a cast of the flash base address to image_header_t*
 * maps directly onto the on-flash layout.
 * ========================================================================= */
typedef struct __attribute__((packed))
{
	uint32_t crc;            /* CRC-32 of [imageMagic .. end of code]      */
	uint16_t imageMagic;     /* Must equal IMAGE_MAGIC (0xABCD)            */
	uint16_t imageVersion;   /* Monotonically increasing version number     */
	uint32_t imageSize;      /* Application code size in bytes              */
	uint8_t signature[4096]; /* Raw signature bytes; unused bytes zeroed   */
} image_header_t;

/* =========================================================================
 * API
 * ========================================================================= */

/**
 * Return a read-only pointer to the image header of @p slot.
 * Validates the magic number before returning; returns NULL if the slot
 * contains no recognisable image.
 *
 * @param slot  SLOT_A, SLOT_B, or RAM.
 * @return      Pointer to the image_header_t in flash/RAM, or NULL.
 */
const image_header_t* imageGetHeader(ImageSlot slot);

/**
 * Validate the CRC-32 of the image stored in @p slot (in flash).
 * Reads the header to obtain the stored CRC and image size, then recomputes
 * the CRC over the same byte range using the hardware CRC peripheral.
 *
 * @param slot  SLOT_A or SLOT_B.
 * @return      0 if the CRC matches, 1 on mismatch, 2 if no valid header.
 */
int16_t imageValidate(ImageSlot slot);

/**
 * Validate the CRC-32 of the image currently held in RAM (BOOT_RAM_ADDRESS).
 * The stored CRC is read from the header of @p slot (in flash); the RAM copy
 * is then recomputed and compared.
 *
 * @param slot  The flash slot whose header provides the reference CRC.
 * @return      0 if the CRC matches, 1 on mismatch, 2 if no valid header.
 */
int16_t imageValidateInRAM(ImageSlot slot);

/**
 * Copy the image from @p slot into RAM and verify its digital signature.
 * The signature field is zeroed in the RAM copy before verification, matching
 * the convention used during signing.  On success the RAM copy is ready for
 * imageStart(); on failure the RAM contents are undefined.
 *
 * @param slot  SLOT_A or SLOT_B.
 * @return      0 on success, 1 on signature failure, 2 if no valid header.
 */
int16_t imageLoad(ImageSlot slot);

/**
 * Jump to the application image loaded in RAM at BOOT_RAM_ADDRESS.
 * Reconfigures the Cortex-M4 vector table, resets the stack pointer, and
 * branches to the application reset handler.  This function does not return.
 */
void imageStart(void);

/**
 * Print a human-readable summary of the image headers stored in SLOT_A and
 * SLOT_B (magic, version, size, CRC) over the debug UART (printf).
 */
void printImageHeaders(void);

#endif /* INC_IMAGE_H_ */
