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

int16_t swapBootWithUpdate();

uint32_t getBootloaderStatus();

int16_t setBootloaderStatus(uint32_t newStatus);

int16_t setupSystemForImageSwap();

int16_t checkSystemForImageSwap();

int16_t setupSystemForNominal();

int16_t checkSystemForNominal();

int16_t setupSystemForUpdate();

int16_t checkSystemForUpdate();

int16_t checkUpdateVersion();

uint32_t getLowestAllowedVersion();

uint32_t getCounterValue();

int16_t setCounterValue(uint32_t newValue);

int32_t updateRollbackCounter();

#endif /* INC_UPDATE_H_ */
