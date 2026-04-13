#ifndef BENCHMARK_IO_UTILS_H
#define BENCHMARK_IO_UTILS_H

#include <stddef.h>
#include <stdint.h>

int io_write_file(const char* path, const uint8_t* data, size_t len);
int io_read_file(const char* path, uint8_t** buf, size_t* len);

#endif /* BENCHMARK_IO_UTILS_H */
