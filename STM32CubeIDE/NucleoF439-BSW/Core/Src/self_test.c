/*
 * self_test.c
 *
 *  Created on: Feb 9, 2026
 *      Author: Matyas
 */

#include <stdio.h>
#include "self_test.h"
#include "option_bytes.h"

#define BSW_FLASH_OB_SECTORS                                                                       \
	OB_WRP_SECTOR_0 | OB_WRP_SECTOR_1 | OB_WRP_SECTOR_2 | OB_WRP_SECTOR_3 | OB_WRP_SECTOR_4

int16_t performSelfTests(void)
{
	// TODO: Add BSW CRC Check - where should the CRC be stored?

	if (checkSectorWriteProtection(BSW_FLASH_OB_SECTORS) != 0)
	{
		printf("BSW protection disabled!\r\n");
		if (enableSectorWriteProtection(BSW_FLASH_OB_SECTORS) != 0)
		{
			printf("Locking BSW sectors failed\r\n");
			return 1;
		}
		return 0;
	}

	return 0;
}
