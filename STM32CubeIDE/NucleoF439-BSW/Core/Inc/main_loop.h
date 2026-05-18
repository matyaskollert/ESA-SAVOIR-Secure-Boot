/*
 * main_loop.h
 *
 * BSW main dispatcher: reads the stored BootloaderStatus from flash and
 * either executes the corresponding action immediately (NOMINAL, SWAP) or
 * enters the standby command loop waiting for a ground-station packet.
 *
 *  Created on: Apr 3, 2026
 *      Author: Matyas
 */

#ifndef INC_MAIN_LOOP_H_
#define INC_MAIN_LOOP_H_

#include "stm32f4xx_hal.h"

/**
 * Run the BSW main dispatch loop.
 *
 * Reads the stored BootloaderStatus and acts accordingly:
 *  - NOMINAL      → validate and boot the primary image.
 *  - SWAP         → verify and swap primary/secondary images, then reset.
 *  - STANDBY      → wait up to STANDBY_TIMEOUT_MS for a ground command packet,
 *                   then fall through to NOMINAL on timeout.
 *  - UPDATE       → receive a new image over UART into the secondary slot.
 *  - RESET        → perform a system reset.
 *  - Other        → default to NOMINAL behaviour.
 *
 * This function never returns; it loops until a reset occurs or imageStart()
 * transfers control to the application.
 *
 * @param uart  UART handle used for all ECSS packet communication.
 */
void run_main_loop(UART_HandleTypeDef* uart);

#endif /* INC_MAIN_LOOP_H_ */
