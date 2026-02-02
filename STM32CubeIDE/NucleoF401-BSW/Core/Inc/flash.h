/*
 * flash.h
 *
 *  Created on: Jan 19, 2026
 *      Author: Matyas
 */

#ifndef INC_FLASH_H_
#define INC_FLASH_H_

#include "stm32f4xx_hal.h"

#define BOOT_FLASH_ADDRESS  0x08020000U
#define BOOT_FLASH_SECTOR FLASH_SECTOR_5
#define UPDATE_FLASH_ADDRESS  0x08040000U
#define UPDATE_FLASH_SECTOR FLASH_SECTOR_6
#define SWAP_FLASH_ADDRESS  0x08060000U
#define SWAP_FLASH_SECTOR FLASH_SECTOR_7

void writeFlashSector(uint32_t sector, uint32_t address, uint32_t* buffer, uint32_t bufferLength);

#endif /* INC_FLASH_H_ */
