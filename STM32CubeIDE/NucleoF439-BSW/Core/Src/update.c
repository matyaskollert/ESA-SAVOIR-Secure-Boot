/*
 * update.c
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#include <stdio.h>
#include <string.h>
#include "update.h"
#include "input.h"
#include "flash.h"
#include "option_bytes.h"
#include "image.h"

#define RX_BUFFER_SIZE 256U
uint8_t myRXBuffer[RX_BUFFER_SIZE];

#define FLASH_SECTOR_SIZE 128U*1024U/4U

#define ROLLBACK_WINDOW 1U;


// TODO: Refactor + better protocol
int16_t receiveUpdateData(UART_HandleTypeDef* uart)
{

	if (receiveData(uart, myRXBuffer, 4) != 0)
	{
		printf("Error receiving update data\r\n");
		return 1;
	}

	uint32_t dataLength = ((uint32_t *)myRXBuffer)[0];
	// printf("Upload Data Length: %lu\r\n", dataLength);

	uint32_t amountOfChunks = dataLength / RX_BUFFER_SIZE;
	uint32_t reminder = dataLength % RX_BUFFER_SIZE;

	// Send ACK after receiving data length
	if (sendAck(uart) != 0)
	{
		printf("Error sending ACK for data length\r\n");
		return 1;
	}

	void* ramDestination = (void *)BOOT_RAM_ADDRESS;

	for (uint32_t i = 0; i < amountOfChunks; i++)
	{
		if (receiveData(uart, myRXBuffer, RX_BUFFER_SIZE) != 0)
		{
			printf("Error receiving update data\r\n");
			return 1;
		}

		if (i == 0)
		{
			// Check header version ASAP
			uint32_t lowestAllowedVersion = getLowestAllowedVersion();
			uint16_t updateMagic = (uint16_t)myRXBuffer[4];
			uint16_t updateVersion = (uint16_t)myRXBuffer[6];
			if (updateMagic != IMAGE_MAGIC || updateVersion < lowestAllowedVersion)
			{
				printf("This is not an image or the image version is too low\r\n");
				// TODO: Send some REJECT packet
			}
		}

		// copy CRC + header + image
		memcpy(ramDestination + i * RX_BUFFER_SIZE, myRXBuffer, RX_BUFFER_SIZE);
		
		// Send ACK after successfully receiving and writing chunk
		if (sendAck(uart) != 0)
		{
			printf("Error sending ACK for chunk %lu\r\n", i);
			return 1;
		}
	}

	if (reminder != 0)
	{
		if (receiveData(uart, myRXBuffer, reminder) != 0)
		{
			printf("Error receiving update data\r\n");
			return 1;
		}
		memcpy(ramDestination + amountOfChunks * RX_BUFFER_SIZE, myRXBuffer, RX_BUFFER_SIZE);
		
		// Send ACK after successfully receiving and writing final chunk
		if (sendAck(uart) != 0)
		{
			printf("Error sending ACK for final chunk\r\n");
			return 1;
		}
	}

	// TODO: Perform CRC and SIGN checks before putting into UPDATE
	writeFlashSector(UPDATE_FLASH_SECTOR, UPDATE_FLASH_ADDRESS, (uint32_t *)ramDestination, dataLength/4U);
	return 0;
}

int16_t swapBootWithUpdate()
{
	// TODO: Error handling?
	writeFlashSector(SWAP_FLASH_SECTOR, SWAP_FLASH_ADDRESS, (uint32_t *)BOOT_FLASH_ADDRESS, FLASH_SECTOR_SIZE);
	writeFlashSector(BOOT_FLASH_SECTOR, BOOT_FLASH_ADDRESS, (uint32_t *)UPDATE_FLASH_ADDRESS, FLASH_SECTOR_SIZE);
	writeFlashSector(UPDATE_FLASH_SECTOR, UPDATE_FLASH_ADDRESS, (uint32_t *)SWAP_FLASH_ADDRESS, FLASH_SECTOR_SIZE);
	return 0;
}

uint32_t getBootloaderStatus() {
	uint32_t status = *((uint32_t*)COMM_FLASH_ADDRESS);
	return status;
}

int16_t setBootloaderStatus(uint32_t newStatus)
{
	if (HAL_FLASH_Unlock() != HAL_OK)
	{
		return 1;
	}
	if (eraseFlashSector(COMM_FLASH_SECTOR) != 0)
	{
		return 1;
	}
	if (writeFlashWord(COMM_FLASH_ADDRESS, newStatus) != 0)
	{
		return 1;
	}
	if (HAL_FLASH_Lock() != HAL_OK)
	{
		return 1;
	}
	return 0;
}

int16_t setupSystemForImageSwap()
{
	if (setBootloaderStatus(123) != 0)
	{
		printf("Setting bootloader status failed\r\n");
		return 1;
	}

	uint32_t sectorMask = COUNTER_FLASH_OB_SECTOR | BOOT_FLASH_OB_SECTOR;
	if (disableSectorWriteProtection(sectorMask) != 0)
	{
		printf("Unlocking necessary FLASH sectors failed\r\n");
		return 1;
	}

	return 0;
}

int16_t checkSystemForImageSwap()
{
	if (getBootloaderStatus() != 123)
	{
		printf("Bootloader status is not set to SWAP\r\n");
		return 1;
	}
	uint32_t sectorMask = COUNTER_FLASH_OB_SECTOR | BOOT_FLASH_OB_SECTOR;
	if (checkSectorWriteProtection(sectorMask) != 1)
	{
		printf("Cannot swap with BOOT and COUNTER protected\r\n");
		return 1;
	}
	return 0;
}

int16_t setupSystemForNominal()
{
	if (setBootloaderStatus(321) != 0)
	{
		printf("Setting bootloader status failed\r\n");
		return 1;
	}


	uint32_t sectorMask = COUNTER_FLASH_OB_SECTOR | BOOT_FLASH_OB_SECTOR;
	if (enableSectorWriteProtection(sectorMask) != 0)
	{
		printf("Locking necessary FLASH sectors failed\r\n");
		return 1;
	}

	return 0;
}

int16_t checkSystemForNominal()
{
	// TODO: Decide if we should check the STATUS here
	uint32_t sectorMask = COUNTER_FLASH_OB_SECTOR | BOOT_FLASH_OB_SECTOR;
	if (checkSectorWriteProtection(sectorMask) != 0)
	{
		printf("Cannot boot with BOOT and COUNTER unprotected\r\n");
		return 1;
	}
	return 0;
}

int16_t setupSystemForUpdate()
{
	// TODO: Do we need to UNLOCK update and swap since they should never be locked??
	return setupSystemForNominal();
}

int16_t checkSystemForUpdate()
{
	// TODO: Decide if we should check the STATUS here
	// TODO: This could be done in one step?
	uint32_t sectorMask = COUNTER_FLASH_OB_SECTOR | BOOT_FLASH_OB_SECTOR;
	if (checkSectorWriteProtection(sectorMask) != 0)
	{
		printf("Cannot update with BOOT and COUNTER unprotected\r\n");
		return 1;
	}

	sectorMask = UPDATE_FLASH_OB_SECTOR;
	if (checkSectorWriteProtection(sectorMask) != 1)
	{
		printf("Cannot update with UPDATE protected. This should never happen\r\n");
		return 1;
	}
	return 0;
}

int16_t checkUpdateVersion()
{
	// First we need to Verify the CRC + digital signature so the version cannot be modified
	if (imageLoad(UPDATE) != 0)
	{
		printf("Update image verification failed\r\n");
		return 2;
	}
	uint32_t lowestAllowedVersion = getLowestAllowedVersion();
	const image_header_t* updateImage = (const image_header_t *)(UPDATE_FLASH_ADDRESS);
	uint32_t updateImageVersion = (uint32_t)updateImage->imageVersion;
	if (lowestAllowedVersion > updateImageVersion)
	{
		printf("UPDATE version: %lu is lower than allowed: %lu\r\n", updateImageVersion, lowestAllowedVersion);
		return 1;
	}
	return 0;
}

uint32_t getLowestAllowedVersion()
{
	uint32_t counterValue = getCounterValue();
	uint32_t lowestAllowedVersion = counterValue - ROLLBACK_WINDOW;
	return lowestAllowedVersion;
}

uint32_t getCounterValue() {
	uint32_t counterValue = *((uint32_t*)COUNTER_FLASH_ADDRESS);
	return counterValue;
}

int16_t setCounterValue(uint32_t newValue)
{
	if (HAL_FLASH_Unlock() != HAL_OK)
	{
		return 1;
	}
	if (eraseFlashSector(COUNTER_FLASH_SECTOR) != 0)
	{
		return 1;
	}
	if (writeFlashWord(COUNTER_FLASH_ADDRESS, newValue) != 0)
	{
		return 1;
	}
	if (HAL_FLASH_Lock() != HAL_OK)
	{
		return 1;
	}
	return 0;
}

int32_t updateRollbackCounter()
{
	uint32_t counterValue = getCounterValue();
	const image_header_t* bootImage = (const image_header_t *)(BOOT_FLASH_ADDRESS);
	const image_header_t* updateImage = (const image_header_t *)(UPDATE_FLASH_ADDRESS);
	uint32_t bootImageVersion = (uint32_t)bootImage->imageVersion;
	uint32_t updateImageVersion = (uint32_t)updateImage->imageVersion;
	if (counterValue >= bootImageVersion && counterValue >= updateImageVersion)
	{
		// do nothing
		return 0;
	}
	else if (bootImageVersion > counterValue && bootImageVersion > updateImageVersion)
	{
		return setCounterValue(bootImageVersion);
	} else
	{
		// TODO: can this happen?
		return -1;
	}
}
