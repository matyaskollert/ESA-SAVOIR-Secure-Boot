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
	int16_t ret;
	ret = imageValidate();
	if (ret != 0)
	{
		return -1;
	}
	ret = imageLoad();
	if (ret != 0)
	{
		return -2;
	}
	ret = imageValidateInRAM();
	if (ret != 0)
	{
		return -3;
	}
	imageStart();
	return 0;
}




