#ifndef INC_IMAGE_H_
#define INC_IMAGE_H_

#include <stdint.h>

typedef struct __attribute__((packed)){
    uint32_t crc;
    uint16_t imageMagic;
    uint16_t imageVersion;
    uint32_t imageSize;
    //uint32_t num_sections;
    //uint32_t signature_alg;
    uint8_t signature[4096];
} image_header_t;

const image_header_t* imageGetHeader();

int16_t imageValidate();

int16_t imageValidateInRAM();

int16_t imageLoad();

void imageStart();


#endif /* INC_IMAGE_H_ */
