/*
 * update.c
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#include <stdio.h>
#include <string.h>
#include <stddef.h>
#include "update.h"
#include "input.h"
#include "flash.h"
#include "option_bytes.h"
#include "image.h"
#include "crypto.h"

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
		printf("Expected START_UPLOAD, got 0x%02X\r\n", header.service_type);
		sendNackPacket(uart, header.sequence_count, 2);
		return 2;
	}
	
	// Receive data length (4 bytes in payload)
	if (header.data_length != 4)
	{
		printf("START packet should contain 4 bytes\r\n");
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
			printf("Expected DATA_CHUNK, got 0x%02X\r\n", header.service_type);
			sendNackPacket(uart, header.sequence_count, 7);
			return 7;
		}
		
		// Verify sequence
		if (header.sequence_count != expectedSequence)
		{
			printf("Sequence mismatch: expected %u, got %u\r\n",
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
		if (sendAckPacket(uart, header.sequence_count) != 0)
		{
			printf("Error sending ACK for END\r\n");
		}
	}
	
	// Check CRC in RAM
	if (imageValidateInRAM(RAM) != 0) {
		printf("CRC verification failed\r\n");
		return 11;
	}

	// Check Digital Signature in RAM
	const image_header_t* imageHeader = imageGetHeader(RAM);
	uint8_t signature[4096];
	memcpy(signature, imageHeader->signature, 4096);
	byte* ramImageAddress = (byte *)(BOOT_RAM_ADDRESS + 4);
	// set digital signature to 0 to verify
	uint32_t dsHeaderOffset = 12U; // 4b CRC, 2b MAGIC, 2b VERSION, 4b SIZE
	memset(ramDestination + dsHeaderOffset, 0, 4096);
	if (verifySignature(ramImageAddress, dataLength - 4, signature) != 1)
	{
		printf("Digital signature validation failed\r\n");
	    return 12;
	}
	// set digital signature to the correct value for saving
	memcpy(ramDestination + dsHeaderOffset, signature, 4096);

	// Write to flash
	printf("Writing to flash...\r\n");
	if (HAL_FLASH_Unlock() != HAL_OK)
	{
		return 13;
	}
	ImageSlot secondary = getSecondarySlot();
	if (writeFlashSector(getSlotFlashSector(secondary), getSlotFlashAddress(secondary),
	                     (uint32_t *)ramDestination, dataLength/4U) != 0)
	{
		printf("Flash write failed\r\n");
		HAL_FLASH_Lock();
		return 14;
	}
	if (HAL_FLASH_Lock() != HAL_OK)
	{
		return 13;
	}
	printf("Flash write complete!\r\n");
	
	return 0;
}

int16_t swapBootWithUpdate(void)
{
#ifdef HARDWARE_SWAP
	printf("Swapping updated image into primary partition\r\n");
#else
	printf("Updating primary partition flag\r\n");
#endif

	ImageSlot newImageSlot = getSecondarySlot();
	ImageSlot oldImageSlot = getPrimarySlot();
	const image_header_t* oldImageHeader = imageGetHeader(oldImageSlot);
	if (oldImageHeader == NULL)
	{
		return 1;
	}
	const image_header_t* newImageHeader = imageGetHeader(newImageSlot);
	if (newImageHeader == NULL)
	{
		return 1;
	}
	
	uint32_t oldVersion = (uint32_t)oldImageHeader->imageVersion;
	uint32_t newVersion = (uint32_t)newImageHeader->imageVersion;
	uint32_t counter = getCounterValue();

	uint32_t newCounter;
	if (counter >= newVersion && counter >= oldVersion)
	{
		newCounter = counter;
	}
	else if (newVersion > counter && newVersion > oldVersion)
	{
		printf("Updating rollback counter from %lu to %lu\r\n", counter, newVersion);
		newCounter = newVersion;
	}
	else
	{
		printf("Cannot determine new rollback counter value\r\n");
		return 1;
	}

#ifdef HARDWARE_SWAP
	uint32_t newFlag = getPrimaryFlag();
	const uint32_t oldImageSizeWords = (oldImageHeader->imageSize + IMAGE_OFFSET) / 4U;
	const uint32_t newImageSizeWords = (newImageHeader->imageSize + IMAGE_OFFSET) / 4U;
	if (HAL_FLASH_Unlock() != HAL_OK)
	{
		return 2;
	}
	if (writeFlashSector(SWAP_FLASH_SECTOR, SWAP_FLASH_ADDRESS, (uint32_t *)oldImageHeader, oldImageSizeWords) != 0)
	{
		printf("Failed to write old image to swap sector\r\n");
		HAL_FLASH_Lock();
		return 3;
	}
	if (writeFlashSector(getSlotFlashSector(oldImageSlot), getSlotFlashAddress(oldImageSlot),
	                     (uint32_t *)newImageHeader, newImageSizeWords) != 0)
	{
		printf("Failed to write new image to old image slot\r\n");
		HAL_FLASH_Lock();
		return 3;
	}
	if (writeFlashSector(getSlotFlashSector(newImageSlot), getSlotFlashAddress(newImageSlot),
	                     (uint32_t *)SWAP_FLASH_ADDRESS, oldImageSizeWords) != 0)
	{
		printf("Failed to write old image from swap sector to new image slot\r\n");
		HAL_FLASH_Lock();
		return 3;
	}
	if (HAL_FLASH_Lock() != HAL_OK)
	{
		return 2;
	}
#else
	/* Flip the primary-partition flag: the slot that was secondary becomes
	 * primary and vice versa.  No data is physically moved. */
	uint32_t currentFlag = getPrimaryFlag();
	uint32_t newFlag = (currentFlag == PROTECTED_BSW_STATE_PRIMARY_SLOT_B)
	                   ? PROTECTED_BSW_STATE_PRIMARY_SLOT_A
	                   : PROTECTED_BSW_STATE_PRIMARY_SLOT_B;
