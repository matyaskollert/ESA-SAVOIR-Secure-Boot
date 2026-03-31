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

void    uart_rx_init(UART_HandleTypeDef* uart);

int16_t receiveData(UART_HandleTypeDef* uart, uint8_t* receiveBuffer, uint32_t bufferLength);
int16_t sendAck(UART_HandleTypeDef* uart);

/* ECSS packet functions */
int16_t receivePacketHeader(UART_HandleTypeDef* uart, ECSSPacketHeader* header);
int16_t receivePacketHeaderWithTimeout(UART_HandleTypeDef* uart, ECSSPacketHeader* header, uint32_t timeout_ms);
int16_t receivePacketData(UART_HandleTypeDef* uart, uint8_t* buffer, uint16_t length);
int16_t sendPacket(UART_HandleTypeDef* uart, const ECSSPacketHeader* header, const uint8_t* data);
int16_t sendAckPacket(UART_HandleTypeDef* uart, uint16_t sequence);
int16_t sendNackPacket(UART_HandleTypeDef* uart, uint16_t sequence, uint8_t error_code);
int16_t sendDebugPacket(UART_HandleTypeDef* uart, const char* message, uint16_t length);

#endif /* INC_INPUT_H_ */
