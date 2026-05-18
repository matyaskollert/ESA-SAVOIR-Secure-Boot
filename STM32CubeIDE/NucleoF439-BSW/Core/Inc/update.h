/*
 * update.h
 *
 * Image update and slot-swap logic for the BSW.
 *
 * Three main operations are supported:
 *  1. receiveUpdateData()   — receive a new image via UART into RAM then write
 *                             it to the secondary flash slot.
 *  2. swapMainWithUpdate()  — promote the secondary image to primary by
 *                             updating the protected BSW state (rollback counter
 *                             and primary-slot flag).
 *  3. checkSystem*() /      — query and configure the flash write-protection
 *     setupSystem*()          state required by each operation.
 *
 * Outcome codes written to bsw_report_t are documented in bsw_report.h.
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#ifndef INC_UPDATE_H_
#define INC_UPDATE_H_

#include "stm32f4xx_hal.h"
#include "bsw_report.h"

/* =========================================================================
 * Image receive and swap
 * ========================================================================= */

/**
 * Receive a new application image from the ground station via UART and
 * store it in the secondary flash slot.
 *
 * Uses the ECSS packet protocol: START_UPLOAD → n × DATA_CHUNK → END_UPLOAD.
 * Validates the image magic, version (must be ≥ rollback floor), and CRC after
 * all chunks have been received.  The digital signature is NOT verified here;
 * it is verified during a subsequent swap command.
 *
 * Populates @p report with step flags and the outcome code before returning.
 *
 * @param uart    UART handle used for ECSS communication.
 * @param report  In/out: report struct initialised with BSW_REPORT_TYPE_UPDATE.
 * @return        0 on success (image written to secondary slot),
 *                or a positive step number on the first failure.
 */
int16_t receiveUpdateData(UART_HandleTypeDef* uart, bsw_report_t* report);

/**
 * Promote the secondary image to primary by atomically updating the protected
 * BSW state sector (rollback counter and primary-slot flag).
 * On hardware-swap builds, also physically copies flash sectors.
 *
 * Populates @p report with step flags and the outcome code before returning.
 *
 * @param report  In/out: report struct initialised with BSW_REPORT_TYPE_SWAP.
 * @return        0 on success, positive step number on failure.
 */
int16_t swapMainWithUpdate(bsw_report_t* report);

/**
 * Atomically write a new rollback counter and primary-slot flag to the
 * protected BSW state sector (FLASH_SECTOR_9).
 * Manages HAL_FLASH_Unlock / HAL_FLASH_Lock internally.
 *
 * @param rollback_counter  New monotonic rollback counter value.
 * @param primary_slot      PROTECTED_BSW_STATE_PRIMARY_SLOT_A or _SLOT_B.
 * @return                  0 on success, 1 on HAL error.
 */
int16_t setProtectedBswState(uint32_t rollback_counter, uint32_t primary_slot);

/* =========================================================================
 * Flash write-protection configuration
 *
 * "Setup" functions modify Option Bytes; if a change is needed they trigger
 * a system reset via OB_Launch (they do not return in that case).
 * "Check" functions are read-only and return 0 if the expected protection
 * state is already in place, non-zero otherwise.
 * ========================================================================= */

/**
 * Prepare the flash protection state for a slot swap.
 * Unlocks the primary slot and BSW-state sector so they can be updated.
 * Triggers a reset if any OB change is needed.
 *
 * @return  0 if already in the correct state, -1 on HAL error.
 */
int16_t setupSystemForImageSwap(void);

/**
 * Verify the flash protection state is correct for a slot swap.
 * Primary slot and BSW-state sector must be unprotected.
 *
 * @return  0 if the system is ready for a swap, non-zero otherwise.
 */
int16_t checkSystemForImageSwap(void);

/**
 * Configure flash protection for nominal (boot) operation.
 * Write-protects the primary slot and BSW-state sector.
 * Triggers a reset if any OB change is needed.
 *
 * @return  0 if already in the correct state, -1 on HAL error.
 */
int16_t setupSystemForNominal(void);

/**
 * Verify the flash protection state is correct for nominal boot.
 * Primary slot and BSW-state sector must be write-protected.
 *
 * @return  0 if the system is correctly configured, non-zero otherwise.
 */
int16_t checkSystemForNominal(void);

/**
 * Configure flash protection for an image update.
 * Write-protects the primary slot and BSW-state sector; unprotects the
 * secondary slot so a new image can be written to it.
 * Triggers a reset if any OB change is needed.
 *
 * @return  0 if already in the correct state, -1 on HAL error.
 */
int16_t setupSystemForUpdate(void);

/**
 * Verify the flash protection state is correct for an image update.
 * Primary slot and BSW-state sector must be protected; secondary slot must
 * be unprotected.
 *
 * @return  0 if the system is correctly configured, non-zero otherwise.
 */
int16_t checkSystemForUpdate(void);

/* =========================================================================
 * Rollback and version management
 * ========================================================================= */

/**
 * Verify that the secondary slot contains a valid image (magic, CRC) and
 * that the digital signature is authentic.
 *
 * @return  0 on success, 1 on CRC failure, 2 on signature failure.
 */
int16_t checkUpdateValidity(void);

/**
 * Verify that the secondary image version is at or above the rollback floor.
 *
 * @return  0 if the version is acceptable, non-zero if it is too low or the
 *          secondary slot has no valid header.
 */
int16_t checkUpdateVersion(void);

/**
 * Compute the lowest image version that may be installed without violating
 * the anti-rollback policy.
 *
 * @return  Minimum acceptable imageVersion.
 */
uint32_t getLowestAllowedVersion(void);

/**
 * Read the current rollback counter from the protected BSW state sector.
 *
 * @return  Stored counter value (0xFFFFFFFF if the sector is erased).
 */
uint32_t getCounterValue(void);

/**
 * Write a new rollback counter to the protected BSW state sector.
 * Preserves the existing primary-slot flag.
 *
 * @param newValue  New monotonic counter value.
 * @return          0 on success, 1 on HAL error.
 */
int16_t setCounterValue(uint32_t newValue);

/**
 * Evaluate whether a rollback should be performed.
 * Checks whether the last boot was attempted but not confirmed by the ASW
 * (i.e. BOOTLOADER_STATUS_BOOT_ATTEMPTED is still stored in the comm sector).
 *
 * @return  1 if rollback should be triggered, 0 otherwise.
 */
int16_t checkRollbackCondition(void);

#endif /* INC_UPDATE_H_ */
