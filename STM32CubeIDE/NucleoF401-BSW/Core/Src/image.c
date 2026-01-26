#include <stdio.h>

#include "stm32f4xx_hal.h"
#include "image.h"
#include "crc.h"
#include "crypto.h"

volatile image_hdr_t header;

const image_hdr_t* imageGetHeader(image_slot_t slot)
{
	 const image_hdr_t *header = NULL;

	 switch (slot)
	 {
		 case IMAGE_SLOT_1:
			 header = (const image_hdr_t *)(FLASH_AREA_IMAGE_1);
			 break;
		 case IMAGE_SLOT_2:
			 header = (const image_hdr_t *)(FLASH_AREA_IMAGE_2);
			 break;
		 default:
			 break;
	 }

	 if (header && header->image_magic == IMAGE_MAGIC)
	 {
		 return header;
	 }
	 else
	 {
		 printf("No valid header found in slot %d !!\r\n", slot);
		 return NULL;
	 }

}

const section_copy_entry_t* imageGetCopyTable(image_slot_t slot)
{
	 const section_copy_entry_t *copy_table = NULL;
	 const uint32_t copy_table_offset = sizeof(image_hdr_t);
	 printf("Copy table at FLASH offset 0x%lX\r\n", copy_table_offset);

	 switch (slot)
	 {
		 case IMAGE_SLOT_1:
			 copy_table = (const section_copy_entry_t *)(FLASH_AREA_IMAGE_1 + copy_table_offset);
			 break;
		 case IMAGE_SLOT_2:
			 copy_table = (const section_copy_entry_t *)(FLASH_AREA_IMAGE_2 + copy_table_offset);
			 break;
		 default:
			 break;
	 }

	 return copy_table;
}

int imageValidate(image_slot_t slot)
{
	image_hdr_t* hdr = imageGetHeader(slot);
	if (hdr == NULL) {
		return -1;
	}

	// Get section copy table
	const section_copy_entry_t *section_table = imageGetCopyTable(slot);
	uint32_t num_sections = hdr->num_sections;
	
	// Compute CRC for each section and combine
	uint32_t combined_crc = 0;
	for (uint32_t i = 0; i < num_sections; i++) {
		uint32_t src_lma = section_table[i].src_lma;
		uint32_t size = section_table[i].size;
		
		if (size == 0) {
			printf("Section %lu: empty, skipping\r\n", i);
			continue;
		}
		
		// Use src_lma directly - it's the absolute address in FLASH
		void *section_addr = (void *)src_lma;
		
		// Compute CRC for this section
		uint32_t section_crc = crc32(section_addr, size);
		printf("Section %lu: addr=0x%08lx, size=%lu, crc=0x%08lx\r\n", i, src_lma, size, section_crc);
		
		// Combine CRCs using XOR
		combined_crc ^= section_crc;
	}
	

	memcpy(&header, hdr, sizeof(image_hdr_t));

	header.crc = 0;

	uint32_t hdr_size = sizeof(image_hdr_t);
	uint32_t header_crc = crc32(&header, hdr_size);

	printf("Header: addr=%p, size=%lu, crc=0x%08lx\r\n",
	       &header,
	       hdr_size,
	       header_crc);

	combined_crc ^= header_crc;

	printf("Combined CRC: 0x%08lx\r\n", combined_crc);
	printf("Expected CRC: 0x%08lx\r\n", hdr->crc);
	
	if (combined_crc == hdr->crc)
	{
		printf("CRC success!\r\n");
	    return 0;
	}
	else
	{
	    printf("CRC Mismatch: 0x%08lx vs 0x%08lx\r\n", combined_crc, hdr->crc);
	    return -1;
	}
}

int imageValidateInRAM(image_slot_t slot)
{
	const image_hdr_t* hdr = imageGetHeader(slot);
	if (hdr == NULL) {
		return -1;
	}

	// Get section copy table
	const section_copy_entry_t *section_table = imageGetCopyTable(slot);
	uint32_t num_sections = hdr->num_sections;
	
	// Compute CRC for each section in RAM and combine
	uint32_t combined_crc = 0;
	for (uint32_t i = 0; i < num_sections; i++) {
		uint32_t dst_vma = section_table[i].dst_vma;
		uint32_t size = section_table[i].size;
		
		if (size == 0) {
			printf("Section %lu: empty, skipping\r\n", i);
			continue;
		}
		
		// Compute CRC for this section in RAM
		void *section_addr = (void *)dst_vma;
		uint32_t section_crc = crc32(section_addr, size);
		printf("Section %lu in RAM: addr=0x%08lx, size=%lu, crc=0x%08lx\r\n",
		       i, dst_vma, size, section_crc);

		// Combine CRCs using XOR
		combined_crc ^= section_crc;
	}
	
	memcpy(&header, hdr, sizeof(image_hdr_t));

	header.crc = 0;

	uint32_t hdr_size = sizeof(image_hdr_t);
	uint32_t header_crc = crc32(&header, hdr_size);

	printf("Header: addr=%p, size=%lu, crc=0x%08lx\r\n",
		   &header,
		   hdr_size,
		   header_crc);

	combined_crc ^= header_crc;

	printf("Combined CRC: 0x%08lx\r\n", combined_crc);
	printf("Expected CRC: 0x%08lx\r\n", hdr->crc);
	
	if (combined_crc == hdr->crc)
	{
		printf("CRC validation in RAM successful!\r\n");
	    return 0;
	}
	else
	{
	    printf("CRC Mismatch in RAM: 0x%08lx vs 0x%08lx\r\n", combined_crc, hdr->crc);
	    return -1;
	}
}

void imageLoad(image_slot_t slot) {
	  const image_hdr_t *head = imageGetHeader(slot);
	  printf("Magic: %u", head->image_magic);

	  printf("Starting section-by-section copy from FLASH to RAM\r\n");
	  uint32_t num_sections = head->num_sections;

	  const section_copy_entry_t *section_table = imageGetCopyTable(slot);

	  // Iterate through each section and copy it
	  for (uint32_t i = 0; i < num_sections; i++) {
		  uint32_t src_lma = section_table[i].src_lma;
		  uint32_t dst_vma = section_table[i].dst_vma;
		  uint32_t size = section_table[i].size;

		  if (size == 0) {
			  printf("Section %lu: empty, skipping\r\n", i);
			  continue;
		  }

		  printf("Section %lu: copying %lu bytes from 0x%08lX to 0x%08lX\r\n",
				 i, size, src_lma, dst_vma);

		  // The src_lma is the absolute address in the app's FLASH space
		  // We need to translate it to our loaded image location
		  // If the app expects to be at 0x08010000 and we loaded it there, use as-is
		  // Otherwise, adjust: actual_src = app_flash_base + (src_lma - 0x08010000)

		  uint8_t *actual_src = (uint8_t *)src_lma;
		  uint8_t *actual_dst = (uint8_t *)dst_vma;

		  // Perform the copy
		  memcpy(actual_dst, actual_src, size);
	  }

	  printf("All sections copied successfully\r\n");
}

void imageStart(image_slot_t slot)
{
	  printf("Booting from image slot %d\r\n", slot);

	  uint32_t app_vector = RAM_AREA_IMAGE;

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
