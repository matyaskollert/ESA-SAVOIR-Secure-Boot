/*
 * option_bytes.c
 *
 *  Created on: Jan 19, 2026
 *      Author: Matyas
 */

#include "option_bytes.h"
#include "flash.h"
#include <stdio.h>
#include "main.h"

int16_t disableSectorWriteProtection(uint32_t sectorMask)
{
	if (checkSectorWriteProtection(sectorMask) == 1)
	{
		return 0;
	}

	FLASH_OBProgramInitTypeDef obInit;

	if (HAL_FLASH_Unlock() != HAL_OK)
	{
		printf("FLASH unlock failed\r\n");
		return -1;
	}
	if (HAL_FLASH_OB_Unlock() != HAL_OK)
	{
		printf("OB unlock failed\r\n");
		if (HAL_FLASH_Lock() != HAL_OK)
			printf("FLASH lock failed\r\n");
		return -1;
	}

	HAL_FLASHEx_OBGetConfig(&obInit);

	// printf("WRP status %lu\r\n", obInit.WRPSector);
	printf("Disabling WRP for Sector %lu\r\n", sectorMask);

	obInit.OptionType = OPTIONBYTE_WRP;
	obInit.WRPState   = OB_WRPSTATE_DISABLE;
	obInit.WRPSector  = sectorMask;

	if (HAL_FLASHEx_OBProgram(&obInit) != HAL_OK)
	{
		printf("WRP programming failed\r\n");
		if (HAL_FLASH_OB_Lock() != HAL_OK)
			printf("OB lock failed\r\n");
		if (HAL_FLASH_Lock() != HAL_OK)
			printf("FLASH lock failed\r\n");
		return -1;
	}

	if (HAL_FLASH_OB_Launch() != HAL_OK)
	{
		printf("OB launch failed\r\n");
		if (HAL_FLASH_OB_Lock() != HAL_OK)
			printf("OB lock failed\r\n");
		if (HAL_FLASH_Lock() != HAL_OK)
			printf("FLASH lock failed\r\n");
		return -1;
	}
	if (HAL_FLASH_OB_Lock() != HAL_OK)
		printf("OB lock failed\r\n");
	if (HAL_FLASH_Lock() != HAL_OK)
		printf("FLASH lock failed\r\n");
	printf("WRP programmed (will take effect after reset)\r\n");
	NVIC_SystemReset();
}

int16_t enableSectorWriteProtection(uint32_t sectorMask)
{

	if (checkSectorWriteProtection(sectorMask) == 0)
	{
		return 0;
	}

	FLASH_OBProgramInitTypeDef obInit;

	if (HAL_FLASH_Unlock() != HAL_OK)
	{
		printf("FLASH unlock failed\r\n");
		return -1;
	}
	if (HAL_FLASH_OB_Unlock() != HAL_OK)
	{
		printf("OB unlock failed\r\n");
		if (HAL_FLASH_Lock() != HAL_OK)
			printf("FLASH lock failed\r\n");
		return -1;
	}

	HAL_FLASHEx_OBGetConfig(&obInit);

	//printf("WRP status %lu\r\n", obInit.WRPSector);
	printf("Enabling WRP for Sector %lu\r\n", sectorMask);

	obInit.OptionType = OPTIONBYTE_WRP;
	obInit.WRPState   = OB_WRPSTATE_ENABLE;
	obInit.WRPSector  = sectorMask;

	if (HAL_FLASHEx_OBProgram(&obInit) != HAL_OK)
	{
		printf("WRP programming failed\r\n");
		if (HAL_FLASH_OB_Lock() != HAL_OK)
			printf("OB lock failed\r\n");
		if (HAL_FLASH_Lock() != HAL_OK)
			printf("FLASH lock failed\r\n");
		return -1;
	}
	if (HAL_FLASH_OB_Launch() != HAL_OK)
	{
		printf("OB launch failed\r\n");
		if (HAL_FLASH_OB_Lock() != HAL_OK)
			printf("OB lock failed\r\n");
		if (HAL_FLASH_Lock() != HAL_OK)
			printf("FLASH lock failed\r\n");
		return -1;
	}
	if (HAL_FLASH_OB_Lock() != HAL_OK)
		printf("OB lock failed\r\n");
	if (HAL_FLASH_Lock() != HAL_OK)
		printf("FLASH lock failed\r\n");
	printf("WRP programmed (will take effect after reset)\r\n");
	NVIC_SystemReset();
}

int16_t checkSectorWriteProtection(uint32_t sectorMask)
{
	FLASH_OBProgramInitTypeDef obInit;
	HAL_FLASHEx_OBGetConfig(&obInit);

	if ((obInit.WRPSector & sectorMask) == 0)
	{
		// printf("Sector %lu is write protected\r\n", sectorMask);
		return 0;
	}

	// printf("Sector %lu is NOT write protected\r\n", sectorMask);
	return 1;
}

int16_t checkAllSectorsUnprotected(uint32_t sectorMask)
{
	FLASH_OBProgramInitTypeDef obInit;
	HAL_FLASHEx_OBGetConfig(&obInit);

	return ((obInit.WRPSector & sectorMask) == sectorMask) ? 1 : 0;
}
