/*
 * report.h
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#ifndef INC_REPORT_H_
#define INC_REPORT_H_

#include "stm32f4xx_hal.h"

void printImageHeaders(void);

typedef enum {ERROR_REPORT, INFO_REPORT} ReportLevel;

int16_t createBootReport(ReportLevel level);

#endif /* INC_REPORT_H_ */
