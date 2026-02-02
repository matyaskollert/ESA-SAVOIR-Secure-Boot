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

#endif /* INC_UPDATE_H_ */
