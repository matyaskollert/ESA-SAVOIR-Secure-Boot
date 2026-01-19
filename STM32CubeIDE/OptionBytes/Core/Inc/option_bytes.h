/*
 * option_bytes.h
 *
 *  Created on: Jan 19, 2026
 *      Author: Matyas
 */

#ifndef INC_OPTION_BYTES_H_
#define INC_OPTION_BYTES_H_

#include "stm32f4xx_hal.h"

void disableSectorWriteProtection(uint32_t sector);

void enableSectorWriteProtection(uint32_t sector);

uint32_t checkSectorWriteProtection(uint32_t sector);

#endif /* INC_OPTION_BYTES_H_ */
