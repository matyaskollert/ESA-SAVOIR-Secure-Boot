/*
 * update.h
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#ifndef INC_UPDATE_H_
#define INC_UPDATE_H_

#include "stm32f4xx_hal.h"

int16_t receiveUpdateData(UART_HandleTypeDef* uart);

int16_t swapBootWithUpdate(void);

uint32_t getBootloaderStatus(void);

int16_t setBootloaderStatus(uint32_t newStatus);

int16_t setupSystemForImageSwap(void);

int16_t checkSystemForImageSwap(void);

int16_t setupSystemForNominal(void);

int16_t checkSystemForNominal(void);

int16_t setupSystemForUpdate(void);

int16_t checkSystemForUpdate(void);

int16_t checkUpdateVersion(void);

uint32_t getLowestAllowedVersion(void);

uint32_t getCounterValue(void);

int16_t setCounterValue(uint32_t newValue);

int32_t updateRollbackCounter(void);

#endif /* INC_UPDATE_H_ */
