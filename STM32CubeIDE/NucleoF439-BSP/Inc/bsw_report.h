/*
 * bsw_report.h
 *
 * BSW boot-event report: struct definition, flash layout constants, and
 * step-flag bit-masks.  Placed in the BSP so that any software layer
 * (BSW, ASW, ground tools) can parse reports stored in flash.
 *
 *  Created on: May 8, 2026
 *      Author: Matyas
 */

#ifndef INC_BSW_REPORT_H_
#define INC_BSW_REPORT_H_

#include <stdint.h>
#include "flash.h"   /* ImageSlot, REPORT_FLASH_ADDRESS, REPORT_FLASH_SECTOR */

/* =========================================================================
 * Flash circular buffer layout
 *
 * REPORT_FLASH_SECTOR (sector 10, 128 KB) is split into BSW_REPORT_MAX_COUNT
 * equal-sized slots.  Reports are written sequentially; when all slots are
 * occupied the sector is erased and writing restarts from slot 0, effectively
 * overwriting the oldest entry first.
 * ========================================================================= */
#define BSW_REPORT_MAGIC        0xBEEF0042U              /* Marks a valid entry  */
#define BSW_REPORT_MAX_COUNT    5U                        /* Max stored reports   */
#define BSW_REPORT_SLOT_SIZE    (sizeof(bsw_report_t))       /* Size of one report   */

/* =========================================================================
 * Report type
 * ========================================================================= */
typedef enum {
    BSW_REPORT_TYPE_NOMINAL = 0x01,  /* Normal boot sequence                  */
    BSW_REPORT_TYPE_UPDATE  = 0x02,  /* Image upload and store to flash        */
    BSW_REPORT_TYPE_SWAP    = 0x03,  /* Slot swap / primary-flag flip          */
} bsw_report_type_t;

/* =========================================================================
 * Step-flag bit definitions
 *
 * Each report type uses the same step_flags field, but bit positions carry
 * type-specific meaning.  Bits are SET when the corresponding check PASSES.
 * ========================================================================= */

/* -- NOMINAL boot (type == BSW_REPORT_TYPE_NOMINAL) ---------------------- */
/* Steps are ordered; a flag is SET only when the corresponding check PASSES. */
#define BSW_NOMINAL_FLAG_STATUS_SET  (1U << 0)  /* BOOT_ATTEMPTED status written to flash                  */
#define BSW_NOMINAL_FLAG_CRC_OK      (1U << 1)  /* Primary-slot CRC (imageValidate) passed                 */
#define BSW_NOMINAL_FLAG_SIG_OK      (1U << 2)  /* Primary-slot digital signature (imageVerify) passed     */
#define BSW_NOMINAL_FLAG_RAM_CRC_OK  (1U << 3)  /* RAM copy CRC (imageValidateInRAM) passed                */
#define BSW_NOMINAL_FLAG_SYSTEM_OK   (1U << 4)  /* checkSystemForNominal() passed (sectors protected)      */

/* -- UPDATE sequence (type == BSW_REPORT_TYPE_UPDATE) -------------------- */
#define BSW_UPDATE_FLAG_VERSION_OK   (1U << 0)  /* Received version >= rollback floor */
#define BSW_UPDATE_FLAG_RAM_CRC_OK   (1U << 1)  /* Received image CRC passed          */
#define BSW_UPDATE_FLAG_RAM_SIG_OK   (1U << 2)  /* Received image signature valid     */
#define BSW_UPDATE_FLAG_FLASH_OK     (1U << 3)  /* Image written to secondary slot    */
#define BSW_UPDATE_FLAG_SYSTEM_OK    (1U << 4)  /* checkSystemForUpdate() passed      */

/* -- SWAP sequence (type == BSW_REPORT_TYPE_SWAP) ------------------------ */
#define BSW_SWAP_FLAG_VERSION_OK     (1U << 0)  /* Secondary version >= floor                             */
#define BSW_SWAP_FLAG_CRC_OK         (1U << 1)  /* Secondary-slot CRC passed                              */
#define BSW_SWAP_FLAG_SIG_OK         (1U << 2)  /* Secondary-slot signature verified                      */
#define BSW_SWAP_FLAG_COUNTER_OK     (1U << 3)  /* Rollback counter written                               */
#define BSW_SWAP_FLAG_SLOT_FLIPPED   (1U << 4)  /* Primary-slot flag updated                              */
#define BSW_SWAP_FLAG_SYSTEM_OK      (1U << 5)  /* checkSystemForImageSwap() passed (sectors unlocked)    */

