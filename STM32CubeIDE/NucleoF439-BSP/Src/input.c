/*
 * input.c
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#include "input.h"
#include <stdio.h>
#include <string.h>

/* ── DMA circular ring-buffer ──────────────────────────────────────────
 *
 * HAL_UART_Receive_DMA is started once in uart_rx_init() with the DMA
 * stream configured in CIRCULAR mode (see stm32f4xx_hal_msp.c).
 * The DMA controller writes incoming bytes directly into s_rx_dma_buf
 * without any CPU involvement.  The software read index s_rx_read_idx
 * chases the hardware write position derived from the DMA counter.
 *
 * This means bytes arriving during HAL_UART_Transmit busy-loops (e.g.
 * while sending ACKs or DEBUG_LOG packets) are captured by hardware and
 * are never lost.
 *
 * If uart_rx_init() has not been called (e.g. in the ASW which has no
 * DMA configured), every receive call falls back to polled
 * HAL_UART_Receive so the API is backward-compatible.
 * ────────────────────────────────────────────────────────────────────── */

#define UART_RX_DMA_BUF_SIZE  512U

static uint8_t             s_rx_dma_buf[UART_RX_DMA_BUF_SIZE];
static uint32_t            s_rx_read_idx  = 0;
static uint8_t             s_rx_dma_ready = 0;
static UART_HandleTypeDef *s_rx_uart      = NULL;

void uart_rx_init(UART_HandleTypeDef* uart)
{
	s_rx_uart      = uart;
	s_rx_read_idx  = 0;
	s_rx_dma_ready = 1;
	HAL_UART_Receive_DMA(uart, s_rx_dma_buf, UART_RX_DMA_BUF_SIZE);
}

/* Number of bytes currently sitting unread in the ring-buffer. */
static uint32_t rx_bytes_available(void)
{
	uint32_t write_idx = UART_RX_DMA_BUF_SIZE
	                     - __HAL_DMA_GET_COUNTER(s_rx_uart->hdmarx);
	return (write_idx - s_rx_read_idx + UART_RX_DMA_BUF_SIZE)
	       % UART_RX_DMA_BUF_SIZE;
}

/*
 * Read exactly 'len' bytes from the ring-buffer (or via polling fallback).
 *
 * Returns  0  on success
 *         -1  on timeout
 *          1  on HAL error (polling fallback only)
 *
 * Using HAL_MAX_DELAY as timeout_ms effectively waits forever because
 * (HAL_GetTick() - start) would need ~49 days to reach 0xFFFFFFFF.
 */
static int16_t rx_read(UART_HandleTypeDef* uart,
                       uint8_t* dst, uint16_t len, uint32_t timeout_ms)
{
	if (!s_rx_dma_ready || s_rx_uart != uart)
	{
		/* Polling fallback – used by ASW which has no DMA configured */
		HAL_StatusTypeDef ret = HAL_UART_Receive(uart, dst, len, timeout_ms);
		if (ret == HAL_TIMEOUT) return -1;
		if (ret != HAL_OK)      return  1;
		return 0;
	}

	uint32_t start    = HAL_GetTick();
	uint32_t received = 0;

	while (received < len)
	{
		if (rx_bytes_available() > 0)
		{
			dst[received++] = s_rx_dma_buf[s_rx_read_idx];
			s_rx_read_idx = (s_rx_read_idx + 1U) % UART_RX_DMA_BUF_SIZE;
		}
		else if ((HAL_GetTick() - start) >= timeout_ms)
		{
			return -1;
		}
	}
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
