/*
 * io_utils.c — Simple file I/O helpers for the host benchmark tool.
 *
 *  Created on: 2026
 *      Author: Matyas
 */

#include "io_utils.h"

#include <stdio.h>
#include <stdlib.h>

int io_write_file(const char* path, const uint8_t* data, size_t len)
{
	FILE* file_handle = fopen(path, "wb");
	if (!file_handle)
	{
		perror(path);
		return -1;
	}

	int write_status = (fwrite(data, 1, len, file_handle) == len) ? 0 : -1;
	fclose(file_handle);
	return write_status;
}

int io_read_file(const char* path, uint8_t** buf, size_t* len)
{
	FILE* file_handle = fopen(path, "rb");
	if (!file_handle)
	{
		perror(path);
		return -1;
	}

	fseek(file_handle, 0, SEEK_END);
	long file_size = ftell(file_handle);
	rewind(file_handle);
	if (file_size <= 0)
	{
		fclose(file_handle);
		return -1;
	}

	*buf = (uint8_t*)malloc((size_t)file_size);
	if (!*buf)
	{
		fclose(file_handle);
		return -1;
	}

	if (fread(*buf, 1, (size_t)file_size, file_handle) != (size_t)file_size)
	{
		free(*buf);
		*buf = NULL;
		fclose(file_handle);
		return -1;
	}

	*len = (size_t)file_size;
	fclose(file_handle);
	return 0;
}
