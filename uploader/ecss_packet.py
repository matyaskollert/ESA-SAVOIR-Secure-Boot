"""
ECSS-inspired packet protocol implementation
Simplified version for proof of concept
"""
import struct
from enum import IntEnum
from typing import Optional


class PacketType(IntEnum):
    """ECSS-inspired packet service types"""
    START_UPLOAD = 0x01
    DATA_CHUNK = 0x02
    END_UPLOAD = 0x03
    DEBUG_LOG = 0x04
    REPORT_DATA = 0x05
    ACK = 0x06
    NACK = 0x15


class ECSSPacket:
    """
    ECSS-inspired packet structure
    
    Primary Header (7 bytes):
    - Version/Type/Flags (1 byte): Version(3 bits) | Type(1 bit) | Reserved(4 bits)
    - Service Type (1 byte): Command type (START, DATA, END, ACK, NACK)
    - Sequence Count (2 bytes, big-endian): Packet sequence number
    - Data Length (2 bytes, big-endian): Length of data field
    - Header Checksum (1 byte): XOR checksum of first 6 header bytes
    
    Data Field (variable):
    - Payload data
    """
    
    HEADER_SIZE = 7
    VERSION = 0b001  # 3 bits - version 1
    TYPE_TELECOMMAND = 1  # Uplink from ground to spacecraft
    TYPE_TELEMETRY = 0    # Downlink from spacecraft to ground
    
    def __init__(self, service_type: PacketType, sequence_count: int, data: bytes = b'', is_telecommand: bool = True, data_length: Optional[int] = None):
        """
        Initialize ECSS packet
        
        Args:
            service_type: Type of service (START, DATA, END, ACK, NACK)
            sequence_count: Packet sequence number (0-65535)
            data: Payload data
            is_telecommand: True for uplink (ground->board), False for downlink (board->ground)
            data_length: Optional data length (used when unpacking header only)
        """
        self.service_type = service_type
        self.sequence_count = sequence_count & 0xFFFF  # 16-bit
        self.data = data
        self.is_telecommand = is_telecommand
        # Store data_length from header if provided, otherwise compute from data
        self.data_length = data_length if data_length is not None else len(data)
    
    def _calculate_header_checksum(self, header_bytes: bytes) -> int:
        """Calculate XOR checksum of header (first 6 bytes)"""
        checksum = 0
        for byte in header_bytes[:6]:
            checksum ^= byte
        return checksum
    
    def pack_header(self) -> bytes:
        """
        Pack only the header bytes for transmission
        
        Returns:
            Header as bytes (7 bytes)
        """
        # Construct version/type/flags byte
        version_type_flags = (self.VERSION << 5)
        version_type_flags |= ((1 if self.is_telecommand else 0) << 4)
        
        # Pack header without checksum first
        header_no_crc = struct.pack(
            '>BBHH',  # big-endian: byte, byte, short, short
            version_type_flags,
            self.service_type,
            self.sequence_count,
            len(self.data)
        )
        
        # Calculate checksum
        checksum = self._calculate_header_checksum(header_no_crc)
        
        # Complete header with checksum
        return header_no_crc + bytes([checksum])
    
    def pack(self) -> bytes:
        """
        Pack packet into bytes for transmission
        
        Returns:
            Complete packet as bytes (header + data)
        """
        # Return header + data
        return self.pack_header() + self.data
    
    @classmethod
    def unpack_header(cls, header_bytes: bytes) -> 'ECSSPacket':
        """
        Unpack only the header bytes into an ECSSPacket (without data)
        Used when reading header first to determine data length
        
        Args:
            header_bytes: Header bytes (must be exactly HEADER_SIZE bytes)
            
        Returns:
            ECSSPacket object with data_length set but empty data
            
        Raises:
            ValueError: If header is invalid
        """
        if len(header_bytes) != cls.HEADER_SIZE:
            raise ValueError(f"Header must be exactly {cls.HEADER_SIZE} bytes, got {len(header_bytes)}")
        
        # Unpack header
        version_type_flags, service_type, sequence_count, data_length, checksum = struct.unpack(
            '>BBHHB',
            header_bytes
        )
        
        # Verify checksum
        calculated_checksum = 0
        for byte in header_bytes[:6]:
            calculated_checksum ^= byte
        
        if checksum != calculated_checksum:
            raise ValueError(f"Header checksum mismatch: {checksum} != {calculated_checksum}")
        
        # Extract version and type
        version = (version_type_flags >> 5) & 0b111
        is_telecommand = bool((version_type_flags >> 4) & 1)
        
        # Return packet object with data_length set but no data yet
        return cls(
            service_type=PacketType(service_type),
            sequence_count=sequence_count,
            data=b'',  # Empty data - caller will read it separately
            is_telecommand=is_telecommand,
            data_length=data_length
        )
    
    @classmethod
    def unpack(cls, packet_bytes: bytes) -> 'ECSSPacket':
        """
        Unpack bytes into ECSSPacket
        
        Args:
            packet_bytes: Raw packet bytes
            
        Returns:
            ECSSPacket object
            
        Raises:
            ValueError: If packet is invalid
        """
        if len(packet_bytes) < cls.HEADER_SIZE:
            raise ValueError(f"Packet too short: {len(packet_bytes)} < {cls.HEADER_SIZE}")
        
        # Unpack header
        version_type_flags, service_type, sequence_count, data_length, checksum = struct.unpack(
            '>BBHHB',
            packet_bytes[:cls.HEADER_SIZE]
        )

        print(f"Unpacking packet: version/type/flags={version_type_flags:08b}, "
              f"service={service_type}, seq={sequence_count}, data_len={data_length}, checksum={checksum:02X}")
        
        data = packet_bytes[cls.HEADER_SIZE:cls.HEADER_SIZE + data_length]
        print(f"Packet data extracted: {data.hex()} (length={len(data)})")
        
        # Verify checksum
        calculated_checksum = 0
        for byte in packet_bytes[:6]:
            calculated_checksum ^= byte
        
        if checksum != calculated_checksum:
            raise ValueError(f"Header checksum mismatch: {checksum} != {calculated_checksum}")
        
        # Extract version and type
        version = (version_type_flags >> 5) & 0b111
        is_telecommand = bool((version_type_flags >> 4) & 1)
        
        # Extract data
        data_start = cls.HEADER_SIZE
        data_end = data_start + data_length
        
        if len(packet_bytes) < data_end:
            raise ValueError(f"Packet data incomplete: expected {data_length} bytes, got {len(packet_bytes) - cls.HEADER_SIZE}")
        
        data = packet_bytes[data_start:data_end]
        
        return cls(
            service_type=PacketType(service_type),
            sequence_count=sequence_count,
            data=data,
            is_telecommand=is_telecommand
        )
    
    def __repr__(self):
        return (f"ECSSPacket(service={PacketType(self.service_type).name}, "
                f"seq={self.sequence_count}, data_len={len(self.data)}, "
                f"tc={self.is_telecommand})")


