
#include "crc.h"
#include "main.h"

// External CRC handle from main.c
extern CRC_HandleTypeDef hcrc;

uint32_t crc32_for_byte(uint32_t r) {
  for(int j = 0; j < 8; ++j)
    r = (r & 1? 0: (uint32_t)0xEDB88320L) ^ r >> 1;
  return r ^ (uint32_t)0xFF000000L;
}



uint32_t crc32(const void *data, uint32_t n_bytes) {
  uint32_t crc = 0;
  static uint32_t table[0x100];
  if(!*table)
    for(size_t i = 0; i < 0x100; ++i)
      table[i] = crc32_for_byte(i);
  for(size_t i = 0; i < n_bytes; ++i)
    crc = table[(uint8_t)crc ^ ((uint8_t*)data)[i]] ^ crc >> 8;

  return crc;
}


uint32_t crc32HW(const void *data, uint32_t n_bytes) {
	uint32_t n_words = n_bytes / 4;
	uint32_t crc_result = HAL_CRC_Calculate(&hcrc, (uint32_t *) data, n_bytes);
	return crc_result;
}
