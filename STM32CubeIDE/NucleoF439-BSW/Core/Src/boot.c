/*
 * boot.c
 *
 *  Created on: Dec 15, 2025
 *      Author: Matyas
 */

#include "image.h"
#include "boot.h"
#include "flash.h"
#include "update.h"


int16_t boot(void)
{
	/* Stamp BOOT_ATTEMPTED before jumping. If the app crashes or resets
	* without clearing this status, the next bootloader run will detect
	* the failure and trigger rollback evaluation. */
	if (setBootloaderStatus(BOOTLOADER_STATUS_BOOT_ATTEMPTED) != 0)
		return 1;
	ImageSlot primary = getPrimarySlot();
	if (imageValidate(primary) != 0)
		return 2;
	if (imageLoad(primary) != 0)
		return 3;
	if (imageValidateInRAM(primary) != 0)
		return 4;
	imageStart();
	return 0;
}




