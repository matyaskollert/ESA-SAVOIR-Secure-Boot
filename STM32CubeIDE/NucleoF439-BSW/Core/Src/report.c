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


void printImageHeaders(void)
{
	ImageSlot primary   = getPrimarySlot();
	ImageSlot secondary = getSecondarySlot();

	const image_header_t* slotAImage = (const image_header_t *)(SLOT_A_FLASH_ADDRESS);
	const image_header_t* slotBImage = (const image_header_t *)(SLOT_B_FLASH_ADDRESS);

	printf("SLOT_A version: %u [%s]\r\n", slotAImage->imageVersion,
	       (primary == SLOT_A) ? "PRIMARY" : "SECONDARY");
	printf("SLOT_B version: %u [%s]\r\n", slotBImage->imageVersion,
	       (primary == SLOT_B) ? "PRIMARY" : "SECONDARY");
	(void)secondary;
}
