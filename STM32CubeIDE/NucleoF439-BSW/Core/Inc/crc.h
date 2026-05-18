/*
 * crc.h
 *
 * CRC-32 computation — software (table-lookup) and hardware (STM32 CRC
 * peripheral) variants.
 *
 * Both functions compute the same CRC-32/ISO-HDLC polynomial (0xEDB88320,
 * reflected) used by zlib / PNG.  The hardware path processes data in
 * 32-bit word chunks and is significantly faster on large buffers; the
 * software path accepts any byte count.
 *
 *  Created on: Jan 19, 2026
 *      Author: Matyas
 */

#ifndef INC_CRC_H_
#define INC_CRC_H_

#include <stdint.h>
#include <stddef.h>

/**
 * Compute the CRC-32/ISO-HDLC checksum of @p data in software.
 * Uses a 256-entry table built on the first call (lazy initialisation).
 *
 * @param data       Pointer to the data to checksum.
 * @param sizeBytes  Number of bytes to process.
 * @return           32-bit CRC value.
 */
uint32_t crc32(const void* data, uint32_t sizeBytes);

/**
 * Compute the CRC-32 checksum of @p data using the STM32 hardware CRC unit.
 * The CRC peripheral is initialised by main() before this function is called.
 * Only complete 32-bit words are fed to the peripheral; trailing bytes that
 * do not form a full word are currently ignored (sizeBytes must be a multiple
 * of 4 for correct results).
 *
 * @param data       Pointer to the data to checksum (word-aligned).
 * @param sizeBytes  Number of bytes to process (should be a multiple of 4).
 * @return           32-bit CRC value from the hardware peripheral.
 */
uint32_t crc32_hw(const void* data, uint32_t sizeBytes);

#endif /* INC_CRC_H_ */
