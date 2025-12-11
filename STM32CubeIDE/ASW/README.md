# Sample ASW image

This is a sample ASW image which blinks the LED and outputs using the USB port. For proper functionality, the image header along with the `STM32F401CDUX_FLASH_RAM.ld` file is crucial.

The image header along with the section copy table is loaded into FLASH at address `FLASH_HEADER = 0x8010000` and the image itself is loaded at `FLASH = 0x8010400`. Both of these variables and the placements are specified in the linker script. It is important to keep the `FLASH` address aligned to `0x200` for the VTOR table to work as intended.