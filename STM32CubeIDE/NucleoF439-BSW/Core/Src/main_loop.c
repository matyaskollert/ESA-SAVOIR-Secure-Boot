/*
 * main_loop.c
 *
 *  Created on: Apr 3, 2026
 *      Author: Matyas
 */

#include "main_loop.h"
#include <stdio.h>
#include "boot.h"
#include "input.h"
#include "update.h"
#include "report.h"
#include "self_test.h"
#include "flash.h"
#include "bsw_report.h"

#define STANDBY_TIMEOUT_MS  15000

/* Map a received command byte to a BootloaderStatus */
static BootloaderStatus commandToStatus(uint8_t cmd)
{
	switch (cmd)
	{
		case '1': return BOOTLOADER_STATUS_NOMINAL;
		case '2': return BOOTLOADER_STATUS_UPDATE;
		case '3': return BOOTLOADER_STATUS_SWAP;
		case '4': return BOOTLOADER_STATUS_CHECK_VERSIONS;
		case '5': return BOOTLOADER_STATUS_RESET;
		case '6': return BOOTLOADER_STATUS_STANDBY;   /* no-op */
		case '7': return BOOTLOADER_STATUS_REPORT;
		default:  return BOOTLOADER_STATUS_UNKNOWN;
	}
}

static void handleRollback(UART_HandleTypeDef* uart); /* forward declaration */

/* Handle a swap command: verify preconditions, perform swap, reset */
static void handleSwap(UART_HandleTypeDef* uart, uint16_t sequence_count)
{
	if (checkSystemForImageSwap() != 0)
	{
		printf("Setting up system for image swap\r\n");
		sendNackPacket(uart, sequence_count, 12);
		setupSystemForImageSwap();;
		NVIC_SystemReset();
	}
	if (checkUpdateVersion() != 0)
	{
		sendNackPacket(uart, sequence_count, 9);
		return;
	}
	if (checkUpdateValidity() != 0)
	{
		sendNackPacket(uart, sequence_count, 9);
		return;
	}

	sendAckPacket(uart, sequence_count);

	if (swapBootWithUpdate() != 0)
	{
		printf("Swapping images failed\r\n");
		return;
	}
	if (setupSystemForNominal() != 0)
	{
		printf("Setting up system for nominal mode failed\r\n");
		return;
	}
	NVIC_SystemReset();
}

/*
 * Standby command loop.
 * If initial_status is not BOOTLOADER_STATUS_STANDBY, it is dispatched immediately
 * using initial_seq as the sequence count; otherwise the loop waits for a command.
 */
static void standbyLoop(UART_HandleTypeDef* uart, BootloaderStatus initial_status, uint16_t initial_seq)
{
	BootloaderStatus status = initial_status;
	uint16_t seq = initial_seq;
	uint8_t use_initial = (status != BOOTLOADER_STATUS_STANDBY);

	while (1)
	{
		if (!use_initial)
		{
			printf("Entering standby mode. Send: 1=boot, 2=update, 3=swap, 4=check versions, 5=reset\r\n");
			ECSSPacketHeader header;
			if (receivePacketHeader(uart, &header) != 0)
			{
				printf("Error receiving command header, retrying\r\n");
				continue;
			}
			uint8_t data = 0;
			if (header.data_length == 1)
			{
				if (receivePacketData(uart, &data, 1) != 0)
				{
					printf("Error receiving command data\r\n");
					continue;
				}
			}
			seq = header.sequence_count;
			status = commandToStatus(data);
		}
		use_initial = 0;

		switch (status)
		{
			case BOOTLOADER_STATUS_NOMINAL:
				/* Boot */
				if (checkSystemForNominal() != 0)
				{
					printf("System not configured for nominal mode\r\n");
					sendNackPacket(uart, seq, 11);
					setupSystemForNominal();
					NVIC_SystemReset();
				}
				sendAckPacket(uart, seq);

				int16_t ret = boot();
				if (ret != 0)
					printf("Booting image failed: %d\r\n", ret);
				break;

			case BOOTLOADER_STATUS_UPDATE:
				/* Update */
				if (checkSystemForUpdate() != 0)
				{
					printf("System not configured for update\r\n");
					sendNackPacket(uart, seq, 10);
					setupSystemForUpdate();
					NVIC_SystemReset();
				}
				if (sendAckPacket(uart, seq) != 0)
				{
					printf("Error sending ACK for command\r\n");
					break;
				}

				if (receiveUpdateData(uart) != 0)
				{
					printf("Receiving image failed\r\n");
					break;
				}

				if (setupSystemForImageSwap() != 0)
				{
					printf("Setting up system for image swap failed\r\n");
					break;
				}
				NVIC_SystemReset();

			case BOOTLOADER_STATUS_SWAP:
				/* Swap */
				handleSwap(uart, seq);
				break;

			case BOOTLOADER_STATUS_CHECK_VERSIONS:
				/* Check image versions */
				if (sendAckPacket(uart, seq) != 0)
					printf("Error sending ACK for command\r\n");
				printImageHeaders();
				break;

			case BOOTLOADER_STATUS_RESET:
				/* Reset */
				if (sendAckPacket(uart, seq) != 0)
					printf("Error sending ACK\r\n");
				NVIC_SystemReset();

			case BOOTLOADER_STATUS_ROLLBACK:
				/* Rollback */
				handleRollback(uart);
				break;

			case BOOTLOADER_STATUS_REPORT:
				/* Return all 5 stored boot-event reports, newest first */
				sendAckPacket(uart, seq);
				for (uint8_t age = 0; age < BSW_REPORT_MAX_COUNT; age++)
				{
					const bsw_report_t *rep = bsw_report_get_by_age(age);
					sendReportDataPacket(uart, (uint16_t)age,
					                     (const uint8_t *)rep,
					                     (uint16_t)sizeof(bsw_report_t));
				}
				break;

			case BOOTLOADER_STATUS_STANDBY:
				/* No-op (command '6') */
				if (sendAckPacket(uart, seq) != 0)
					printf("Error sending ACK\r\n");
				break;

			default:
				printf("Unknown command\r\n");
				sendNackPacket(uart, seq, 15);
				break;
		}
	}
}

