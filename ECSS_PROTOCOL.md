# ECSS-Inspired Packet Protocol

This project implements a simplified ECSS-inspired packet protocol for uploading firmware to STM32F4 microcontrollers via UART. The protocol is based on ECSS-E-ST-70-41C telemetry and telecommand packet structures, adapted for a proof-of-concept implementation.

## Protocol Overview

### Packet Structure

Each packet consists of:
1. **Primary Header** (7 bytes) - Fixed header with metadata
2. **Data Field** (variable) - Payload data

### Primary Header Format

```
Byte 0: Version/Type/Flags
  - Bits 7-5: Packet Version Number (3 bits) = 001 (version 1)
  - Bit 4: Packet Type (1 bit)
    - 1 = Telecommand (uplink from host to board)
    - 0 = Telemetry (downlink from board to host)
  - Bits 3-0: Reserved (set to 0)

Byte 1: Service Type
  - 0x01 = START_UPLOAD
  - 0x02 = DATA_CHUNK
  - 0x03 = END_UPLOAD
  - 0x06 = ACK (acknowledgment)
  - 0x15 = NACK (negative acknowledgment)

Bytes 2-3: Sequence Count (big-endian, 16-bit)
  - Packet sequence number (0-65535)

Bytes 4-5: Data Length (big-endian, 16-bit)
  - Length of data field in bytes (0-65535)

Byte 6: Header Checksum
  - XOR checksum of bytes 0-5
```

### Data Field

Variable-length payload data. The length is specified in the header's Data Length field.

## Upload Protocol Sequence

### 1. START_UPLOAD Phase

**Host → Board:**
- Service Type: `START_UPLOAD (0x01)`
- Sequence: 0
- Data Length: 4 bytes
- Data: Total file size (32-bit, little-endian)

**Board → Host:**
- Service Type: `ACK (0x06)`
- Sequence: 0
- Data Length: 0

### 2. DATA_CHUNK Phase

**Host → Board:** (repeated for each chunk)
- Service Type: `DATA_CHUNK (0x02)`
- Sequence: Incrementing (1, 2, 3, ...)
- Data Length: Chunk size (typically 256 bytes)
- Data: Binary chunk data

**Board → Host:** (after each chunk)
- Service Type: `ACK (0x06)`
- Sequence: Same as received chunk
- Data Length: 0

### 3. END_UPLOAD Phase

**Host → Board:**
- Service Type: `END_UPLOAD (0x03)`
- Sequence: Last sequence + 1
- Data Length: 0
- Data: None

**Board → Host:**
- Service Type: `ACK (0x06)`
- Sequence: Same as received
- Data Length: 0

### Error Handling

If the board detects an error, it sends:
- Service Type: `NACK (0x15)`
- Sequence: Related packet sequence
- Data Length: 1 byte
- Data: Error code

## Implementation Files

### Python (Host Side)

- `uploader/ecss_packet.py` - ECSS packet implementation
  - `ECSSPacket` class for packing/unpacking packets
  - Helper functions: `create_start_packet()`, `create_data_packet()`, `create_end_packet()`
  - `PacketType` enum for service types

- `uploader/main.py` - GUI application with ECSS protocol support
  - `wait_for_ack_packet()` - Parse and validate ACK/NACK packets
  - `run()` - Upload sequence using ECSS packets

### Firmware (STM32 Side)

- `Core/Inc/ecss_packet.h` - C header for ECSS protocol
  - `ECSSPacketHeader` structure
  - Function prototypes for packet operations

- `Core/Src/ecss_packet.c` - C implementation
  - `ecss_parse_header()` - Parse received packet header
  - `ecss_create_header()` - Create packet header for transmission
  - `ecss_calculate_header_checksum()` - Checksum calculation

- `Core/Src/input.c` - UART packet I/O functions
  - `receivePacketHeader()` - Receive and validate packet header
  - `receivePacketData()` - Receive packet data field
  - `sendAckPacket()` - Send ACK packet
  - `sendNackPacket()` - Send NACK packet

- `Core/Src/update.c` - Firmware update handler
  - `receiveUpdateData()` - Main upload handler using ECSS protocol

## Example Packet

**START_UPLOAD Packet (Total size: 10240 bytes)**

```
Header (7 bytes):
  0x30          - Version 1, Type=Telecommand
  0x01          - Service Type: START_UPLOAD
  0x00 0x00     - Sequence: 0
  0x00 0x04     - Data Length: 4 bytes
  0x35          - Checksum

Data (4 bytes):
  0x00 0x28 0x00 0x00 - Size: 10240 (little-endian)
```

**ACK Packet**

```
Header (7 bytes):
  0x20          - Version 1, Type=Telemetry
  0x06          - Service Type: ACK
  0x00 0x00     - Sequence: 0
  0x00 0x00     - Data Length: 0
  0x26          - Checksum
```

## Advantages Over Simple Protocol

1. **Structured Headers** - Well-defined packet format similar to space standards
2. **Error Detection** - Header checksum validates packet integrity
3. **Sequence Tracking** - Detect lost or out-of-order packets
4. **Extensible** - Easy to add new service types
5. **Standards-Based** - Follows ECSS concepts for professional development
6. **ACK/NACK Support** - Explicit acknowledgment and error reporting

## Notes

- This is a **simplified** ECSS implementation for proof-of-concept
- Full ECSS compliance includes additional features:
  - CRC-16 or CRC-32 for data integrity
  - Secondary headers for timestamps and source IDs
  - Application ID (APID) for multiple services
  - More sophisticated error correction
- Designed for single-point UART communication (no packet routing)
- Byte order: Big-endian for header fields (network byte order)
- Data payloads can use application-specific byte order

## Future Enhancements

- [ ] Add CRC-16 for data field integrity
- [ ] Implement secondary header with timestamps
- [ ] Add multiple service types for diagnostics
- [ ] Implement packet retransmission on NACK
- [ ] Add flow control mechanisms
- [ ] Support for larger transfers with fragmentation

## References

- ECSS-E-ST-70-41C: Telemetry and telecommand packet utilization
- STM32F4 HAL UART documentation
- PySide6 serial communication
