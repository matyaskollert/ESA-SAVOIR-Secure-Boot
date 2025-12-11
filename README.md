# Secure Boot Proof of Concept repository

## Installation

- Copy this gitlab repository
- Upload the whole `STM32CubeIDE` directory as projects into STM32CubeIDE

## Build

- Connect STM32F401CD using the external ST-Link
- Run BSW (right click and run)
- Run ASW (right click and run)

## Build with CRC
- Connect STM32F401CD using the external ST-Link
- Run BSW (right click and run)
- Build ASW (right click and build)
- Locate `.bin` file in the Debug directory
- Run `py crc.py X` where X is the location of the `.bin` file
- Upload updated image to the device using STM32CubeProgrammer with the base address taken from `FLASH` in the ASW `FLASH_RAM` linker script

## Run

- Connect the internal USB-C port to your PC
- Open a Serial Monitor (baud rate 9600) to receive status updates
- You can use the NRST button to restart the BSW/ASW without disconnecting from the PC
