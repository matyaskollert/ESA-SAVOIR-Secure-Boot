
#include "crc.h"
#include "main.h"

// External CRC handle from main.c
extern CRC_HandleTypeDef hcrc;

uint32_t crc32_byte(uint32_t r)
{
	for(uint8_t j = 0; j < 8; ++j)
	{
		r = (r & 1? 0: (uint32_t)0xEDB88320L) ^ r >> 1;
	}
	return r ^ (uint32_t)0xFF000000L;
}



uint32_t crc32(const void *data, uint32_t sizeBytes)
{
	uint32_t crc = 0;
	static uint32_t table[0x100];
	if(!*table)
	{
		for(uint16_t i = 0; i < 0x100; ++i)
		{
			table[i] = crc32_byte(i);
		}
	}
	for(uint32_t i = 0; i < sizeBytes; ++i)
	{
		crc = table[(uint8_t)crc ^ ((uint8_t*)data)[i]] ^ crc >> 8;
	}
	return crc;
}


uint32_t crc32_hw(const void *data, uint32_t sizeBytes)
{
	uint32_t sizeWords = sizeBytes / 4;
	uint32_t crcResult = HAL_CRC_Calculate(&hcrc, (uint32_t *) data, sizeWords);
	return crcResult;
}
