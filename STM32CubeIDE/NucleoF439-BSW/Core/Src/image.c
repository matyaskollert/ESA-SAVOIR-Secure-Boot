/*
 * image.c
 *
 * Application image operations: header parsing, CRC-32 validation,
 * digital-signature verification, RAM loading, and final jump.
 *
 * All flash access is read-only (cast to pointer); writes go through flash.c.
 * The hardware CRC peripheral (crc32_hw) is used for all CRC checks because
 * it is approximately 10× faster than the software implementation on the
 * STM32F439 at 168 MHz.
 *
 *  Created on: Dec 15, 2025
 *      Author: Matyas
 */

#include <stdio.h>
#include <string.h>
#include "stm32f4xx_hal.h"
#include "image.h"
#include "crc.h"
#include "crypto.h"

const image_header_t* imageGetHeader(ImageSlot slot)
{
	const image_header_t* header;
	switch (slot)
	{
	case SLOT_A:
		header = (const image_header_t*)SLOT_A_FLASH_ADDRESS;
		break;
	case SLOT_B:
		header = (const image_header_t*)SLOT_B_FLASH_ADDRESS;
		break;
	case RAM:
		header = (const image_header_t*)BOOT_RAM_ADDRESS;
		break;
	default:
		return NULL;
	}

	if (header && header->imageMagic == IMAGE_MAGIC)
		return header;
	else
	{
		printf("No valid header found in slot %d\r\n", slot);
		return NULL;
	}
}

int16_t imageValidate(ImageSlot slot)
{
	const image_header_t* header = imageGetHeader(slot);
	if (header == NULL)
		return 2;

	void* image_address = (void*)(header) + 4;
	uint32_t dataSize   = header->imageSize + IMAGE_OFFSET - 4;

	//uint32_t imageCRC = crc32(image_address, dataSize);
	uint32_t imageCRC_HW = crc32_hw(image_address, dataSize);

	//printf("CRC calculated in software: 0x%08lx\r\n", imageCRC);
	printf("CRC calculated in hardware: 0x%08lx\r\n", imageCRC_HW);

	if (imageCRC_HW == header->crc)
	{
		printf("CRC validation in FLASH successful!\r\n");
		return 0;
	}
	else
	{
		printf("CRC mismatch in FLASH: 0x%08lx vs 0x%08lx\r\n", imageCRC_HW, header->crc);
		return 1;
	}
}

int16_t imageValidateInRAM(ImageSlot slot)
{
	const image_header_t* header = imageGetHeader(slot);
	if (header == NULL)
		return 2;

	void* image_address = (void*)BOOT_RAM_ADDRESS + 4;
	// header size + image size - CRC
	uint32_t dataSize = header->imageSize + IMAGE_OFFSET - 4;

	//uint32_t imageCRC = crc32(image_address, dataSize);
	uint32_t imageCRC_HW = crc32_hw(image_address, dataSize);

	if (imageCRC_HW == header->crc)
	{
		printf("CRC validation in RAM successful!\r\n");
		return 0;
	}
	else
	{
		printf("CRC mismatch in RAM: 0x%08lx vs 0x%08lx\r\n", imageCRC_HW, header->crc);
		return 1;
	}
}

int16_t imageVerify(ImageSlot slot)
{
	const image_header_t* header = imageGetHeader(slot);
	if (header == NULL)
		return 2;

	byte* ramImageAddress = (byte*)(BOOT_RAM_ADDRESS + 4);
	// header size + image size - CRC
	uint32_t dataSize = IMAGE_OFFSET + header->imageSize - 4;
	// printf("Verify image: addr=0x%08lx, size=%lu\r\n", (uint32_t)ramImageAddress, dataSize);

	uint32_t start = HAL_GetTick();
	int16_t ret    = verifySignature(ramImageAddress, dataSize, header->signature);
	uint32_t end   = HAL_GetTick();

	printf("Digital Signature: %lu milliseconds\r\n", end - start);

	return ret;
}

int16_t imageLoad(ImageSlot slot)
{
	const image_header_t* header = imageGetHeader(slot);
	if (header == NULL)
		return 2;

	printf("Starting copy from FLASH to RAM\r\n");

	void* ramDestination = (void*)BOOT_RAM_ADDRESS;
	void* flashSource    = (void*)header;
	// copy CRC + header + image
	memcpy(ramDestination, flashSource, IMAGE_OFFSET + header->imageSize);

	// set digital signature to 0 to verify
	uint32_t dsHeaderOffset = 12U;  // 4b CRC, 2b MAGIC, 2b VERSION, 4b SIZE
	memset(ramDestination + dsHeaderOffset, 0, IMAGE_OFFSET - dsHeaderOffset);
	if (imageVerify(slot) == 1)
		printf("Digital signature valid\r\n");
	else
	{
		printf("Digital signature validation failed\r\n");
		return 1;
	}
	// set digital signature to the correct value for CRC
	memcpy(ramDestination + dsHeaderOffset, flashSource + dsHeaderOffset,
	       IMAGE_OFFSET - dsHeaderOffset);

	printf("Image copied successfully\r\n");
	return 0;
}

__attribute__((noreturn)) void imageStart(void)
{
	uint32_t appVector = BOOT_RAM_ADDRESS + IMAGE_OFFSET;

	printf("App Vector: 0x%08lX\r\n", appVector);

	__disable_irq();

	SysTick->CTRL = 0;

	/* Disable all interrupts */
	for (int i = 0; i < 8; i++)
	{
		NVIC->ICER[i] = 0xFFFFFFFF;
		NVIC->ICPR[i] = 0xFFFFFFFF;
	}

	HAL_DeInit();

	uint32_t mspValue     = *(volatile uint32_t*)(appVector);
	uint32_t resetHandler = *(volatile uint32_t*)(appVector + 4);

	SCB->VTOR = appVector;

	__DSB();
	__ISB();

	__set_MSP(mspValue);

	__DSB();
	__ISB();

	((void (*)(void))resetHandler)();

	while (1)
		;  // Should never reach here
}

//void imageStart()
//{
//	uint32_t appVector = BOOT_RAM_ADDRESS + IMAGE_OFFSET;
//
//	printf("App Vector: 0x%08lX\r\n", appVector);
//
//	// Disable interrupts
//	__disable_irq();
//
//	// (optional) Disable SysTick
//	SysTick->CTRL = 0;
//
//	// Set vector table for the ASW
//	SCB->VTOR = appVector;
//
//	// Fetch MSP and ResetHandler
//	uint32_t mspValue = *(volatile uint32_t *)(appVector);
//	uint32_t resetHandler = *(volatile uint32_t *)(appVector + 4);
//
//	HAL_DeInit();
//
//	__set_MSP(mspValue);
//
//	// Jump to ASW
//	((void (*)(void))resetHandler)();
//}

void printImageHeaders(void)
{
	ImageSlot primary   = getPrimarySlot();
	ImageSlot secondary = getSecondarySlot();

	const image_header_t* slotAImage = (const image_header_t*)(SLOT_A_FLASH_ADDRESS);
	const image_header_t* slotBImage = (const image_header_t*)(SLOT_B_FLASH_ADDRESS);

	printf("SLOT_A version: %u [%s]\r\n", slotAImage->imageVersion,
	       (primary == SLOT_A) ? "PRIMARY" : "SECONDARY");
	printf("SLOT_B version: %u [%s]\r\n", slotBImage->imageVersion,
	       (primary == SLOT_B) ? "PRIMARY" : "SECONDARY");
	(void)secondary;
}
