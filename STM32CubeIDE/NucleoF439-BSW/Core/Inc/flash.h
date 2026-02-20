/*
 * flash.h
 *
 *  Created on: Jan 19, 2026
 *      Author: Matyas
 */

#ifndef INC_FLASH_H_
#define INC_FLASH_H_

#include "stm32f4xx_hal.h"

#define BOOT_FLASH_ADDRESS		0x08020000U
#define BOOT_FLASH_SECTOR 		FLASH_SECTOR_5
#define BOOT_FLASH_OB_SECTOR 	OB_WRP_SECTOR_5
#define UPDATE_FLASH_ADDRESS  	0x08040000U
#define UPDATE_FLASH_SECTOR 	FLASH_SECTOR_6
#define UPDATE_FLASH_OB_SECTOR 	OB_WRP_SECTOR_6
#define SWAP_FLASH_ADDRESS  	0x08060000U
#define SWAP_FLASH_SECTOR 		FLASH_SECTOR_7
#define SWAP_FLASH_OB_SECTOR 	OB_WRP_SECTOR_7

#define COMM_FLASH_ADDRESS  	0x08080000U
#define COMM_FLASH_SECTOR 		FLASH_SECTOR_8
#define COMM_FLASH_OB_SECTOR 	OB_WRP_SECTOR_8
#define COUNTER_FLASH_ADDRESS  	0x080A0000U
#define COUNTER_FLASH_SECTOR 	FLASH_SECTOR_9
#define COUNTER_FLASH_OB_SECTOR OB_WRP_SECTOR_9

#define REPORT_FLASH_ADDRESS  	0x080C0000U
#define REPORT_FLASH_SECTOR 	FLASH_SECTOR_10
#define REPORT_FLASH_OB_SECTOR  OB_WRP_SECTOR_10

int16_t eraseFlashSector(uint32_t sector);

int16_t writeFlashSector(uint32_t sector, uint32_t address, uint32_t* buffer, uint32_t bufferLength);
int16_t writeFlashBlock(uint32_t address, uint32_t* buffer, uint32_t bufferLength);
int16_t writeFlashWord(uint32_t address, uint32_t value);



#endif /* INC_FLASH_H_ */
