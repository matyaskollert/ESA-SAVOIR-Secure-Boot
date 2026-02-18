#include <image.h>
#include <stdio.h>
#include <string.h>
#include "stm32f4xx_hal.h"
#include "crc.h"
#include "crypto.h"
#include "flash.h"

#define IMAGE_MAGIC 		0xABCD
#define IMAGE_OFFSET 		0x1400
#define BOOT_RAM_ADDRESS 	0x20008000

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
		return 2;
	}
	
	void* image_address = (void *)(BOOT_FLASH_ADDRESS + 4);
	uint32_t dataSize = header->imageSize + IMAGE_OFFSET - 4;

	uint32_t imageCRC = crc32(image_address, dataSize);
	
	if (imageCRC == header->crc)
	{
		printf("CRC validation in FLASH successful!\r\n");
	    return 0;
	}
	else
	{
	    printf("CRC Mismatch in FLASH: 0x%08lx vs 0x%08lx\r\n", imageCRC, header->crc);
	    return 1;
	}
}

int16_t imageValidateInRAM()
{
	const image_header_t* header = imageGetHeader();
	if (header == NULL)
	{
		return 2;
	}

	void* image_address = (void *)(BOOT_RAM_ADDRESS + 4);
	// header size + image size - CRC
	uint32_t dataSize = header->imageSize + IMAGE_OFFSET - 4;

	uint32_t imageCRC = crc32(image_address, dataSize);
	
	if (imageCRC == header->crc)
	{
		printf("CRC validation in RAM successful!\r\n");
	    return 0;
	}
	else
	{
	    printf("CRC Mismatch in RAM: 0x%08lx vs 0x%08lx\r\n", imageCRC, header->crc);
	    return 1;
	}
}

int16_t imageVerify() {
	const image_header_t* header = imageGetHeader();
	if (header == NULL) {
		return 2;
	}

	byte* ramImageAddress = (byte *)(BOOT_RAM_ADDRESS + 4);
	// header size + image size - CRC
	uint32_t dataSize = IMAGE_OFFSET + header->imageSize - 4;
	printf("Verify image: addr=0x%08lx, size=%lu\r\n", (uint32_t)ramImageAddress, dataSize);
	return verifySignature(ramImageAddress, dataSize, header->signature);
}

int16_t imageLoad() {
	const image_header_t* header = imageGetHeader();
	if (header == NULL) {
		return 2;
	}

	printf("Starting copy from FLASH to RAM\r\n");

	void* ramDestination = (void *)BOOT_RAM_ADDRESS;
	void* flashSource = (void *)BOOT_FLASH_ADDRESS;
	// copy CRC + header + image
	memcpy(ramDestination, flashSource, IMAGE_OFFSET + header->imageSize);

	// set digital signature to 0 to verify
	uint32_t dsHeaderOffset = 12U; // 4b CRC, 2b MAGIC, 2b VERSION, 4b SIZE
	memset(ramDestination + dsHeaderOffset, 0, IMAGE_OFFSET - dsHeaderOffset);
	if (imageVerify() == 1) {
		printf("Digital signature valid\r\n");
	} else {
		printf("Digital signature validation failed\r\n");
		return 1;
	}
	// set digital signature to the correct value for CRC
	memcpy(ramDestination + dsHeaderOffset, flashSource + dsHeaderOffset, IMAGE_OFFSET - dsHeaderOffset);

	printf("Image copied successfully\r\n");
	return 0;
}

void imageStart()
{
	uint32_t appVector = BOOT_RAM_ADDRESS + IMAGE_OFFSET;

	printf("App Vector: 0x%08lX\r\n", appVector);
	HAL_Delay(1000);

	// Disable interrupts
	__disable_irq();

	// (optional) Disable SysTick
	SysTick->CTRL = 0;

	// Set vector table for the ASW
	SCB->VTOR = appVector;

	// Fetch MSP and ResetHandler
	uint32_t mspValue = *(volatile uint32_t *)(appVector);
	uint32_t resetHandler = *(volatile uint32_t *)(appVector + 4);

	HAL_DeInit();

	__set_MSP(mspValue);

	// Jump to ASW
	((void (*)(void))resetHandler)();
}
