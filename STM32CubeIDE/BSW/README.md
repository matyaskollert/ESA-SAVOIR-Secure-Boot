# Secure Bootloader PoC

This is a Secure Bootloader PoC implementation using the STM32CubeIDE along with its built-in HAL.

## Functionality

- Load ASW image header
- Check ASW image header magic number
- Check ASW image CRC (per section)
- Load ASW image into RAM
- CRC after loading into RAM (per section)
- Run ASW image
- Supports 2 ASW images which can be manually triggered by choosing `IMAGE_SLOT_1` or `IMAGE_SLOT_2` in the `main.c` file

## TODO

- Digital Signatures
- and much more