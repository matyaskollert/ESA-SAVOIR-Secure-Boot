#include <image.h>
#include <stdio.h>
#include <string.h>
#include "stm32f4xx_hal.h"
#include "crc.h"
#include "crypto.h"

#define IMAGE_MAGIC 0xABCD

#define BOOT_FLASH_ADDRESS   0x08020000
#define UPDATE_FLASH_ADDRESS 0x08040000
#define SWAP_FLASH_ADDRESS   0x08060000
#define BOOT_RAM_ADDRESS     0x20008000
#define IMAGE_OFFSET 0x1400

const image_header_t* imageGetHeader()
{
	const image_header_t *header = (const image_header_t *)(BOOT_FLASH_ADDRESS);

	if (header && header->imageMagic == IMAGE_MAGIC)
	{
		return header;
	}
	else
	{
		printf("No valid header found in slot 1 !!\r\n");
		return NULL;
	}
}

int16_t imageValidate()
{
	const image_header_t* header = imageGetHeader();
	if (header == NULL)
	{
		return -2;
	}
	
	void* image_address = (void *)(BOOT_FLASH_ADDRESS + 4);
	uint32_t dataSize = header->imageSize + IMAGE_OFFSET - 4;

	// Compute CRC for this section
	uint32_t imageCRC = crc32(image_address, dataSize);
	printf("Image: addr=0x%08lx, size=%lu, crc=0x%08lx\r\n", (uint32_t)image_address, dataSize, imageCRC);

	printf("Combined CRC: 0x%08lx\r\n", imageCRC);
	printf("Expected CRC: 0x%08lx\r\n", header->crc);
	
	if (imageCRC == header->crc)
	{
		printf("CRC success!\r\n");
	    return 0;
	}
	else
	{
	    printf("CRC Mismatch: 0x%08lx vs 0x%08lx\r\n", imageCRC, header->crc);
	    return -1;
	}
}

int16_t imageValidateInRAM()
{
	const image_header_t* header = imageGetHeader();
	if (header == NULL)
	{
		return -2;
	}

	void* image_address = (void *)(BOOT_RAM_ADDRESS + 4);
	uint32_t dataSize = header->imageSize + IMAGE_OFFSET - 4;

	// Compute CRC for this section
	uint32_t imageCRC = crc32(image_address, dataSize);
	printf("RAM Image: addr=0x%08lx, size=%lu, crc=0x%08lx\r\n", (uint32_t)image_address, dataSize, imageCRC);

	printf("Combined CRC: 0x%08lx\r\n", imageCRC);
	printf("Expected CRC: 0x%08lx\r\n", header->crc);
	
	if (imageCRC == header->crc)
	{
		printf("CRC validation in RAM successful!\r\n");
	    return 0;
	}
	else
	{
	    printf("CRC Mismatch in RAM: 0x%08lx vs 0x%08lx\r\n", imageCRC, header->crc);
	    return -1;
	}
}

int16_t imageVerify() {
	const image_header_t* header = imageGetHeader();
	if (header == NULL) {
		return -1;
	}

	byte* ramImageAddress = (byte *)(BOOT_RAM_ADDRESS + 4);
	uint32_t dataSize = IMAGE_OFFSET + header->imageSize - 4;
	printf("Verify image: addr=0x%08lx, size=%lu\r\n", (uint32_t)ramImageAddress, dataSize);
	return verifySignature(ramImageAddress, dataSize, header->signature);
}

int16_t imageLoad() {
	const image_header_t* header = imageGetHeader();
	if (header == NULL) {
		return -2;
	}

	printf("Starting copy from FLASH to RAM\r\n");

	void* ramDestination = (void *)BOOT_RAM_ADDRESS;
	void* flashSource = (void *)BOOT_FLASH_ADDRESS;
	memcpy(ramDestination, flashSource, IMAGE_OFFSET + header->imageSize);

	memset(ramDestination + 12, 0, IMAGE_OFFSET - 12);
	int16_t ret = imageVerify();
	if (ret == 1) {
		printf("Digital signature valid\r\n");
	} else {
		printf("Digital signature validation failed\r\n");
		return -1;
	}
	memcpy(ramDestination + 12, flashSource + 12, IMAGE_OFFSET - 12);

	printf("Image copied successfully\r\n");
	return 0;
}

void imageStart()
{
	printf("Booting from image slot 1\r\n");

	uint32_t appVector = BOOT_RAM_ADDRESS + IMAGE_OFFSET;

	printf("App Vector: 0x%08lX\r\n", appVector);
	HAL_Delay(2000);

	//set the stack pointer and call the reset vector
	// 1. Disable interrupts
	__disable_irq();

	// 2. Stop USB (avoid leftover ISRs)
	HAL_NVIC_DisableIRQ(OTG_FS_IRQn);

	// (optional) Disable SysTick
	SysTick->CTRL = 0;

	// 3. Set vector table for the application
	SCB->VTOR = appVector;

	// 4. Fetch MSP and ResetHandler
	uint32_t mspValue = *(volatile uint32_t *)(appVector);
	uint32_t resetRandler = *(volatile uint32_t *)(appVector + 4);

	HAL_DeInit();

	// 5. Set MSP
	__set_MSP(mspValue);

	// 6. Jump to application
	((void (*)(void))resetRandler)();
}
