/*
 * input.c
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#include "input.h"
#include <stdio.h>
#include <string.h>

#define UART_RX_DMA_BUF_SIZE  512U

static uint8_t rxBuffer[UART_RX_DMA_BUF_SIZE];
static uint8_t dmaReady = 0;
static uint32_t indx = 0;
static uint32_t write_indx = 0;
static UART_HandleTypeDef* uart = NULL;

void uart_rx_init(UART_HandleTypeDef* uuart)
{
	uart = uuart;
	indx = 0;
	dmaReady = 1;
	HAL_UARTEx_ReceiveToIdle_DMA(uart, rxBuffer, UART_RX_DMA_BUF_SIZE);
	// HAL_UART_Receive_DMA(uart, rxBuffer, UART_RX_DMA_BUF_SIZE);
	// printf("UART RX DMA initialized with buffer size %u\r\n", UART_RX_DMA_BUF_SIZE);
}

void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *huart, uint16_t size)
{
	write_indx = size % UART_RX_DMA_BUF_SIZE;
}

static uint32_t bytes_available(void)
{
    if (write_indx >= indx)
        return write_indx - indx;
    else
        return UART_RX_DMA_BUF_SIZE - indx + write_indx;
}


static int16_t rx_read(UART_HandleTypeDef* uuart,
                       uint8_t* dst, uint16_t len, uint32_t timeout_ms)
{
	if (!dmaReady || uart != uuart)
	{
		// printf("DMA not ready or wrong UART instance, falling back to polling\r\n");
		/* Polling fallback – used by ASW which has no DMA configured */
		HAL_StatusTypeDef ret = HAL_UART_Receive(uart, dst, len, timeout_ms);
		if (ret == HAL_TIMEOUT) return -1;
		if (ret != HAL_OK)      return  1;
		return 0;
	}

	uint32_t start = HAL_GetTick();

	while (bytes_available() < len)
	{
		if ((HAL_GetTick() - start) >= timeout_ms)
		{
			return -1;  // Timeout
		}
	}

	for (uint16_t i = 0; i < len; i++)
	{
		dst[i] = rxBuffer[(indx + i) % UART_RX_DMA_BUF_SIZE];
	}
	indx = (indx + len) % UART_RX_DMA_BUF_SIZE;

	return 0;
}

int16_t receiveData(UART_HandleTypeDef* uart, uint8_t* receiveBuffer, uint32_t bufferLength)
{
	if (rx_read(uart, receiveBuffer, (uint16_t)bufferLength, HAL_MAX_DELAY) != 0)
	{
		printf("Error getting data from UART\r\n");
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

/* ── ECSS Packet Protocol Functions ─────────────────────────────────── */

int16_t receivePacketHeader(UART_HandleTypeDef* uart, ECSSPacketHeader* header)
{
	uint8_t buffer[ECSS_HEADER_SIZE];
	if (rx_read(uart, buffer, ECSS_HEADER_SIZE, HAL_MAX_DELAY) != 0)
	{
		printf("Error receiving packet header\r\n");
		return 1;
	}

	if (ecss_parse_header(buffer, header) != 0)
	{
		printf("Error: Invalid packet header checksum\r\n");
		return 2;
	}

	return 0;
}

int16_t receivePacketHeaderWithTimeout(UART_HandleTypeDef* uart, ECSSPacketHeader* header, uint32_t timeout_ms)
{
	uint8_t buffer[ECSS_HEADER_SIZE];
	int16_t ret = rx_read(uart, buffer, ECSS_HEADER_SIZE, timeout_ms);
	if (ret == -1)
	{
		return -1;  // No data received within timeout
	}
	if (ret != 0)
	{
		printf("Error receiving packet header\r\n");
		return 1;
	}

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
		return 0;
	}

	if (rx_read(uart, buffer, length, HAL_MAX_DELAY) != 0)
	{
		printf("Error receiving packet data\r\n");
		return 1;
	}

	return 0;
}

int16_t sendPacket(UART_HandleTypeDef* uart, const ECSSPacketHeader* header, const uint8_t* data)
{
	uint16_t total_length = ECSS_HEADER_SIZE + header->data_length;
	uint8_t packet_buffer[ECSS_HEADER_SIZE + 512];  // Max data size we support

	if (total_length > sizeof(packet_buffer))
	{
		printf("Error: Packet too large: %u bytes\r\n", total_length);
		return 1;
	}

	ecss_pack_header(header, packet_buffer);

	if (header->data_length > 0 && data != NULL)
	{
		memcpy(packet_buffer + ECSS_HEADER_SIZE, data, header->data_length);
	}

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