def create_start_packet(sequence: int, total_size: int) -> ECSSPacket:
    """Create START_UPLOAD packet with total data size as payload"""
    data = struct.pack('<I', total_size)  # 4 bytes, little-endian for compatibility
    return ECSSPacket(PacketType.START_UPLOAD, sequence, data)


def create_data_packet(sequence: int, chunk_data: bytes) -> ECSSPacket:
    """Create DATA_CHUNK packet with chunk as payload"""
    return ECSSPacket(PacketType.DATA_CHUNK, sequence, chunk_data)


def create_end_packet(sequence: int) -> ECSSPacket:
    """Create END_UPLOAD packet (no payload)"""
    return ECSSPacket(PacketType.END_UPLOAD, sequence, b'')


def create_ack_packet(sequence: int) -> ECSSPacket:
    """Create ACK packet from firmware"""
    return ECSSPacket(PacketType.ACK, sequence, b'', is_telecommand=False)


def create_nack_packet(sequence: int, error_code: int = 0) -> ECSSPacket:
    """Create NACK packet from firmware"""
    data = bytes([error_code]) if error_code else b''
    return ECSSPacket(PacketType.NACK, sequence, data, is_telecommand=False)


def create_command_packet(sequence: int, command: str) -> ECSSPacket:
    """Create DEBUG_LOG telecommand packet with command text"""
    data = command.encode('utf-8')
    return ECSSPacket(PacketType.DEBUG_LOG, sequence, data, is_telecommand=True)
