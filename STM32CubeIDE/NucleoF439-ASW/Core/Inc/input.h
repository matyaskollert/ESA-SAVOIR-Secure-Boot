/*
 * input.h
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#ifndef INC_INPUT_H_
#define INC_INPUT_H_

#include "stm32f4xx_hal.h"
#include "ecss_packet.h"


int16_t sendPacket(UART_HandleTypeDef* uart, const ECSSPacketHeader* header, const uint8_t* data);
int16_t sendDebugPacket(UART_HandleTypeDef* uart, const char* message, uint16_t length);

#endif /* INC_INPUT_H_ */
