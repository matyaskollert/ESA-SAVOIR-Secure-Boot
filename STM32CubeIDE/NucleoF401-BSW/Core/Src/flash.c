/*
 * flash.c
 *
 *  Created on: Jan 19, 2026
 *      Author: Matyas
 */


#include "flash.h"
#include <stdio.h>

void eraseFlashSector(uint32_t sector) {
  /* Erase sector */
  FLASH_EraseInitTypeDef eraseInit;
  uint32_t sectorError;

  eraseInit.TypeErase    = FLASH_TYPEERASE_SECTORS;
  eraseInit.Sector       = sector;
  eraseInit.NbSectors    = 1;
  eraseInit.VoltageRange = FLASH_VOLTAGE_RANGE_3;

  if (HAL_FLASHEx_Erase(&eraseInit, &sectorError) != HAL_OK)
  {
	  printf("Flash erase failed\r\n");
	  HAL_FLASH_Lock();
	  while (1);
  }
}

void writeFlashWord(uint32_t address, uint32_t value) {
	/* Program Flash word */
	  if (HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD,
							address,
							value) != HAL_OK)
	  {
		  printf("Flash program failed\r\n");
		  HAL_FLASH_Lock();
		  while (1);
	  }
}


void writeFlashSector(uint32_t sector, uint32_t address, uint32_t* value, uint32_t size) {
  HAL_FLASH_Unlock();

  eraseFlashSector(sector);

  printf("First address: 0x%08lx and first word: 0x%08lx", address, value[0]);

  for (int i = 0; i < size; i++) {
	  writeFlashWord(address + 4*i, value[i]);
  }

  /* Lock Flash */
  HAL_FLASH_Lock();
}
