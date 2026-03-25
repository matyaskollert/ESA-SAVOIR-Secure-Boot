/*
 * boot.c
 *
 *  Created on: Dec 15, 2025
 *      Author: Matyas
 */

#include "image.h"
#include "boot.h"
#include "flash.h"


int16_t boot(void)
{
	/* Stamp BOOT_ATTEMPTED before jumping. If the app crashes or resets
	* without clearing this status, the next bootloader run will detect
	* the failure and trigger rollback evaluation. */
	// TODO: error checking?
    setBootloaderStatus(BOOTLOADER_STATUS_BOOT_ATTEMPTED);
	if (imageValidate(BOOT) != 0)
	{
		return 1;
	}
	if (imageLoad(BOOT) != 0)
	{
		return 2;
	}
	if (imageValidateInRAM(BOOT) != 0)
	{
		return 3;
	}
	imageStart();
	return 0;
}




