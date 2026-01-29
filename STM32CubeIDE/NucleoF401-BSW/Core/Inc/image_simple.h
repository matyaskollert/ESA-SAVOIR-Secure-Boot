#ifndef INC_IMAGE_SIMPLE_H_
#define INC_IMAGE_SIMPLE_H_

#include <stdint.h>

typedef struct __attribute__((packed)){
    uint32_t crc;
    uint16_t imageMagic;
    uint16_t imageVersion;
    uint32_t imageSize;
    //uint32_t num_sections;
    //uint32_t signature_alg;
    uint8_t signature[4096];
} image_hdr_simple_t;

const image_hdr_simple_t *imageSimpleGetHeader();

int imageSimpleValidate();

int imageSimpleValidateInRAM();

void imageSimpleLoad();

void imageSimpleStart();


#endif /* INC_IMAGE_SIMPLE_H_ */
