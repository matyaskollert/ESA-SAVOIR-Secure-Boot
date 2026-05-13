/*
 * boot.h
 *
 *  Created on: Dec 15, 2025
 *      Author: Matyas
 */

#ifndef INC_BOOT_H_
#define INC_BOOT_H_

#include "stm32f4xx_hal.h"
#include "bsw_report.h"

int16_t boot(bsw_report_t *report);

#endif /* INC_BOOT_H_ */
