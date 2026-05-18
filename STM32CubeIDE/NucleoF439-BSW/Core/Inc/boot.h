/*
 * boot.h
 *
 * Nominal boot sequence: CRC validation, image loading, digital-signature
 * verification, and final jump to the application image.
 *
 * boot() is entered only after checkSystemForNominal() has confirmed that
 * the required flash sectors are write-protected.  A BSW report is populated
 * incrementally as each step completes and flushed to flash before any reset
 * or the final imageStart() call.
 *
 *  Created on: Dec 15, 2025
 *      Author: Matyas
 */

#ifndef INC_BOOT_H_
#define INC_BOOT_H_

#include "stm32f4xx_hal.h"
#include "bsw_report.h"

/**
 * Execute the nominal boot sequence for the primary image slot.
 *
 * Steps (in order):
 *  1. Write BOOTLOADER_STATUS_BOOT_ATTEMPTED to the communication sector.
 *  2. Validate the primary-slot CRC (imageValidate).
 *  3. Load the image into RAM and verify its digital signature (imageLoad).
 *  4. Validate the RAM copy CRC (imageValidateInRAM).
 *  5. Call imageStart() — this function does not return on success.
 *
 * Each passing step sets the corresponding BSW_NOMINAL_FLAG_* bit in
 * @p report->step_flags.  On failure @p report->outcome is set to the step
 * number and the report is flushed to flash before returning.
 *
 * @param report  In/out: report struct initialised by the caller with
 *                bsw_report_init(BSW_REPORT_TYPE_NOMINAL).
 * @return        0 if imageStart() is called (non-returning path),
 *                or the failing step number (1–4) on error.
 */
int16_t boot(bsw_report_t* report);

#endif /* INC_BOOT_H_ */
