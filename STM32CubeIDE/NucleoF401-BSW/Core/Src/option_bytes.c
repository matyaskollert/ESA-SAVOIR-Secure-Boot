/*
 * option_bytes.c
 *
 *  Created on: Jan 19, 2026
 *      Author: Matyas
 */

#include "option_bytes.h"
#include "flash.h"
#include <stdio.h>

void disableSectorWriteProtection(uint32_t sector)
{
	if (checkSectorWriteProtection(sector) == 1)
	{
		return;
	}

	FLASH_OBProgramInitTypeDef obInit;

	HAL_FLASH_Unlock();
	HAL_FLASH_OB_Unlock();

	HAL_FLASHEx_OBGetConfig(&obInit);

	// printf("WRP status %lu\r\n", obInit.WRPSector);
	printf("Disabling WRP for Sector %lu\r\n", sector);

	obInit.OptionType = OPTIONBYTE_WRP;
	obInit.WRPState   = OB_WRPSTATE_DISABLE;
	obInit.WRPSector  = sector;

	if (HAL_FLASHEx_OBProgram(&obInit) != HAL_OK)
	{
		printf("WRP programming failed\r\n");
		HAL_FLASH_OB_Lock();
		HAL_FLASH_Lock();
		while (1);
	}

	printf("WRP programmed (will take effect after reset)\r\n");
	HAL_FLASH_OB_Launch();
	HAL_FLASH_OB_Lock();
	HAL_FLASH_Lock();
}

void enableSectorWriteProtection(uint32_t sector)
{

	if (checkSectorWriteProtection(sector) == 0)
	{
		return;
	}

	FLASH_OBProgramInitTypeDef obInit;

	HAL_FLASH_Unlock();
	HAL_FLASH_OB_Unlock();

	HAL_FLASHEx_OBGetConfig(&obInit);

	//printf("WRP status %lu\r\n", obInit.WRPSector);
	printf("Enabling WRP for Sector %lu\r\n", sector);

	obInit.OptionType = OPTIONBYTE_WRP;
	obInit.WRPState   = OB_WRPSTATE_ENABLE;
	obInit.WRPSector  = sector;

	if (HAL_FLASHEx_OBProgram(&obInit) != HAL_OK)
	{
		printf("WRP programming failed\r\n");
		HAL_FLASH_OB_Lock();
		HAL_FLASH_Lock();
		while (1);
	}

	printf("WRP programmed (will take effect after reset)\r\n");
	HAL_FLASH_OB_Launch();
	HAL_FLASH_OB_Lock();
	HAL_FLASH_Lock();
}

int16_t checkSectorWriteProtection(uint32_t sector)
{
	FLASH_OBProgramInitTypeDef obInit;
	HAL_FLASHEx_OBGetConfig(&obInit);

	if ((obInit.WRPSector & sector) == 0)
	{
		printf("Sector %lu is write protected\r\n", sector);
		return 0;
	}

	printf("Sector %lu is NOT write protected\r\n", sector);
	return 1;
}

int16_t performOBSelfTest(int8_t update)
{
	if (update == 0)
	{
		if (checkSectorWriteProtection(BOOT_FLASH_OB_SECTOR) == 1)
		{
			enableSectorWriteProtection(BOOT_FLASH_OB_SECTOR);
			return 1;
		}
		if (checkSectorWriteProtection(UPDATE_FLASH_OB_SECTOR) == 0)
		{
			disableSectorWriteProtection(UPDATE_FLASH_OB_SECTOR);
			return 2;
		}
		if (checkSectorWriteProtection(SWAP_FLASH_OB_SECTOR) == 1)
		{
			enableSectorWriteProtection(SWAP_FLASH_OB_SECTOR);
			return 3;
		}
	}
	else
	{
		if (checkSectorWriteProtection(BOOT_FLASH_OB_SECTOR) == 0)
		{
			disableSectorWriteProtection(BOOT_FLASH_OB_SECTOR);
			return -1;
		}
		if (checkSectorWriteProtection(UPDATE_FLASH_OB_SECTOR) == 0)
		{
			disableSectorWriteProtection(UPDATE_FLASH_OB_SECTOR);
			return -2;
		}
		if (checkSectorWriteProtection(SWAP_FLASH_OB_SECTOR) == 0)
		{
			disableSectorWriteProtection(SWAP_FLASH_OB_SECTOR);
			return -3;
		}
	}
	return 0;
}
