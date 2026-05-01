#ifndef INC_IMAGE_H_
#define INC_IMAGE_H_

#include <stdint.h>

typedef enum {BOOT, UPDATE, SWAP, RAM} ImageSlot;

#define IMAGE_OFFSET 		0x1400
#define IMAGE_MAGIC 		0xABCD
#define BOOT_RAM_ADDRESS 	0x20008000


typedef struct __attribute__((packed)){
    uint32_t crc;
    uint16_t imageMagic;
    uint16_t imageVersion;
    uint32_t imageSize;
    //uint32_t num_sections;
    //uint32_t signature_alg;
    uint8_t signature[4096];
} image_header_t;

const image_header_t* imageGetHeader(ImageSlot slot);

int16_t imageValidate(ImageSlot slot);

int16_t imageValidateInRAM(ImageSlot slot);

int16_t imageLoad(ImageSlot slot);

void imageStart(void);


#endif /* INC_IMAGE_H_ */
