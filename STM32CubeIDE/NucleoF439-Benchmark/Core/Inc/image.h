#ifndef INC_IMAGE_H_
#define INC_IMAGE_H_

#include <stdint.h>

typedef enum {BOOT, UPDATE, SWAP} ImageSlot;

#define IMAGE_MAGIC             0xABCD
#define BOOT_RAM_ADDRESS        0x20008000

// Total byte-size of the header region in flash (header struct + padding).
// The application code starts at flashBase + IMAGE_OFFSET.
#define IMAGE_OFFSET            0x1400U

// Byte offset of the signature[] field within image_header_t.
// = sizeof(crc) + sizeof(imageMagic) + sizeof(imageVersion) + sizeof(imageSize)
#define IMAGE_HEADER_DS_OFFSET  12U


typedef struct __attribute__((packed)){
    uint32_t crc;
    uint16_t imageMagic;
    uint16_t imageVersion;
    uint32_t imageSize;
    uint8_t signature[4096];
} image_header_t;

const image_header_t* imageGetHeader(ImageSlot slot);

int16_t imageValidate(ImageSlot slot);

int16_t imageValidateInRAM(ImageSlot slot);

int16_t imageLoad(ImageSlot slot);

void imageStart(void);


#endif /* INC_IMAGE_H_ */
