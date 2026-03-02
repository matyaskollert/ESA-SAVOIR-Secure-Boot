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

#define RX_BUFFER_SIZE 256U
uint8_t myRXBuffer[RX_BUFFER_SIZE];

#define FLASH_SECTOR_SIZE 128U*1024U/4U


int16_t receiveUpdateData(UART_HandleTypeDef* uart)
{

	int16_t ret = receiveData(uart, myRXBuffer, 4);
	if (ret != 0)
	{
		printf("Error receiving update data\r\n");
		return ret;
	}

	uint32_t dataLength = ((uint32_t *)myRXBuffer)[0];
	// printf("Upload Data Length: %lu\r\n", dataLength);

	uint32_t amountOfChunks = dataLength / RX_BUFFER_SIZE;
	uint32_t reminder = dataLength % RX_BUFFER_SIZE;

	unlockFlash();
	eraseFlashSector(UPDATE_FLASH_SECTOR);

	// Send ACK after receiving data length
	ret = sendAck(uart);
	if (ret != 0)
	{
		printf("Error sending ACK for data length\r\n");
		return ret;
	}

	for (uint32_t i = 0; i < amountOfChunks; i++)
	{
		ret = receiveData(uart, myRXBuffer, RX_BUFFER_SIZE);
		if (ret != 0)
		{
			printf("Error receiving update data\r\n");
			lockFlash();
			return ret;
		}
		writeFlashBlock(UPDATE_FLASH_ADDRESS + i * RX_BUFFER_SIZE, (uint32_t *)myRXBuffer, RX_BUFFER_SIZE/4);
		
		// Send ACK after successfully receiving and writing chunk
		ret = sendAck(uart);
		if (ret != 0)
		{
			printf("Error sending ACK for chunk %lu\r\n", i);
			lockFlash();
			return ret;
		}
	}

	if (reminder != 0)
	{
		ret = receiveData(uart, myRXBuffer, reminder);
		if (ret != 0)
		{
			printf("Error receiving update data\r\n");
			lockFlash();
			return ret;
		}
		writeFlashBlock(UPDATE_FLASH_ADDRESS + amountOfChunks * RX_BUFFER_SIZE, (uint32_t *)myRXBuffer, RX_BUFFER_SIZE/4);
		
		// Send ACK after successfully receiving and writing final chunk
		ret = sendAck(uart);
		if (ret != 0)
		{
			printf("Error sending ACK for final chunk\r\n");
			lockFlash();
			return ret;
		}
	}

	lockFlash();
	return 0;
}

int16_t swapBootWithUpdate()
{
	writeFlashSector(SWAP_FLASH_SECTOR, SWAP_FLASH_ADDRESS, (uint32_t *)BOOT_FLASH_ADDRESS, FLASH_SECTOR_SIZE);
	writeFlashSector(BOOT_FLASH_SECTOR, BOOT_FLASH_ADDRESS, (uint32_t *)UPDATE_FLASH_ADDRESS, FLASH_SECTOR_SIZE);
	writeFlashSector(UPDATE_FLASH_SECTOR, UPDATE_FLASH_ADDRESS, (uint32_t *)SWAP_FLASH_ADDRESS, FLASH_SECTOR_SIZE);
	return 0;
}
