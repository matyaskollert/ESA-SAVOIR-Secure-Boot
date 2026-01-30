/*
 * option_bytes.c
 *
 *  Created on: Jan 19, 2026
 *      Author: Matyas
 */

#include "option_bytes.h"
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
	NVIC_SystemReset();

	printf("This should not be printed\r\n");
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
	NVIC_SystemReset();

	printf("This should not be printed\r\n");
}

uint32_t checkSectorWriteProtection(uint32_t sector)
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
