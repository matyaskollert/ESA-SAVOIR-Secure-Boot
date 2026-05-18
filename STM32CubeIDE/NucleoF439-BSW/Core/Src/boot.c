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
#include "bsw_report.h"

int16_t boot(bsw_report_t* report)
{
	/* Reaching this function means checkSystemForNominal() already passed. */
	report->step_flags |= BSW_NOMINAL_FLAG_SYSTEM_OK;

	/* Stamp BOOT_ATTEMPTED before jumping. If the app crashes or resets
	 * without clearing this status, the next bootloader run will detect
	 * the failure and trigger rollback evaluation. */
	if (setBootloaderStatus(BOOTLOADER_STATUS_BOOT_ATTEMPTED) != 0)
	{
		report->outcome = 1;
		bsw_report_flush(report);
		return 1;
	}
	report->step_flags |= BSW_NOMINAL_FLAG_STATUS_SET;

	ImageSlot primary = getPrimarySlot();
	if (imageValidate(primary) != 0)
	{
		report->outcome = 2;
		bsw_report_flush(report);
		return 2;
	}
	report->step_flags |= BSW_NOMINAL_FLAG_CRC_OK;

	/* imageLoad copies image to RAM and verifies digital signature internally */
	if (imageLoad(primary) != 0)
	{
		report->outcome = 3;
		bsw_report_flush(report);
		return 3;
	}
	report->step_flags |= BSW_NOMINAL_FLAG_SIG_OK;

	if (imageValidateInRAM(primary) != 0)
	{
		report->outcome = 4;
		bsw_report_flush(report);
		return 4;
	}
	report->step_flags |= BSW_NOMINAL_FLAG_RAM_CRC_OK;

	bsw_report_flush(report);
	imageStart();
	return 0; /* unreachable; imageStart() is noreturn */
}
