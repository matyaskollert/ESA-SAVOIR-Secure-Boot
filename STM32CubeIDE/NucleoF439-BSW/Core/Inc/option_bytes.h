/*
 * option_bytes.h
 *
 * STM32F439 Option-Byte write-protection (WRP) management.
 *
 * The STM32F4 WRP mechanism is "inverted": a protected sector has its
 * corresponding bit CLEAR in the WRP register; an unprotected sector has
 * its bit SET.  The HAL OB_WRPSTATE_ENABLE / _DISABLE constants follow the
 * same convention.
 *
 * Changing Option Bytes requires an OB_Launch which triggers a full system
 * reset; callers must not expect code to continue after enable/disable calls.
 *
 *  Created on: Jan 19, 2026
 *      Author: Matyas
 */

#ifndef INC_OPTION_BYTES_H_
#define INC_OPTION_BYTES_H_

#include "stm32f4xx_hal.h"

/**
 * Remove write-protection from every sector in @p sectorMask.
 * If all target sectors are already unprotected the function returns
 * immediately without touching the Option Bytes.
 * Otherwise, the new OB configuration is programmed and OB_Launch triggers a
 * system reset — this function does not return in that case.
 *
 * @param sectorMask  OR of OB_WRP_SECTOR_* constants identifying target sectors.
 * @return            0 if sectors were already unprotected (no-op), -1 on HAL error.
 */
int16_t disableSectorWriteProtection(uint32_t sectorMask);

/**
 * Apply write-protection to every sector in @p sectorMask.
 * If all target sectors are already protected the function returns
 * immediately without touching the Option Bytes.
 * Otherwise, the new OB configuration is programmed and OB_Launch triggers a
 * system reset — this function does not return in that case.
 *
 * @param sectorMask  OR of OB_WRP_SECTOR_* constants identifying target sectors.
 * @return            0 if sectors were already protected (no-op), -1 on HAL error.
 */
int16_t enableSectorWriteProtection(uint32_t sectorMask);

/**
 * Check the current write-protection state of @p sectorMask.
 *
 * @param sectorMask  OR of OB_WRP_SECTOR_* constants.
 * @return            0 if all sectors in @p sectorMask are write-protected,
 *                    1 if any sector is unprotected.
 */
int16_t checkSectorWriteProtection(uint32_t sectorMask);

/**
 * Check whether every sector in @p sectorMask is write-UNprotected.
 *
 * @param sectorMask  OR of OB_WRP_SECTOR_* constants.
 * @return            1 if every sector in @p sectorMask is unprotected,
 *                    0 if any sector is still protected.
 */
int16_t checkAllSectorsUnprotected(uint32_t sectorMask);

/**
 * Unlock the flash sectors required to perform an image swap.
 * Specifically removes WRP from the primary image slot and the protected
 * BSW-state sector so that their contents can be updated during the swap.
 * Triggers a system reset via OB_Launch if any protection needs changing.
 *
 * @return  0 if no protection change was needed, -1 on HAL error.
 */
int16_t prepareOBForSwap(void);

/**
 * Re-apply write-protection to the primary image slot and the protected
 * BSW-state sector after a swap has completed.
 * Triggers a system reset via OB_Launch if any protection needs changing.
 *
 * @return  0 if no protection change was needed, -1 on HAL error.
 */
int16_t lockOBAfterSwap(void);

#endif /* INC_OPTION_BYTES_H_ */
