/*
 * input.h
 *
 * UART receive/transmit layer built on top of the ECSS packet protocol.
 *
 * The module owns a single DMA-backed circular receive buffer.  After
 * uart_rx_init() is called all incoming bytes are captured into that buffer
 * transparently; the read functions drain it with an optional timeout.
 *
 * On targets that have not configured DMA (e.g. the ASW), the module falls
 * back to polled HAL_UART_Receive automatically.
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#ifndef INC_INPUT_H_
#define INC_INPUT_H_

#include "stm32f4xx_hal.h"
#include "ecss_packet.h"

/* =========================================================================
 * Initialisation
 * ========================================================================= */

/**
 * Initialise the DMA-backed UART receive ring-buffer for @p uart.
 * Must be called once before any receive function is used.
 * If this function is never called the module falls back to polled reception.
 *
 * @param uart  Handle to the UART peripheral to listen on.
 */
void uart_rx_init(UART_HandleTypeDef* uart);

/* =========================================================================
 * Low-level helpers (legacy / non-ECSS)
 * ========================================================================= */

/**
 * Receive exactly @p bufferLength bytes into @p receiveBuffer, blocking
 * until all bytes arrive (no timeout).
 *
 * @param uart           UART handle.
 * @param receiveBuffer  Destination buffer (at least @p bufferLength bytes).
 * @param bufferLength   Number of bytes to receive.
 * @return               0 on success, 1 on UART error.
 */
int16_t receiveData(UART_HandleTypeDef* uart, uint8_t* receiveBuffer, uint32_t bufferLength);

/**
 * Transmit a single legacy ACK byte (0x06).
 *
 * @param uart  UART handle.
 * @return      0 on success, 1 on transmit error.
 */
int16_t sendAck(UART_HandleTypeDef* uart);

/* =========================================================================
 * ECSS packet I/O
 * ========================================================================= */

/**
 * Receive and parse a 7-byte ECSS packet header, blocking indefinitely.
 * Validates the header checksum; returns an error if it does not match.
 *
 * @param uart    UART handle.
 * @param header  Output: populated on success.
 * @return        0 on success, 1 on receive error, 2 on checksum mismatch.
 */
int16_t receivePacketHeader(UART_HandleTypeDef* uart, ECSSPacketHeader* header);

/**
 * Receive and parse a 7-byte ECSS packet header with a deadline.
 * Returns immediately if no data arrives within @p timeout_ms.
 *
 * @param uart        UART handle.
 * @param header      Output: populated on success.
 * @param timeout_ms  Maximum wait time in milliseconds.
 * @return            0 on success, -1 on timeout, 1 on receive error,
 *                    2 on checksum mismatch.
 */
int16_t receivePacketHeaderWithTimeout(UART_HandleTypeDef* uart, ECSSPacketHeader* header,
                                       uint32_t timeout_ms);

/**
 * Receive exactly @p length payload bytes into @p buffer.
 * Must be called immediately after a successful receivePacketHeader() call.
 *
 * @param uart    UART handle.
 * @param buffer  Destination buffer (at least @p length bytes).
 * @param length  Number of payload bytes to receive (from header.data_length).
 * @return        0 on success, 1 on receive error.
 */
int16_t receivePacketData(UART_HandleTypeDef* uart, uint8_t* buffer, uint16_t length);

/**
 * Serialise and transmit a complete ECSS packet (header + data payload).
 *
 * @param uart    UART handle.
 * @param header  Header to send (checksum is computed internally).
 * @param data    Payload bytes; may be NULL when header.data_length == 0.
 * @return        0 on success, 1 if the packet exceeds the internal buffer,
 *                2 on UART transmit error.
 */
int16_t sendPacket(UART_HandleTypeDef* uart, const ECSSPacketHeader* header, const uint8_t* data);

/**
 * Transmit a PKT_ACK packet echoing @p sequence.
 *
 * @param uart      UART handle.
 * @param sequence  Sequence count copied from the acknowledged packet.
 * @return          0 on success, non-zero on transmit error.
 */
int16_t sendAckPacket(UART_HandleTypeDef* uart, uint16_t sequence);

/**
 * Transmit a PKT_NACK packet with a 1-byte error code payload.
 *
 * @param uart        UART handle.
 * @param sequence    Sequence count copied from the rejected packet.
 * @param error_code  Application-defined error code byte.
 * @return            0 on success, non-zero on transmit error.
 */
int16_t sendNackPacket(UART_HandleTypeDef* uart, uint16_t sequence, uint8_t error_code);

/**
 * Transmit a PKT_DEBUG_LOG packet carrying a human-readable string.
 * An internal auto-incrementing sequence counter is used.
 *
 * @param uart     UART handle.
 * @param message  String to send (need not be NUL-terminated).
 * @param length   Number of bytes in @p message.
 * @return         0 on success, non-zero on transmit error.
 */
int16_t sendDebugPacket(UART_HandleTypeDef* uart, const char* message, uint16_t length);

/**
 * Transmit a PKT_REPORT_DATA packet carrying a serialised BSW boot-event report.
 *
 * @param uart      UART handle.
 * @param sequence  Sequence count for this packet.
 * @param data      Pointer to the raw report bytes.
 * @param length    Number of bytes in @p data.
 * @return          0 on success, non-zero on transmit error.
 */
int16_t sendReportDataPacket(UART_HandleTypeDef* uart, uint16_t sequence, const uint8_t* data,
                             uint16_t length);

#endif /* INC_INPUT_H_ */
