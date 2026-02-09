/*
 * input.c
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#include "input.h"
#include <stdio.h>

int16_t receiveData(UART_HandleTypeDef* uart, uint8_t* receiveBuffer, uint32_t bufferLength)
{
	HAL_StatusTypeDef ret = HAL_UART_Receive(uart, receiveBuffer, bufferLength, HAL_MAX_DELAY);
	if (ret != HAL_OK)
	{
		printf("Error getting data from UART: %d\r\n", ret);
		return 1;
	}
	return 0;
}

int16_t sendAck(UART_HandleTypeDef* uart)
{
	uint8_t ack = 0x06;  // ACK byte
	HAL_StatusTypeDef ret = HAL_UART_Transmit(uart, &ack, 1, 1000);
	if (ret != HAL_OK)
	{
		printf("Error sending ACK: %d\r\n", ret);
		return 1;
	}
	return 0;
}
