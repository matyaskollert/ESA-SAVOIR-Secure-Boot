/*
 * flash.c
 *
 *  Created on: Jan 19, 2026
 *      Author: Matyas
 */


#include "flash.h"
#include <stdio.h>

int16_t eraseFlashSector(uint32_t sector)
{
	FLASH_EraseInitTypeDef eraseInit;
	uint32_t sectorError;

	eraseInit.TypeErase    = FLASH_TYPEERASE_SECTORS;
	eraseInit.Sector       = sector;
	eraseInit.NbSectors    = 1;
	eraseInit.VoltageRange = FLASH_VOLTAGE_RANGE_3;

	if (HAL_FLASHEx_Erase(&eraseInit, &sectorError) != HAL_OK)
	{
		printf("Flash erase failed\r\n");
		// return 1 whatever happens with lockFlash, ignore output
		HAL_FLASH_Lock();
		return 1;
	}
	return 0;
}

int16_t writeFlashWord(uint32_t address, uint32_t value)
{
	if (HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD,
			address, value) != HAL_OK)
	{
		printf("Flash program failed\r\n");
		// return 1 whatever happens with lockFlash, ignore output
		HAL_FLASH_Lock();
		return 1;
	}
	return 0;
}

int16_t writeFlashBlock(uint32_t address, uint32_t* buffer, uint32_t bufferSize)
{
	for (uint32_t i = 0; i < bufferSize; i++)
	{
		if (writeFlashWord(address + 4*i, buffer[i]) != 0)
		{
			return 1;
		}
	}
	return 0;
}


int16_t writeFlashSector(uint32_t sector, uint32_t address, uint32_t* buffer, uint32_t bufferSize)
{
	if (HAL_FLASH_Unlock() != HAL_OK)
	{
		return 1;
	}

	if (eraseFlashSector(sector) != 0)
	{
		return 1;
	}

	printf("First address: 0x%08lx and first word: 0x%08lx\r\n", address, buffer[0]);

	for (uint32_t i = 0; i < bufferSize; i++)
	{
		if (writeFlashWord(address + 4*i, buffer[i]) != 0)
		{
			return 1;
		}
	}

	if (HAL_FLASH_Lock() != HAL_OK)
	{
		return 1;
	}

	return 0;
}
