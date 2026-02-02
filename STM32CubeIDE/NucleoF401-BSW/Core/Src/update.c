/*
 * update.c
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#include "update.h"
#include "input.h"
#include "flash.h"
#include <stdio.h>

//TODO: dynamic
#define RX_BUFFER_SIZE 16388U//0x10000;
uint8_t myRXBuffer[RX_BUFFER_SIZE];

#define FLASH_SECTOR_SIZE 128U*1024U/4U;


int16_t receiveUpdateData(UART_HandleTypeDef* uart)
{
	int16_t ret = receiveData(uart, myRXBuffer, RX_BUFFER_SIZE);
	if (ret != 0)
	{
		printf("Error receiving update data\r\n");
		return ret;
	}

	printf("First Word: 0x%04lx\r\n", ((uint32_t *)myRXBuffer)[0]);
	writeFlashSector(UPDATE_FLASH_SECTOR, UPDATE_FLASH_ADDRESS, (uint32_t *)myRXBuffer, RX_BUFFER_SIZE/4);
	return 0;
}

int16_t swapBootWithUpdate()
{
	writeFlashSector(SWAP_FLASH_SECTOR, SWAP_FLASH_ADDRESS, (uint32_t *)BOOT_FLASH_ADDRESS, RX_BUFFER_SIZE/4);
	writeFlashSector(BOOT_FLASH_SECTOR, BOOT_FLASH_ADDRESS, (uint32_t *)UPDATE_FLASH_ADDRESS, RX_BUFFER_SIZE/4);
	writeFlashSector(UPDATE_FLASH_SECTOR, UPDATE_FLASH_ADDRESS, (uint32_t *)SWAP_FLASH_ADDRESS, RX_BUFFER_SIZE/4);
	return 0;
}
