#include <stdio.h>
#include <string.h>
#include "stm32f4xx_hal.h"
#include "image_simple.h"
#include "crc.h"

image_hdr_simple_t simple_header;

const image_hdr_simple_t* imageSimpleGetHeader()
{
	 const image_hdr_simple_t *header = (const image_hdr_simple_t *)(FLASH_AREA_IMAGE_1);

	 if (header && header->image_magic == IMAGE_MAGIC)
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
	
	uint32_t* image = FLASH_AREA_IMAGE_1 + IMAGE_OFFSET;

	// Compute CRC for this section
	uint32_t image_crc = crc32(image, hdr->image_size);
	printf("Image: addr=0x%08lx, size=%lu, crc=0x%08lx\r\n", image, hdr->image_size, image_crc);
	

	memcpy(&simple_header, hdr, sizeof(image_hdr_simple_t));

	simple_header.crc = 0;

	uint32_t hdr_size = sizeof(image_hdr_simple_t);
	uint32_t header_crc = crc32(&simple_header, hdr_size);

	printf("Header: addr=%p, size=%lu, crc=0x%08lx\r\n",
	       &simple_header,
	       hdr_size,
	       header_crc);

	image_crc ^= header_crc;

	printf("Combined CRC: 0x%08lx\r\n", image_crc);
	printf("Expected CRC: 0x%08lx\r\n", hdr->crc);
	
	if (image_crc == hdr->crc)
	{
		printf("CRC success!\r\n");
	    return 0;
	}
	else
	{
	    printf("CRC Mismatch: 0x%08lx vs 0x%08lx\r\n", image_crc, hdr->crc);
	    return -1;
	}
}

int imageSimpleValidateInRAM()
{
	const image_hdr_simple_t* hdr = imageSimpleGetHeader();
	if (hdr == NULL) {
		return -1;
	}

	uint32_t* image = RAM_AREA_IMAGE + IMAGE_OFFSET;

	// Compute CRC for this section
	uint32_t image_crc = crc32(image, hdr->image_size);
	printf("RAM Image: addr=0x%08lx, size=%lu, crc=0x%08lx\r\n", image, hdr->image_size, image_crc);
	
	memcpy(&simple_header, hdr, sizeof(image_hdr_simple_t));

	simple_header.crc = 0;

	uint32_t hdr_size = sizeof(image_hdr_simple_t);
	uint32_t header_crc = crc32(&simple_header, hdr_size);

	printf("Header: addr=%p, size=%lu, crc=0x%08lx\r\n",
		   &simple_header,
		   hdr_size,
		   header_crc);

	image_crc ^= header_crc;

	printf("Combined CRC: 0x%08lx\r\n", image_crc);
	printf("Expected CRC: 0x%08lx\r\n", hdr->crc);
	
	if (image_crc == hdr->crc)
	{
		printf("CRC validation in RAM successful!\r\n");
	    return 0;
	}
	else
	{
	    printf("CRC Mismatch in RAM: 0x%08lx vs 0x%08lx\r\n", image_crc, hdr->crc);
	    return -1;
	}
}

void imageSimpleLoad() {
	  const image_hdr_simple_t *head = imageSimpleGetHeader();
	  printf("Magic: %u", head->image_magic);

	  printf("Starting copy from FLASH to RAM\r\n");

      uint32_t actual_dst = RAM_AREA_IMAGE + IMAGE_OFFSET;
      uint32_t actual_src = FLASH_AREA_IMAGE_1 + IMAGE_OFFSET;
	  memcpy(actual_dst, actual_src, head->image_size);

	  printf("Image copied successfully\r\n");
}

void imageSimpleStart()
{
	  printf("Booting from image slot 1\r\n");

	  uint32_t app_vector = RAM_AREA_IMAGE + IMAGE_OFFSET;

	  printf("App Vector: 0x%08lX\r\n", app_vector);
	  HAL_Delay(2000);

	  //set the stack pointer and call the reset vector
	  // 1. Disable interrupts
	  __disable_irq();

	  // 2. Stop USB (avoid leftover ISRs)
	  HAL_NVIC_DisableIRQ(OTG_FS_IRQn);

	  // (optional) Disable SysTick
	  SysTick->CTRL = 0;

	  // 3. Set vector table for the application
	  SCB->VTOR = app_vector;

	  // 4. Fetch MSP and ResetHandler
	  uint32_t msp_value = *(volatile uint32_t *)(app_vector);
	  uint32_t reset_handler = *(volatile uint32_t *)(app_vector + 4);

	  HAL_DeInit();

	  // 5. Set MSP
	  __set_MSP(msp_value);

	  // 6. Jump to application
	  ((void (*)(void))reset_handler)();

}
