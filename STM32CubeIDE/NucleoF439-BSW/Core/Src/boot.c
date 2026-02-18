/*
 * boot.c
 *
 *  Created on: Dec 15, 2025
 *      Author: Matyas
 */

#include "image.h"
#include "boot.h"


int16_t boot()
{
	if (imageValidate() != 0)
	{
		return 1;
	}
	if (imageLoad() != 0)
	{
		return 2;
	}
	if (imageValidateInRAM() != 0)
	{
		return 3;
	}
	imageStart();
	return 0;
}




