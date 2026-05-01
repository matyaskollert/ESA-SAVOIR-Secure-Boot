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

typedef enum {
    /* Persistent - stored to flash */
    BOOTLOADER_STATUS_NOMINAL        = 0xAA,  /* Boot the application image */
    BOOTLOADER_STATUS_STANDBY        = 0xBB,  /* Stay in standby, await commands */
    BOOTLOADER_STATUS_SWAP           = 0xCC,  /* Automatic image swap required */
    BOOTLOADER_STATUS_BOOT_ATTEMPTED = 0xDD,  /* Boot was attempted; app must clear this on successful start */
    /* Internal-only, transient - never stored to flash */
    BOOTLOADER_STATUS_UNKNOWN        = 0x00,  /* Unrecognised command */
    BOOTLOADER_STATUS_UPDATE         = 0x11,  /* Receive and store a new image */
    BOOTLOADER_STATUS_ROLLBACK       = 0x22,  /* Evaluate and perform rollback */
    BOOTLOADER_STATUS_RESET          = 0x33,  /* System reset */
    BOOTLOADER_STATUS_CHECK_VERSIONS = 0x44,  /* Print image headers */
} BootloaderStatus;

int16_t eraseFlashSector(uint32_t sector);

int16_t writeFlashSector(uint32_t sector, uint32_t address, uint32_t* buffer, uint32_t bufferLength);
int16_t writeFlashBlock(uint32_t address, uint32_t* buffer, uint32_t bufferLength);
int16_t writeFlashWord(uint32_t address, uint32_t value);

BootloaderStatus getBootloaderStatus(void);

int16_t setBootloaderStatus(BootloaderStatus newStatus);

#endif /* INC_FLASH_H_ */
