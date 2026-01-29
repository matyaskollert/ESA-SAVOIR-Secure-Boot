/*
 * boot.c
 *
 *  Created on: Dec 15, 2025
 *      Author: Matyas
 */

#include "boot.h"
#include "image_simple.h"


void boot() {
	imageSimpleValidate();
	imageSimpleLoad();
	imageSimpleValidateInRAM();
	imageSimpleStart();
}




