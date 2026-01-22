/*
 * boot.c
 *
 *  Created on: Dec 15, 2025
 *      Author: Matyas
 */

#include "boot.h"

void boot() {
	imageValidate(IMAGE_SLOT_2);
	imageLoad(IMAGE_SLOT_2);
	imageValidateInRAM(IMAGE_SLOT_2);
	imageStart(IMAGE_SLOT_2);
}
