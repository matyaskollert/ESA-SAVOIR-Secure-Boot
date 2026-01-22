# STM32F401 Binary Uploader

A simple GUI application for uploading binary files to STM32F401 boards via UART with automatic CRC header processing.

## Features

- 🎯 Simple and intuitive user interface
- 📁 File browser for selecting .bin files
- 🔐 Automatic CRC calculation and header patching
- 📤 UART upload via COM3
- 📊 Real-time progress tracking
- 📝 Detailed status logging
- 🛡️ Non-destructive - creates new patched file without modifying the original

## Requirements

- Python 3.8 or higher
- PySide6 (Qt for Python)
- pyserial

## Installation

1. Navigate to the uploader directory:
```bash
cd Kollert_2025_2026/uploader
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Launch the application:
```bash
python main.py
```

2. Click the **"Browse..."** button to select your .bin file

3. Click **"Process & Upload to COM3"** to:
   - Process the binary with CRC header
   - Create a patched version (original_patched.bin)
   - Wait for COM3 to become available
   - Upload the file to your STM32F401 board

4. Monitor the progress in the status log

## How It Works

1. **File Selection**: User selects a binary file through the GUI
2. **CRC Processing**: The application processes the binary using the same logic as crc.py but creates a new file instead of modifying the original
3. **Header Patching**: Adds image header with CRC and data size
4. **UART Upload**: Waits for COM3 to become available and uploads the patched binary in 256-byte chunks
5. **Confirmation**: Displays upload progress and completion status

## Configuration

To change the serial port or baud rate, modify the parameters in [main.py](main.py):

```python
# In the process_and_upload method
self.uploader_thread = UploaderThread(
    self.patched_file,
    port='COM3',      # Change this to your COM port
    baudrate=115200   # Change this to your baud rate
)
```

## File Structure

```
uploader/
├── main.py              # Main GUI application
├── crc_processor.py     # CRC calculation and header processing
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## Troubleshooting

### COM Port Not Found
- Ensure your STM32F401 board is connected
- Check Device Manager to confirm the COM port number
- Update the port in the code if it's not COM3

### Upload Fails
- Check that the binary file has the correct header format (magic: 0xABCD)
- Ensure the device is in bootloader/upload mode
- Verify the baud rate matches your device configuration

### Permission Errors
- Close any other applications using the COM port
- Run the application with appropriate permissions

## License

This tool is part of the ESA Kollert 2025/2026 project.