/* =========================================================================
 * Outcome codes
 *
 * The outcome field is 0 on success.  On failure it holds the code of the
 * step that failed; the step_flags field shows how far execution reached
 * before the failure occurred.
 *
 * -- BSW_REPORT_TYPE_NOMINAL (boot.c :: boot()) ---------------------------
 *
 *  0  Success — all checks passed; imageStart() was called.
 *  1  setBootloaderStatus(BOOT_ATTEMPTED) failed (flash write error).
 *  2  imageValidate(primary) failed — CRC mismatch in flash.
 *  3  imageLoad(primary) failed — digital signature invalid or RAM write error.
 *  4  imageValidateInRAM(primary) failed — CRC mismatch after RAM copy.
 *  5  checkSystemForNominal() failed — primary slot or BSW-state sector not write-protected.
 *     (written in main_loop.c; boot() is never entered)
 *
 * -- BSW_REPORT_TYPE_UPDATE (update.c :: receiveUpdateData()) --------------
 *
 *  0  Success — image verified in RAM and written to the secondary slot.
 *  1  UART error receiving the START_UPLOAD packet header.
 *  2  Unexpected packet type where START_UPLOAD was expected.
 *  3  START_UPLOAD payload length is not 4 bytes.
 *  4  UART error receiving the START_UPLOAD payload (image size field).
 *  5  UART error sending the ACK for the START_UPLOAD packet.
 *  6  UART error receiving a DATA_CHUNK packet header.
 *  7  Unexpected packet type where DATA_CHUNK was expected.
 *  8  UART error receiving a DATA_CHUNK payload.
 *  9  First chunk rejected: bad magic number or version below rollback floor.
 * 10  UART error sending the ACK for a DATA_CHUNK packet.
 * 11  imageValidateInRAM(RAM) failed — CRC mismatch after full image received.
 * 12  verifySignature() failed — digital signature of received image invalid.
 * 13  HAL_FLASH_Unlock() or HAL_FLASH_Lock() returned an error.
 * 14  writeFlashSector() failed — could not write image to secondary slot.
 * 15  checkSystemForUpdate() failed — primary slot or BSW-state sector not write-protected,
 *     or secondary slot is write-protected.  (written in main_loop.c; receiveUpdateData() is never entered)
 *
 * -- BSW_REPORT_TYPE_SWAP (update.c :: swapBootWithUpdate() and main_loop.c) -
 *
 *  0  Success — primary-slot flag (and counter) updated; images exchanged.
 *  1  imageGetHeader(primary) returned NULL — primary slot has no valid header.
 *  2  imageGetHeader(secondary) returned NULL — secondary slot has no valid header.
 *  3  Cannot determine the new rollback counter value (counter logic error).
 *  4  HAL_FLASH_Unlock() or HAL_FLASH_Lock() returned an error
 *     (hardware-swap build only).
 *  5  writeFlashSector() failed during the physical image copy
 *     (hardware-swap build only).
 *  6  setProtectedBswState() failed — could not persist counter or slot flag.
 *  7  checkSystemForImageSwap() failed — primary slot or BSW-state sector not unlocked.
 *     (written in main_loop.c; swapBootWithUpdate() is never entered)
 *  8  checkUpdateVersion() failed — secondary image version is below the rollback floor,
 *     or secondary slot has no valid header.
 *     (written in main_loop.c; swapBootWithUpdate() is never entered)
 *  9  checkUpdateValidity() failed at CRC — secondary-slot CRC mismatch.
 *     (written in main_loop.c; swapBootWithUpdate() is never entered)
 * 10  checkUpdateValidity() failed at signature — secondary-slot digital signature invalid.
 *     (written in main_loop.c; swapBootWithUpdate() is never entered)
 * ========================================================================= */

/* =========================================================================
 * Report entry — stored packed in one flash slot per entry.
 *
 * An erased (unwritten) slot has 0xFFFFFFFF at the magic offset, which is
 * distinct from BSW_REPORT_MAGIC and is used to find the next free slot.
 *
 * Layout (20 bytes):
 *   offset  0  uint32_t  magic
 *   offset  4  uint8_t   type
 *   offset  5  uint8_t   outcome
 *   offset  6  uint8_t   primary_slot
 *   offset  7  uint8_t   pad
 *   offset  8  uint32_t  rollback_counter
 *   offset 12  uint16_t  primary_version
 *   offset 14  uint16_t  secondary_version
 *   offset 16  uint32_t  step_flags
 * ========================================================================= */
typedef struct __attribute__((packed)) {
    uint32_t magic;              /* BSW_REPORT_MAGIC; erased flash reads 0xFFFFFFFF  */
    uint8_t  type;               /* bsw_report_type_t                                */
    uint8_t  outcome;            /* 0 = success; otherwise the step number that failed
                                  * (matches the step order implied by the flag bits) */
    uint8_t  primary_slot;       /* ImageSlot at the time of the report              */
    uint8_t  pad;                /* Reserved, written as 0                           */
    uint32_t rollback_counter;   /* Rollback counter at the time of the report       */
    uint16_t primary_version;    /* imageVersion of the primary-slot image           */
    uint16_t secondary_version;  /* imageVersion of the secondary-slot image         */
    uint32_t step_flags;         /* Passed-step bits; interpretation is type-specific */
} bsw_report_t;                  /* sizeof == 20 bytes                               */

/* Read-only pointer to the n-th report slot in flash (0-based). */
#define BSW_REPORT_SLOT(n) \
    ((const bsw_report_t *)(REPORT_FLASH_ADDRESS + (uint32_t)(n) * BSW_REPORT_SLOT_SIZE))

/* =========================================================================
 * API (implemented in NucleoF439-BSP/Src/bsw_report.c)
 * ========================================================================= */

/**
 * Load all flash slots into the internal RAM array and determine the index
 * of the next write target.  Must be called once at startup before any
 * bsw_report_init / bsw_report_flush call.
 */
void bsw_report_load(void);

/**
 * Initialise an in-RAM report.
 * Fills all fields with safe defaults and captures the current primary slot,
 * secondary slot versions, and rollback counter from flash.
 */
void bsw_report_init(bsw_report_t *r, bsw_report_type_t type);

/**
 * Persist the in-RAM report to the next free flash slot.
 * If all BSW_REPORT_MAX_COUNT slots are occupied the sector is erased first,
 * then the report is written to slot 0.
 *
 * @return  0 on success, non-zero on flash error.
 */
int16_t bsw_report_flush(const bsw_report_t *r);

/**
 * Return a read-only pointer to a report from the in-RAM array ordered by age.
 * age == 0 is the most recently flushed report; age == BSW_REPORT_MAX_COUNT-1
 * is the oldest (or the next slot to be overwritten).
 */
const bsw_report_t* bsw_report_get_by_age(uint8_t age);

#endif /* INC_BSW_REPORT_H_ */