#endif

	if (setProtectedBswState(newCounter, newFlag) != 0)
	{
		printf("Failed to write BSW state\r\n");
		return 1;
	}

#ifdef HARDWARE_SWAP
	printf("Images swapped in flash");
#else
	printf("Primary slot updated: primary is now %s\r\n",
	       (newFlag == PROTECTED_BSW_STATE_PRIMARY_SLOT_B) ? "SLOT_B" : "SLOT_A");
#endif

	return 0;
}

int16_t setupSystemForImageSwap(void)
{
	if (setBootloaderStatus(BOOTLOADER_STATUS_SWAP) != 0)
	{
		printf("Setting bootloader status failed\r\n");
		return 1;
	}

	/* Unlock BSW state sector (to write new state) and the current
	 * primary slot (it becomes secondary after the flag flip). */
	uint32_t sectorMask = PROTECTED_BSW_STATE_FLASH_OB_SECTOR | getSlotFlashOBSector(getPrimarySlot());
	if (disableSectorWriteProtection(sectorMask) != 0)
	{
		printf("Unlocking necessary FLASH sectors failed\r\n");
		return 1;
	}

	return 0;
}

int16_t checkSystemForImageSwap(void)
{
	/* BSW state sector and the current primary slot must both be unlocked
	 * before the flag flip and counter update can be performed. */
	uint32_t sectorMask = PROTECTED_BSW_STATE_FLASH_OB_SECTOR | getSlotFlashOBSector(getPrimarySlot());
	if (checkAllSectorsUnprotected(sectorMask) != 1)
	{
		printf("Cannot swap with BSW state sector or primary slot protected\r\n");
		return 1;
	}
	return 0;
}

int16_t setupSystemForNominal(void)
{
	if (setBootloaderStatus(BOOTLOADER_STATUS_NOMINAL) != 0)
	{
		printf("Setting bootloader status failed\r\n");
		return 1;
	}

	/* Protect the BSW state sector and the (new) primary slot. */
	uint32_t sectorMask = PROTECTED_BSW_STATE_FLASH_OB_SECTOR | getSlotFlashOBSector(getPrimarySlot());
	if (enableSectorWriteProtection(sectorMask) != 0)
	{
		printf("Locking necessary FLASH sectors failed\r\n");
		return 1;
	}

	return 0;
}

