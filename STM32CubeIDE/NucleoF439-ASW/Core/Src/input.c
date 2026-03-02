/*
 * input.c
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#include "input.h"
#include <stdio.h>
#include <string.h>

int16_t sendPacket(UART_HandleTypeDef* uart, const ECSSPacketHeader* header, const uint8_t* data)
{
	// Allocate buffer for complete packet (header + data)
	uint16_t total_length = ECSS_HEADER_SIZE + header->data_length;
	uint8_t packet_buffer[ECSS_HEADER_SIZE + 512];  // Max data size we support
	
	if (total_length > sizeof(packet_buffer))
	{
		printf("Error: Packet too large: %u bytes\r\n", total_length);
		return 1;
	}
	
	// Pack header into buffer
	ecss_pack_header(header, packet_buffer);
	
	// Append data if present
	if (header->data_length > 0 && data != NULL)
	{
		memcpy(packet_buffer + ECSS_HEADER_SIZE, data, header->data_length);
	}
	
	// Send complete packet in one transmission
	HAL_StatusTypeDef ret = HAL_UART_Transmit(uart, packet_buffer, total_length, 5000);
	if (ret != HAL_OK)
	{
		printf("Error sending packet: %d\r\n", ret);
		return 2;
	}
	
	return 0;
}

int16_t sendDebugPacket(UART_HandleTypeDef* uart, const char* message, uint16_t length)
{
	static uint16_t debug_sequence = 0;
	ECSSPacketHeader header;
	ecss_create_header(&header, PKT_DEBUG_LOG, debug_sequence++, length, 0);
	return sendPacket(uart, &header, (const uint8_t*)message);
}
