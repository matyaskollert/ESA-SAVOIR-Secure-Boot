/*
 * bsw_report.c
 *
 * All five report slots are kept in a static RAM array (g_reports[]) at all
 * times.  On every flush only one logical entry changes:
 *
 *   1. g_reports[g_next_idx] is updated with the new report.
 *   2. The full REPORT_FLASH_SECTOR is erased (hardware constraint — all five
 *      slots share a single 128 KB NOR sector; sub-sector erase is not
 *      available on this device).
 *   3. Every valid entry in g_reports[] is re-written to flash, restoring the
 *      four untouched reports unchanged.
 *   4. g_next_idx advances mod BSW_REPORT_MAX_COUNT.
 *
 *  Created on: May 8, 2026
 *      Author: Matyas
 */

#include "bsw_report.h"
#include "flash.h"
#include "image.h"
#include "stm32f4xx_hal.h"

/* -------------------------------------------------------------------------
 * Private state
 * ---------------------------------------------------------------------- */
static bsw_report_t g_reports[BSW_REPORT_MAX_COUNT];
static uint8_t g_next_idx;

/* -------------------------------------------------------------------------
 * bsw_report_load
 *
 * Reads every flash slot into g_reports[] and sets g_next_idx to the first
 * empty (erased) slot.  If all five slots contain valid entries the index
 * wraps to 0 so slot 0 (the oldest by convention) is overwritten next.
 * ---------------------------------------------------------------------- */
void bsw_report_load(void)
{
	for (uint8_t i = 0; i < BSW_REPORT_MAX_COUNT; i++)
	{
		g_reports[i] = *BSW_REPORT_SLOT(i); /* struct copy: flash → RAM */
		// printf("Loaded report slot %u: magic=0x%08X address=%p\r\n",
		//        i, g_reports[i].magic, (void *)BSW_REPORT_SLOT(i));
	}

	/* First slot whose magic is not BSW_REPORT_MAGIC is the next target */
	for (uint8_t i = 0; i < BSW_REPORT_MAX_COUNT; i++)
	{
		if (g_reports[i].magic != BSW_REPORT_MAGIC)
		{
			g_next_idx = i;
			return;
		}
	}
	/* All five slots valid — wrap to 0 */
	g_next_idx = 0;
}

/* -------------------------------------------------------------------------
 * bsw_report_init
 *
 * Populates *r with the current system state.  The caller then sets
 * step_flags and outcome as the boot sequence progresses, and calls
 * bsw_report_flush() before any reset or image start.
 * ---------------------------------------------------------------------- */
void bsw_report_init(bsw_report_t* r, bsw_report_type_t type)
{
	r->magic            = BSW_REPORT_MAGIC;
	r->type             = (uint8_t)type;
	r->outcome          = 0;
	r->primary_slot     = (uint8_t)getPrimarySlot();
	r->pad              = 0;
	r->rollback_counter = PROTECTED_BSW_STATE->rollback_counter;
	r->step_flags       = 0;

	const image_header_t* ph = imageGetHeader(getPrimarySlot());
	r->primary_version       = (ph != NULL) ? ph->imageVersion : 0xFFFFU;

	const image_header_t* sh = imageGetHeader(getSecondarySlot());
	r->secondary_version     = (sh != NULL) ? sh->imageVersion : 0xFFFFU;
}

/* -------------------------------------------------------------------------
 * bsw_report_flush
 *
 * Writes *r as the new g_reports[g_next_idx], erases the sector, then
 * re-writes all valid RAM entries back to flash so only one logical report
 * entry is replaced per call.
 * ---------------------------------------------------------------------- */
int16_t bsw_report_flush(const bsw_report_t* r)
{
	g_reports[g_next_idx] = *r;

	// printf("Using slot %u for new report\r\n", g_next_idx);

	// print the reports as they are in memory
	// for (uint8_t i = 0; i < BSW_REPORT_MAX_COUNT; i++)
	// {
	//     const bsw_report_t *rep = &g_reports[i];
	//     printf("Report slot %u: magic=0x%08X type=%u outcome=%u primary_slot=%u rollback_counter=%lu primary_version=%u secondary_version=%u step_flags=0x%08X\r\n",
	//            i, rep->magic, rep->type, rep->outcome, rep->primary_slot, rep->rollback_counter,
	//            rep->primary_version, rep->secondary_version, rep->step_flags);
	// }

	if (HAL_FLASH_Unlock() != HAL_OK)
		return 1;

	int16_t ret = writeFlashSector(REPORT_FLASH_SECTOR, REPORT_FLASH_ADDRESS, (uint32_t*)g_reports,
	                               sizeof(g_reports) / 4);

	HAL_FLASH_Lock();

	if (ret != 0)
		return 2;

	g_next_idx = (uint8_t)((g_next_idx + 1U) % BSW_REPORT_MAX_COUNT);
	return 0;
}

/* -------------------------------------------------------------------------
 * bsw_report_get_by_age
 *
 * age 0 = most recently flushed (g_next_idx - 1)
 * age 4 = oldest / next-to-be-overwritten (g_next_idx)
 * ---------------------------------------------------------------------- */
const bsw_report_t * bsw_report_get_by_age(uint8_t age)
{
	uint8_t idx = (uint8_t)((g_next_idx + BSW_REPORT_MAX_COUNT - 1U - age) % BSW_REPORT_MAX_COUNT);
	return &g_reports[idx];
}
