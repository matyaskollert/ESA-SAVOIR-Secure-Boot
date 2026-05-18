/*
 * io_utils.h — Simple file I/O helpers for the host benchmark tool.
 *
 * All functions return 0 on success and -1 on any error (with a perror()
 * message printed to stderr).  Callers own any buffer allocated by
 * io_read_file() and must free() it when done.
 */

#ifndef BENCHMARK_IO_UTILS_H
#define BENCHMARK_IO_UTILS_H

#include <stddef.h>
#include <stdint.h>

/**
 * Write @p len bytes from @p data to the file at @p path.
 * Creates or truncates the file.  Directories in the path must already exist.
 *
 * @param path  Destination file path.
 * @param data  Source buffer.
 * @param len   Number of bytes to write.
 * @return      0 on success, -1 on fopen / fwrite failure.
 */
int io_write_file(const char* path, const uint8_t* data, size_t len);

/**
 * Read the entire contents of the file at @p path into a heap-allocated buffer.
 * On success *buf is set to a malloc'd array and *len is set to the file size.
 * The caller must free(*buf) when done.
 *
 * @param path  Source file path.
 * @param buf   Output: pointer to the allocated buffer (caller must free).
 * @param len   Output: number of bytes read.
 * @return      0 on success, -1 on fopen / fread failure or empty file.
 */
int io_read_file(const char* path, uint8_t** buf, size_t* len);

#endif /* BENCHMARK_IO_UTILS_H */
