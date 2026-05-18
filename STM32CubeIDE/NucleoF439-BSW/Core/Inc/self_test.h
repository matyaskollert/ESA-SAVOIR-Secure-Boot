/*
 * self_test.h
 *
 * BSW power-on self-test (POST) entry point.
 *
 * Self-tests are run once at startup before the main dispatch loop.
 * Currently the suite is a stub; planned checks include a BSW CRC integrity
 * verification and a confirmation that the BSW flash sectors are protected.
 *
 *  Created on: Feb 9, 2026
 *      Author: Matyas
 */

#ifndef INC_SELF_TEST_H_
#define INC_SELF_TEST_H_

#include "stm32f4xx_hal.h"

/**
 * Run all BSW power-on self-tests.
 *
 * Intended to be called once from main() before entering run_main_loop().
 * Each test prints a diagnostic message via printf on failure.
 *
 * @return  0 if all tests pass, 1 if any test fails.
 */
int16_t performSelfTests(void);

#endif /* INC_SELF_TEST_H_ */
