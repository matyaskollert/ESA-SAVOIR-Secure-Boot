/*
 * update.h
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#ifndef INC_UPDATE_H_
#define INC_UPDATE_H_

#include "stm32f4xx_hal.h"
#include "bsw_report.h"

int16_t receiveUpdateData(UART_HandleTypeDef* uart, bsw_report_t *report);

int16_t swapMainWithUpdate(bsw_report_t *report);

int16_t setProtectedBswState(uint32_t rollback_counter, uint32_t primary_slot);

int16_t setupSystemForImageSwap(void);

int16_t checkSystemForImageSwap(void);

int16_t setupSystemForNominal(void);

int16_t checkSystemForNominal(void);

int16_t setupSystemForUpdate(void);

int16_t checkSystemForUpdate(void);

int16_t checkUpdateValidity(void);

int16_t checkUpdateVersion(void);

uint32_t getLowestAllowedVersion(void);

uint32_t getCounterValue(void);

int16_t setCounterValue(uint32_t newValue);

int16_t checkRollbackCondition(void);

#endif /* INC_UPDATE_H_ */
