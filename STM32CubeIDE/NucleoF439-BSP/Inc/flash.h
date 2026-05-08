/*
 * flash.h
 *
 *  Created on: Jan 19, 2026
 *      Author: Matyas
 */

#ifndef INC_FLASH_H_
#define INC_FLASH_H_

#include "stm32f4xx_hal.h"
#include <stdint.h>

/* Image slot identifiers.  SLOT_A and SLOT_B refer to the two persistent
 * flash partitions; RAM is used when the image has been loaded into SRAM. */
typedef enum { SLOT_A, SLOT_B, RAM } ImageSlot;

/* Image slot A: first flash partition (sector 5, 128 KB). */
#define SLOT_A_FLASH_ADDRESS	0x08020000U
#define SLOT_A_FLASH_SECTOR		FLASH_SECTOR_5
#define SLOT_A_FLASH_OB_SECTOR	OB_WRP_SECTOR_5
/* Image slot B: second flash partition (sector 6, 128 KB). */
#define SLOT_B_FLASH_ADDRESS	0x08040000U
#define SLOT_B_FLASH_SECTOR		FLASH_SECTOR_6
#define SLOT_B_FLASH_OB_SECTOR	OB_WRP_SECTOR_6
/* Image swap sector used when HARDWARE_SWAP is enabled (sector 7, 128KB). */
#define SWAP_FLASH_ADDRESS      0x08060000U
#define SWAP_FLASH_SECTOR      FLASH_SECTOR_7
#define SWAP_FLASH_OB_SECTOR    OB_WRP_SECTOR_7

#define COMM_FLASH_ADDRESS  	0x08080000U
#define COMM_FLASH_SECTOR 		FLASH_SECTOR_8
#define COMM_FLASH_OB_SECTOR 	OB_WRP_SECTOR_8
/* BSW persistent state sector (sector 9, 128 KB). Holds the rollback counter
 * and the primary-slot flag, both write-protected during nominal operation. */
#define PROTECTED_BSW_STATE_FLASH_ADDRESS	0x080A0000U
#define PROTECTED_BSW_STATE_FLASH_SECTOR	FLASH_SECTOR_9
#define PROTECTED_BSW_STATE_FLASH_OB_SECTOR	OB_WRP_SECTOR_9

/* Magic values for protected_bsw_state_t.primary_slot.
 * Any value other than PROTECTED_BSW_STATE_PRIMARY_SLOT_B (including the erased
 * 0xFFFFFFFF default) means SLOT_A is the primary partition. */
#define PROTECTED_BSW_STATE_PRIMARY_SLOT_A	0xAAAAAAAAU
#define PROTECTED_BSW_STATE_PRIMARY_SLOT_B	0xBBBBBBBBU

/* In-flash layout of the protected BSW state sector.  Cast the sector base
 * address to a const pointer of this type to read fields directly. */
typedef struct __attribute__((packed)) {
    uint32_t rollback_counter; /* Monotonic rollback counter                          */
    uint32_t primary_slot;     /* PROTECTED_BSW_STATE_PRIMARY_SLOT_A / _SLOT_B        */
} protected_bsw_state_t;

#define PROTECTED_BSW_STATE ((const protected_bsw_state_t *)(PROTECTED_BSW_STATE_FLASH_ADDRESS))

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

uint32_t getSlotFlashSector(ImageSlot slot);
uint32_t getSlotFlashAddress(ImageSlot slot);
uint32_t getSlotFlashOBSector(ImageSlot slot);

uint32_t getPrimaryFlag(void);

ImageSlot getPrimarySlot(void);

ImageSlot getSecondarySlot(void);

#endif /* INC_FLASH_H_ */
