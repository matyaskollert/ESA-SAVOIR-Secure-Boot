#include <stdio.h>
#include <string.h>
#include "stm32f4xx_hal.h"
#include "image_simple.h"
#include "crc.h"
#include "crypto.h"

#define IMAGE_MAGIC 0xABCD

#define FLASH_AREA_IMAGE_1   0x08020000
#define RAM_AREA_IMAGE     0x20008000
#define IMAGE_OFFSET 0x1400

const image_hdr_simple_t* imageSimpleGetHeader()
{
	 const image_hdr_simple_t *header = (const image_hdr_simple_t *)(FLASH_AREA_IMAGE_1);

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

int imageSimpleValidate()
{
	const image_hdr_simple_t* hdr = imageSimpleGetHeader();
	if (hdr == NULL) {
		return -1;
	}
	
	void* image_address = (void *)(FLASH_AREA_IMAGE_1 + 4);
	uint32_t dataSize = hdr->imageSize + IMAGE_OFFSET - 4;

	// Compute CRC for this section
	uint32_t imageCRC = crc32(image_address, dataSize);
	printf("Image: addr=0x%08lx, size=%lu, crc=0x%08lx\r\n", (uint32_t)image_address, dataSize, imageCRC);

	printf("Combined CRC: 0x%08lx\r\n", imageCRC);
	printf("Expected CRC: 0x%08lx\r\n", hdr->crc);
	
	if (imageCRC == hdr->crc)
	{
		printf("CRC success!\r\n");
	    return 0;
	}
	else
	{
	    printf("CRC Mismatch: 0x%08lx vs 0x%08lx\r\n", imageCRC, hdr->crc);
	    return -1;
	}
}

int imageSimpleValidateInRAM()
{
	const image_hdr_simple_t* hdr = imageSimpleGetHeader();
	if (hdr == NULL) {
		return -1;
	}

	void* image_address = (void *)(RAM_AREA_IMAGE + 4);
	uint32_t dataSize = hdr->imageSize + IMAGE_OFFSET - 4;

	// Compute CRC for this section
	uint32_t imageCRC = crc32(image_address, dataSize);
	printf("RAM Image: addr=0x%08lx, size=%lu, crc=0x%08lx\r\n", (uint32_t)image_address, dataSize, imageCRC);

	printf("Combined CRC: 0x%08lx\r\n", imageCRC);
	printf("Expected CRC: 0x%08lx\r\n", hdr->crc);
	
	if (imageCRC == hdr->crc)
	{
		printf("CRC validation in RAM successful!\r\n");
	    return 0;
	}
	else
	{
	    printf("CRC Mismatch in RAM: 0x%08lx vs 0x%08lx\r\n", imageCRC, hdr->crc);
	    return -1;
	}
}

int imageSimpleVerify() {
	const image_hdr_simple_t *head = imageSimpleGetHeader();
	byte* ramImageAddress = (byte *)(RAM_AREA_IMAGE + 4);
	uint32_t dataSize = IMAGE_OFFSET + head->imageSize - 4;
	printf("Verify image: addr=0x%08lx, size=%lu\r\n", (uint32_t)ramImageAddress, dataSize);
	hash(ramImageAddress, dataSize);
	uint32_t signatureLength = 71U;
	//TODO: dynamic signature length
	return verifySignature(head->signature, signatureLength);
}

void imageSimpleLoad() {
	  const image_hdr_simple_t *head = imageSimpleGetHeader();

	  printf("Starting copy from FLASH to RAM\r\n");

      void* ramDestination = (void *)RAM_AREA_IMAGE;
      void* flashSource = (void *)FLASH_AREA_IMAGE_1;
	  memcpy(ramDestination, flashSource, IMAGE_OFFSET + head->imageSize);

	  memset(ramDestination + 12, 0, IMAGE_OFFSET - 12);
	  int ret = imageSimpleVerify();
	  if (ret == 1) {
		  printf("Digital signature valid\r\n");
	  } else {
		  printf("Digital signature validation failed\r\n");
		  //TODO: don't boot further
	  }
	  memcpy(ramDestination + 12, flashSource + 12, IMAGE_OFFSET - 12);

	  printf("Image copied successfully\r\n");
}

void imageSimpleStart()
{
	  printf("Booting from image slot 1\r\n");

	  uint32_t appVector = RAM_AREA_IMAGE + IMAGE_OFFSET;

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
