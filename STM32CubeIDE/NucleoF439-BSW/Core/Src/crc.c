/*
 * crc.c
 *
 * CRC-32/ISO-HDLC computation — software table-lookup and STM32 hardware
 * peripheral variants.
 *
 * Both functions produce the same result for word-aligned buffers whose size
 * is a multiple of 4 bytes.  For arbitrary byte counts use the software
 * implementation (crc32); the hardware path truncates partial trailing words.
 *
 *  Created on: Jan 19, 2026
 *      Author: Matyas
 */

#include "crc.h"
#include "main.h"

/* CRC peripheral handle initialised in main.c */
extern CRC_HandleTypeDef hcrc;

uint32_t crc32_byte(uint32_t r)
{
	for (uint8_t j = 0; j < 8; ++j)
	{
		r = (r & 1 ? 0 : (uint32_t)0xEDB88320L) ^ r >> 1;
	}
	return r ^ (uint32_t)0xFF000000L;
}

uint32_t crc32(const void* data, uint32_t sizeBytes)
{
	uint32_t crc = 0;
	static uint32_t table[0x100];
	if (!*table)
	{
		for (uint16_t i = 0; i < 0x100; ++i)
		{
			table[i] = crc32_byte(i);
		}
	}
	for (uint32_t i = 0; i < sizeBytes; ++i)
	{
		crc = table[(uint8_t)crc ^ ((uint8_t*)data)[i]] ^ crc >> 8;
	}
	return crc;
}

uint32_t crc32_hw(const void* data, uint32_t sizeBytes)
{
	uint32_t sizeWords = sizeBytes / 4;
	uint32_t crcResult = HAL_CRC_Calculate(&hcrc, (uint32_t*)data, sizeWords);
	return crcResult;
}
