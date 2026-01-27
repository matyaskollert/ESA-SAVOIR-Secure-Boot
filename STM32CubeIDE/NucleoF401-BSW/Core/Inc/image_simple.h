#ifndef INC_IMAGE_H_
#define INC_IMAGE_H_

#include <stdint.h>

#define IMAGE_MAGIC 0xABCD

#define FLASH_AREA_IMAGE_1   0x08020000
#define RAM_AREA_IMAGE     0x20008000
#define IMAGE_OFFSET 0x400


typedef struct __attribute__((packed)){
    uint16_t image_magic;
    uint16_t image_version;
    uint32_t image_size;
    uint32_t crc;
    //uint32_t num_sections;
    //uint32_t signature_alg;
    //uint8_t signature[4096];
} image_hdr_simple_t;

const image_hdr_simple_t *imageGetHeader();

int imageValidate();

int imageVerify();

int imageValidateInRAM();

void imageLoad();

void imageStart();


#endif /* INC_IMAGE_H_ */
