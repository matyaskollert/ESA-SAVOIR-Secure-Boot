/*
 * option_bytes.h
 *
 *  Created on: Jan 19, 2026
 *      Author: Matyas
 */

#ifndef INC_OPTION_BYTES_H_
#define INC_OPTION_BYTES_H_

#include "stm32f4xx_hal.h"

int16_t disableSectorWriteProtection(uint32_t sectorMask);

int16_t enableSectorWriteProtection(uint32_t sectorMask);

int16_t checkSectorWriteProtection(uint32_t sectorMask);

/* Returns 1 if every sector in sectorMask is unprotected, 0 otherwise. */
int16_t checkAllSectorsUnprotected(uint32_t sectorMask);

int16_t prepareOBForSwap(void);

int16_t lockOBAfterSwap(void);

#endif /* INC_OPTION_BYTES_H_ */
