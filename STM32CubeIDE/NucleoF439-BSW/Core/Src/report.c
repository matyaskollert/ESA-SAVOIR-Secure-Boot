/*
 * report.c
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#include "report.h"
#include <stdio.h>
#include "image.h"
#include "flash.h"


void printImageHeaders()
{
	const image_header_t* bootImage = (const image_header_t *)(BOOT_FLASH_ADDRESS);
	printf("BOOT version: %u\r\n", bootImage->imageVersion);
	const image_header_t* updateImage = (const image_header_t *)(UPDATE_FLASH_ADDRESS);
	printf("UPDATE version: %u\r\n", updateImage->imageVersion);
	const image_header_t* swapImage = (const image_header_t *)(SWAP_FLASH_ADDRESS);
	printf("SWAP version: %u\r\n", swapImage->imageVersion);
}

int16_t createErrorReport(ReportLevel level)
{
	switch (level)
	{
	case ERROR_REPORT:
		// TODO: Implement ERROR BOOT REPORT
		break;
	case INFO_REPORT:
		// TODO: Implement INFO BOOT REPORT
		break;
	}

	return 0;
}