/*
 * Check the rollback condition and act:
 *   - Rollback possible: configure for swap (sets status=123, re-arms OBs) and reset.
 *     The next boot will see status=123 and take the standard handleSwap path.
 *   - Rollback not possible: set status to STANDBY and enter the command loop.
 */
static void handleRollback(UART_HandleTypeDef* uart)
{
	printf("Boot failed - evaluating rollback\r\n");
	if (checkRollbackCondition() == 0)
	{
		printf("Initiating rollback swap\r\n");
		if (setupSystemForImageSwap() != 0)
		{
			printf("Could not configure system for rollback\r\n");
			standbyLoop(uart, BOOTLOADER_STATUS_STANDBY, 0);
			return;
		}
		/* OB change takes effect after reset; on next boot status=123 → handleSwap */
		NVIC_SystemReset();
	}
	else
	{
		printf("Rollback not applicable - entering standby\r\n");
		standbyLoop(uart, BOOTLOADER_STATUS_STANDBY, 0);
		return;
	}
}

void run_main_loop(UART_HandleTypeDef* uart)
{
    bsw_report_load();

    printf("Performing self-tests\r\n");

  	int16_t testResult = performSelfTests();
	if (testResult != 0)
	{
		printf("System is in an invalid state\r\n");
		NVIC_SystemReset();
	}

	uart_rx_init(uart);

	BootloaderStatus status = getBootloaderStatus();
	printf("Waiting %d ms for manual input... (current status: 0x%02X)\r\n", STANDBY_TIMEOUT_MS, (unsigned int)status);
	printImageHeaders();

	ECSSPacketHeader cmd_header;
	int8_t inputReceived = receivePacketHeaderWithTimeout(uart, &cmd_header, STANDBY_TIMEOUT_MS);

	uint16_t effective_seq = 0;

	if (inputReceived == 0)
	{
		/* Fully receive the packet and map the command byte to a BootloaderStatus */
		uint8_t data = 0;
		if (cmd_header.data_length == 1)
		{
			if (receivePacketData(uart, &data, 1) != 0)
			{
				printf("Error receiving command data\r\n");
				NVIC_SystemReset();
			}
		}

		if (data == '6')
		{
			/* Skip: ACK and defer to stored status */
			if (sendAckPacket(uart, cmd_header.sequence_count) != 0)
				printf("Error sending ACK\r\n");
			printf("Skipping timeout, continuing with status: 0x%02X\r\n", (unsigned int)status);
			inputReceived = 1;
		}
		else
		{
			status = commandToStatus(data);
			effective_seq = cmd_header.sequence_count;
		}
	}

	if (inputReceived != 0)
	{
		/* No user command (or skipped) - map stored status to effective command */
		status = (status == BOOTLOADER_STATUS_BOOT_ATTEMPTED)
		                ? BOOTLOADER_STATUS_ROLLBACK
		                : status;
	}

	printf("Status: 0x%02X\r\n", (unsigned int)status);

	if (status == BOOTLOADER_STATUS_NOMINAL)
	{
		/* ── NOMINAL ── */
		printf("Nominal mode - booting application\r\n");
		if (checkSystemForNominal() != 0)
		{
			printf("System not configured for nominal mode\r\n");
			if (inputReceived == 0)
				sendNackPacket(uart, effective_seq, 11);
			setupSystemForNominal();
			NVIC_SystemReset();
		}
		if (sendAckPacket(uart, effective_seq) != 0)
			printf("Error sending ACK\r\n");
		int16_t ret = boot();
		if (ret != 0)
		{
			printf("Booting image failed: %d\r\n", ret);
			handleRollback(uart);
		}
	}
	else
	{
		/* ── STANDBY ── */
		standbyLoop(uart, status, effective_seq);
	}
}
