#ifndef INC_CRC_H_
#define INC_CRC_H_

#include <stdint.h>
#include <stddef.h>

uint32_t crc32(const void *buf, uint32_t size);
uint32_t crc32HW(const void *data, uint32_t n_bytes);

#endif /* INC_CRC_H_ */
