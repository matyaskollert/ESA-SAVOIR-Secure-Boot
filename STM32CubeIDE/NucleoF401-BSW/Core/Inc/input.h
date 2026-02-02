/*
 * input.h
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#ifndef INC_INPUT_H_
#define INC_INPUT_H_

#include "stm32f4xx_hal.h"

int16_t receiveData(UART_HandleTypeDef* uart, uint8_t* receiveBuffer, uint32_t bufferLength);

#endif /* INC_INPUT_H_ */
