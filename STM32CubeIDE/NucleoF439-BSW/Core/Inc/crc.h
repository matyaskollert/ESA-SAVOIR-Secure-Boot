#ifndef INC_CRC_H_
#define INC_CRC_H_

#include <stdint.h>
#include <stddef.h>

uint32_t crc32(const void *data, uint32_t sizeBytes);
uint32_t crc32_hw(const void *data, uint32_t sizeBytes);

#endif /* INC_CRC_H_ */
