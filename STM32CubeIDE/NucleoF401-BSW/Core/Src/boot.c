/*
 * boot.c
 *
 *  Created on: Dec 15, 2025
 *      Author: Matyas
 */

#include "boot.h"
#include "image.h"
#include "image_simple.h"

void boot() {
	bootSimple();
}

void bootSections() {
	imageValidate(IMAGE_SLOT_1);
	imageLoad(IMAGE_SLOT_1);
	imageValidateInRAM(IMAGE_SLOT_1);
	imageStart(IMAGE_SLOT_1);
}

void bootSimple() {
	imageSimpleValidate();
	imageSimpleLoad();
	imageSimpleValidateInRAM();
	imageSimpleStart();
}
