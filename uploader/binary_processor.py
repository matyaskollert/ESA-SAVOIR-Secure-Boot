"""
Binary processor module for adding header with signature and CRC to binary files.
Binary structure (created by this module):
- First 5120 bytes: Header partition
  - 4 bytes: CRC (calculated over header + image data)
  - 2 bytes: magic (0xABCD)
  - 2 bytes: version
  - 4 bytes: image size
  - 4096 bytes: Digital signature (padded to 4096 bytes)
  - Remaining bytes: padding
- From byte 5120 onwards: Image data

Processing order:
1. Read the binary file (no header present)
2. Calculate image signature (if signing enabled)
3. Build header partition with signature
4. Calculate CRC over entire header partition + image data
5. Place CRC at the beginning of header
"""
import struct
import binascii
from pathlib import Path
from signature_base import SignatureAlgorithm


def process_binary(input_bin_filename, signature_algo: SignatureAlgorithm, output_bin_filename=None, image_version=1) -> str:
    """
    Process binary file and add header with CRC and signature.
    Input file contains only the image data (no header).
    
    Args:
        input_bin_filename: Path to input binary file (raw image data without header)
        signature_algo: Signature algorithm instance
        output_bin_filename: Path to output binary file (optional, defaults to input_with_header.bin)
        image_version: Version number to use (default: 1)
    
    Returns:
        Path to the output file
    """
    HEADER_PARTITION_SIZE = 5 * 1024  # Total header partition size (5KB)
    SIGNATURE_SIZE = 4096  # Digital signature size (padded)
    HEADER_SIZE = 12  # Actual header size (crc:4, magic:2, version:2, size:4)
    IMAGE_HDR_MAGIC = 0xABCD

    # Generate output filename if not provided
    if output_bin_filename is None:
        input_path = Path(input_bin_filename)
        output_bin_filename = str(input_path.parent / f"{input_path.stem}_with_header{input_path.suffix}")

    # Read the binary file (only image data, no header)
    with open(input_bin_filename, "rb") as f:
        image_data = f.read()
    
    image_size = len(image_data)
    
    print(f"Input binary file: {input_bin_filename}")
    print(f"Image size: {image_size} bytes")
    print(f"Using image version: {image_version}")
    
    # Generate signature if signature algorithm is provided
    signature = b'\x00' * SIGNATURE_SIZE  # Default: no signature (zeros)
    real_signature_length = 0  # Real signature length before padding
    
    print(f"Generating signature using {signature_algo.get_algorithm_name()}...")
    
    # Build data for signing: header (without CRC) + image data
    # Header structure for signing: magic(2) + version(2) + size(4)
    sign_data = struct.pack("<HH", IMAGE_HDR_MAGIC, image_version)  # magic + version
    sign_data += struct.pack("<L", image_size)  # image size
    sign_data += b'\x00' * (HEADER_PARTITION_SIZE - 12)
    sign_data += image_data  # image data

    print(f"Data length for signing: {len(sign_data)} bytes")
    
    # Get the raw signature (not padded)
    raw_signature = signature_algo.sign(sign_data)
    real_signature_length = len(raw_signature)
    print(f"Signature generated: {real_signature_length} bytes (raw)")
    
    # Verify signature size doesn't exceed maximum
    if real_signature_length > SIGNATURE_SIZE:
        raise ValueError(f"Signature size {real_signature_length} exceeds maximum {SIGNATURE_SIZE}")
    
    # Pad signature to SIGNATURE_SIZE
    signature = raw_signature + b'\x00' * (SIGNATURE_SIZE - real_signature_length)
    print(f"Signature padded to: {len(signature)} bytes")
    
    # Build header partition without CRC first
    # Header structure: magic(2) + version(2) + size(4) + signature(4096) + padding
    temp_header = struct.pack("<HH", IMAGE_HDR_MAGIC, image_version)  # magic + version
    temp_header += struct.pack("<L", image_size)  # image size
    temp_header += signature  # Signature (padded to 4096 bytes)
    temp_header += b'\x00' * (HEADER_PARTITION_SIZE - HEADER_SIZE - SIGNATURE_SIZE)  # Padding
    
    # Calculate CRC over the entire header partition (with CRC=0) + image data
    crc_data = temp_header + image_data
    final_crc = binascii.crc32(crc_data) & 0xffffffff
    print(f"CRC calculated over header + image: 0x{final_crc:08x}")
    
    # Build final header partition with actual CRC
    final_header = struct.pack("<L", final_crc)  # CRC
    final_header += struct.pack("<HH", IMAGE_HDR_MAGIC, image_version)  # magic + version
    final_header += struct.pack("<L", image_size)  # image size
    final_header += signature  # Signature (padded to 4096 bytes)
    final_header += b'\x00' * (HEADER_PARTITION_SIZE - HEADER_SIZE - SIGNATURE_SIZE)  # Padding
    
    # Create new file with header + image data
    with open(output_bin_filename, "wb") as f:
        # Write the complete header partition
        f.write(final_header)
        # Write the image data
        f.write(image_data)
    
    print(f"Created '{output_bin_filename}' with header and CRC")
    print(f"  Header partition: {HEADER_PARTITION_SIZE} bytes")
    print(f"  Image data: {image_size} bytes")
    print(f"  Total file size: {HEADER_PARTITION_SIZE + image_size} bytes")
    
    return output_bin_filename

