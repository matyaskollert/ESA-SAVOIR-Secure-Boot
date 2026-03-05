/*
 * input.c
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#include "input.h"
#include <stdio.h>
#include <string.h>

int16_t receiveData(UART_HandleTypeDef* uart, uint8_t* receiveBuffer, uint32_t bufferLength)
{
	// TODO: NO POLLING
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
	uint8_t ack = 0x06;  // ACK byte (legacy)
	HAL_StatusTypeDef ret = HAL_UART_Transmit(uart, &ack, 1, 1000);
	if (ret != HAL_OK)
	{
		printf("Error sending ACK: %d\r\n", ret);
		return 1;
	}
	return 0;
}

/* ECSS Packet Protocol Functions */

int16_t receivePacketHeader(UART_HandleTypeDef* uart, ECSSPacketHeader* header)
{
	uint8_t buffer[ECSS_HEADER_SIZE];
	
	// TODO: NO POLLING
	// Receive header bytes
	HAL_StatusTypeDef ret = HAL_UART_Receive(uart, buffer, ECSS_HEADER_SIZE, HAL_MAX_DELAY);
	if (ret != HAL_OK)
	{
		printf("Error receiving packet header: %d\r\n", ret);
		return 1;
	}
	
	// Parse header
	if (ecss_parse_header(buffer, header) != 0)
	{
		printf("Error: Invalid packet header checksum\r\n");
		return 2;
	}
	
	return 0;
}

int16_t receivePacketData(UART_HandleTypeDef* uart, uint8_t* buffer, uint16_t length)
{
	if (length == 0)
	{
		return 0;  // No data to receive
	}
	
	// TODO: NO POLLING
	HAL_StatusTypeDef ret = HAL_UART_Receive(uart, buffer, length, HAL_MAX_DELAY);
	if (ret != HAL_OK)
	{
		printf("Error receiving packet data: %d\r\n", ret);
		return 1;
	}
	
//	for (int i = 0; i < length; i++)
//	{
//		printf("%02X", buffer[i]);
//	}
//
//	printf("\r\n");

	return 0;
}

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

int16_t sendAckPacket(UART_HandleTypeDef* uart, uint16_t sequence)
{
	ECSSPacketHeader header;
	ecss_create_header(&header, PKT_ACK, sequence, 0, 0);
	return sendPacket(uart, &header, NULL);
}

int16_t sendNackPacket(UART_HandleTypeDef* uart, uint16_t sequence, uint8_t error_code)
{
	ECSSPacketHeader header;
	uint8_t data = error_code;
	ecss_create_header(&header, PKT_NACK, sequence, 1, 0);
	return sendPacket(uart, &header, &data);
}

int16_t sendDebugPacket(UART_HandleTypeDef* uart, const char* message, uint16_t length)
{
	static uint16_t debug_sequence = 0;
	ECSSPacketHeader header;
	ecss_create_header(&header, PKT_DEBUG_LOG, debug_sequence++, length, 0);
	return sendPacket(uart, &header, (const uint8_t*)message);
}
