/*
 * self_test.c
 *
 *  Created on: Feb 9, 2026
 *      Author: Matyas
 */


#include "self_test.h"
#include "option_bytes.h"

int16_t performSelfTests()
{
	int16_t ret = performOBSelfTest(0);
	if (ret != 0) {
		return ret;
	}
	return 0;
}
