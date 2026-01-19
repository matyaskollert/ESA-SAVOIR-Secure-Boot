/*
 * flash.h
 *
 *  Created on: Jan 19, 2026
 *      Author: Matyas
 */

#ifndef INC_FLASH_H_
#define INC_FLASH_H_

#include "stm32f4xx_hal.h"

void writeFlashSector(uint32_t sector, uint32_t address, uint32_t* value, uint32_t size);

#endif /* INC_FLASH_H_ */