int16_t checkSystemForNominal(void)
{
	/* Protected BSW state sector and primary slot must be write-protected. */
	uint32_t sectorMask = PROTECTED_BSW_STATE_FLASH_OB_SECTOR | getSlotFlashOBSector(getPrimarySlot());
	if (checkSectorWriteProtection(sectorMask) != 0)
	{
		printf("Cannot boot with primary slot or protected BSW state sector unprotected\r\n");
		return 1;
	}
	return 0;
}

int16_t setupSystemForUpdate(void)
{
	return setupSystemForNominal();
}

int16_t checkSystemForUpdate(void)
{
	/* Protected BSW state sector and primary slot must be protected. */
	uint32_t sectorMask = PROTECTED_BSW_STATE_FLASH_OB_SECTOR | getSlotFlashOBSector(getPrimarySlot());
	if (checkSectorWriteProtection(sectorMask) != 0)
	{
		printf("Cannot update with primary slot or protected BSW state sector unprotected\r\n");
		return 1;
	}

	/* Secondary slot must be unprotected (upload target). */
	if (checkSectorWriteProtection(getSlotFlashOBSector(getSecondarySlot())) != 1)
	{
		printf("Cannot update with secondary slot protected\r\n");
		return 1;
	}
	return 0;
}

int16_t checkUpdateValidity(void)
{
	ImageSlot secondary = getSecondarySlot();
	if (imageValidate(secondary) != 0) {
		printf("Update image CRC verification failed\r\n");
		return 1;
	}
	if (imageLoad(secondary) != 0)
	{
		printf("Update image digital signature verification failed\r\n");
		return 2;
	}
	printf("Update image is valid\r\n");
	return 0;
}

int16_t checkUpdateVersion(void)
{
	uint32_t lowestAllowedVersion = getLowestAllowedVersion();
	ImageSlot secondary = getSecondarySlot();
	const image_header_t* secondaryHeader = imageGetHeader(secondary);
	if (secondaryHeader == NULL)
		return 1;
	uint32_t secondaryVersion = (uint32_t)secondaryHeader->imageVersion;
	if (lowestAllowedVersion > secondaryVersion)
	{
		printf("Secondary image version %lu is below floor %lu\r\n", secondaryVersion, lowestAllowedVersion);
		return 1;
	}
	printf("Secondary image version %lu is valid (floor: %lu)\r\n", secondaryVersion, lowestAllowedVersion);
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
	return PROTECTED_BSW_STATE->rollback_counter;
}

int16_t checkRollbackCondition(void)
{
    ImageSlot primary   = getPrimarySlot();
    ImageSlot secondary = getSecondarySlot();
    const image_header_t* primaryImage   = imageGetHeader(primary);
    const image_header_t* secondaryImage = imageGetHeader(secondary);
    uint32_t primaryVersion   = (uint32_t)primaryImage->imageVersion;
    uint32_t secondaryVersion = (uint32_t)secondaryImage->imageVersion;
    uint32_t lowestAllowed    = getLowestAllowedVersion();

    if (primaryVersion > secondaryVersion && secondaryVersion >= lowestAllowed)
    {
        printf("Rollback condition met: primary v%lu > secondary v%lu, secondary v%lu >= floor v%lu\r\n",
               primaryVersion, secondaryVersion, secondaryVersion, lowestAllowed);
        return 0;
    }
    printf("Rollback not possible: primary v%lu, secondary v%lu, floor v%lu\r\n",
           primaryVersion, secondaryVersion, lowestAllowed);
    return 1;
}

int16_t setProtectedBswState(uint32_t rollback_counter, uint32_t primary_slot)
{
	if (HAL_FLASH_Unlock() != HAL_OK)
		return 1;
	if (eraseFlashSector(PROTECTED_BSW_STATE_FLASH_SECTOR) != 0)
	{
		HAL_FLASH_Lock();
		return 1;
	}
	if (writeFlashWord(PROTECTED_BSW_STATE_FLASH_ADDRESS + offsetof(protected_bsw_state_t, rollback_counter), rollback_counter) != 0)
	{
		HAL_FLASH_Lock();
		return 1;
	}
	if (writeFlashWord(PROTECTED_BSW_STATE_FLASH_ADDRESS + offsetof(protected_bsw_state_t, primary_slot), primary_slot) != 0)
	{
		HAL_FLASH_Lock();
		return 1;
	}
	if (HAL_FLASH_Lock() != HAL_OK)
		return 1;
	return 0;
}
