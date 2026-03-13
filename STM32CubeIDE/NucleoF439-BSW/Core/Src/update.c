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

#define ROLLBACK_WINDOW 1U


// ECSS packet protocol implementation
int16_t receiveUpdateData(UART_HandleTypeDef* uart)
{
	ECSSPacketHeader header;
	uint32_t dataLength = 0;
	uint32_t bytesReceived = 0;
	void* ramDestination = (void *)BOOT_RAM_ADDRESS;
	uint16_t expectedSequence = 0;
	
	printf("Waiting for START_UPLOAD packet...\r\n");
	
	// 1. Receive START_UPLOAD packet
	if (receivePacketHeader(uart, &header) != 0)
	{
		printf("Error receiving START packet header\r\n");
		sendNackPacket(uart, 0, 1);
		return 1;
	}
	
	if (header.service_type != PKT_START_UPLOAD)
	{
		printf("Error: Expected START_UPLOAD, got 0x%02X\r\n", header.service_type);
		sendNackPacket(uart, header.sequence_count, 2);
		return 2;
	}
	
	// Receive data length (4 bytes in payload)
	if (header.data_length != 4)
	{
		printf("Error: START packet should contain 4 bytes\r\n");
		sendNackPacket(uart, header.sequence_count, 3);
		return 3;
	}
	
	if (receivePacketData(uart, myRXBuffer, header.data_length) != 0)
	{
		printf("Error receiving START packet data\r\n");
		sendNackPacket(uart, header.sequence_count, 4);
		return 4;
	}
	
	dataLength = ((uint32_t *)myRXBuffer)[0];
	printf("Upload Data Length: %lu bytes\r\n", dataLength);
	
	// Send ACK for START packet
	if (sendAckPacket(uart, header.sequence_count) != 0)
	{
		printf("Error sending ACK for START\r\n");
		return 5;
	}
	
	expectedSequence = header.sequence_count + 1;
	
	// 2. Receive DATA_CHUNK packets
	printf("Receiving data chunks...\r\n");
	
	while (bytesReceived < dataLength)
	{
		// Receive chunk header
		if (receivePacketHeader(uart, &header) != 0)
		{
			printf("Error receiving DATA packet header\r\n");
			sendNackPacket(uart, expectedSequence, 6);
			return 6;
		}
		
		// Check if it's END_UPLOAD (upload complete)
		if (header.service_type == PKT_END_UPLOAD)
		{
			printf("Received END_UPLOAD packet\r\n");
			break;
		}
		
		if (header.service_type != PKT_DATA_CHUNK)
		{
			printf("Error: Expected DATA_CHUNK, got 0x%02X\r\n", header.service_type);
			sendNackPacket(uart, header.sequence_count, 7);
			return 7;
		}
		
		// Verify sequence
		if (header.sequence_count != expectedSequence)
		{
			printf("Warning: Sequence mismatch. Expected %u, got %u\r\n",
			       expectedSequence, header.sequence_count);
		}
		
		// Receive chunk data
		if (receivePacketData(uart, myRXBuffer, header.data_length) != 0)
		{
			printf("Error receiving chunk data\r\n");
			sendNackPacket(uart, header.sequence_count, 8);
			return 8;
		}
		
		// First chunk: check image header version
		if (bytesReceived == 0)
		{
			uint32_t lowestAllowedVersion = getLowestAllowedVersion();
			// Read 2-byte uint16_t values from buffer (little-endian on ARM)
			uint16_t updateMagic = *(uint16_t*)(&myRXBuffer[4]);
			uint16_t updateVersion = *(uint16_t*)(&myRXBuffer[6]);
			if (updateMagic != IMAGE_MAGIC || updateVersion < lowestAllowedVersion)
			{
				printf("Invalid image or version too low (magic=0x%04X, version=%u)\r\n",
				       updateMagic, updateVersion);
				sendNackPacket(uart, header.sequence_count, 9);
				return 9;
			}
			printf("Image validated: magic=0x%04X, version=%u\r\n", updateMagic, updateVersion);
		}
		
		// Copy data to RAM
		memcpy(ramDestination + bytesReceived, myRXBuffer, header.data_length);
		bytesReceived += header.data_length;
		
		// Send ACK for chunk
		if (sendAckPacket(uart, header.sequence_count) != 0)
		{
			printf("Error sending ACK for chunk\r\n");
			return 10;
		}
		
		expectedSequence++;
		
		// Progress indicator
		if ((bytesReceived % (RX_BUFFER_SIZE * 10)) == 0)
		{
			printf("Received: %lu/%lu bytes\r\n", bytesReceived, dataLength);
		}
	}
	
	printf("All data received: %lu bytes\r\n", bytesReceived);
	
	// 3. Receive END_UPLOAD packet (if not already received)
	if (header.service_type != PKT_END_UPLOAD)
	{
		if (receivePacketHeader(uart, &header) != 0)
		{
			printf("Error receiving END packet\r\n");
			// Continue anyway, data is received
		}
		else if (header.service_type == PKT_END_UPLOAD)
		{
			printf("Received END_UPLOAD packet\r\n");
			sendAckPacket(uart, header.sequence_count);
		}
	}
	else
	{
		// Send ACK for END packet
		sendAckPacket(uart, header.sequence_count);
	}
	
	// TODO: Check CRC and Digital Signature before storing in flash

	// Write to flash
	printf("Writing to flash...\r\n");
	writeFlashSector(UPDATE_FLASH_SECTOR, UPDATE_FLASH_ADDRESS, 
	                 (uint32_t *)ramDestination, dataLength/4U);
	printf("Flash write complete!\r\n");
	
	return 0;
}

int16_t swapBootWithUpdate(void)
{
	// TODO: Error handling?
	writeFlashSector(SWAP_FLASH_SECTOR, SWAP_FLASH_ADDRESS, (uint32_t *)BOOT_FLASH_ADDRESS, FLASH_SECTOR_SIZE);
	writeFlashSector(BOOT_FLASH_SECTOR, BOOT_FLASH_ADDRESS, (uint32_t *)UPDATE_FLASH_ADDRESS, FLASH_SECTOR_SIZE);
	writeFlashSector(UPDATE_FLASH_SECTOR, UPDATE_FLASH_ADDRESS, (uint32_t *)SWAP_FLASH_ADDRESS, FLASH_SECTOR_SIZE);
	return 0;
}

uint32_t getBootloaderStatus(void) {
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

int16_t setupSystemForImageSwap(void)
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

int16_t checkSystemForImageSwap(void)
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

int16_t setupSystemForNominal(void)
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

int16_t checkSystemForNominal(void)
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

int16_t setupSystemForUpdate(void)
{
	// TODO: Do we need to UNLOCK update and swap since they should never be locked??
	return setupSystemForNominal();
}

int16_t checkSystemForUpdate(void)
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

int16_t checkUpdateVersion(void)
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

uint32_t getLowestAllowedVersion(void)
{
	uint32_t counterValue = getCounterValue();
	if (ROLLBACK_WINDOW >= counterValue) {
		return 0;
	}
	uint32_t lowestAllowedVersion = counterValue - ROLLBACK_WINDOW;
	return lowestAllowedVersion;
}

uint32_t getCounterValue(void) {
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

int32_t updateRollbackCounter(void)
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
