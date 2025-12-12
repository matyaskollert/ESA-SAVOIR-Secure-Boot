#ifndef INC_IMAGE_H_
#define INC_IMAGE_H_

#include "usb_device.h"

#define IMAGE_MAGIC 0xABCD

#define FLASH_AREA_IMAGE_1   0x08010000
#define FLASH_AREA_IMAGE_2   0x08038800
#define RAM_AREA_IMAGE     0x20004000

#define IMAGE_OFFSET        0x400             //because vector table offset should be a multiple of 0x200


typedef struct __attribute__((packed)){
    uint16_t image_magic;
    uint16_t image_version;
    uint32_t image_size;
    uint32_t crc;
    uint32_t num_sections;
} image_hdr_t;

// Define the section copy table structure
  typedef struct {
      uint32_t src_lma;   // Load Memory Address (source in FLASH)
      uint32_t dst_vma;   // Virtual Memory Address (destination in RAM)
      uint32_t size;      // Size in bytes
} section_copy_entry_t;


typedef enum {
	IMAGE_SLOT_1 = 1,
	IMAGE_SLOT_2 = 2
} image_slot_t;


const section_copy_entry_t *imageGetCopyTable(image_slot_t slot);

const image_hdr_t *imageGetHeader(image_slot_t slot);

int imageValidate(image_slot_t slot);

int imageValidateInRAM(image_slot_t slot);

void imageLoad(image_slot_t slot);

void imageStart(image_slot_t slot);


#endif /* INC_IMAGE_H_ */
