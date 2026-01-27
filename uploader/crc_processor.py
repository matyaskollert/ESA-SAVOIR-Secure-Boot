"""
CRC processor module for patching binary files with header and CRC.
Binary structure (already present in input file):
- First 1024 bytes: Header partition (only first 12 bytes are actual header)
  - 2 bytes: magic (0xABCD)
  - 2 bytes: version
  - 4 bytes: image size
  - 4 bytes: CRC (to be calculated and patched)
  - Remaining 1012 bytes: padding
- From byte 1024 onwards: Image data

Final CRC = image_crc ^ header_crc
"""
import struct
import binascii
from pathlib import Path


def process_binary_with_crc(input_bin_filename, output_bin_filename=None, image_version=None):
    """
    Process binary file and calculate/patch CRC in existing header.
    Input file already has the 1024-byte header partition + image data structure.
    
    Args:
        input_bin_filename: Path to input binary file (with header partition already present)
        output_bin_filename: Path to output binary file (optional, defaults to input_patched.bin)
        image_version: Version number to use (optional, if None uses version from input file)
    
    Returns:
        Path to the output file
    """
    HEADER_PARTITION_SIZE = 1024  # Total header partition size
    HEADER_SIZE = 12  # Actual header size (magic:2, version:2, size:4, crc:4)
    IMAGE_HDR_MAGIC = 0xABCD

    # Generate output filename if not provided
    if output_bin_filename is None:
        input_path = Path(input_bin_filename)
        output_bin_filename = str(input_path.parent / f"{input_path.stem}_patched{input_path.suffix}")

    # Read the binary file (header partition + image data)
    with open(input_bin_filename, "rb") as f:
        header_partition = f.read(HEADER_PARTITION_SIZE)
        image_data = f.read()
    
    # Extract existing header fields
    magic, version, size, old_crc = struct.unpack("<HHLL", header_partition[:HEADER_SIZE])
    
    print(f"Existing header: magic=0x{magic:04x}, version={version}, size={size}, crc=0x{old_crc:08x}")
    
    # Use provided version or keep existing one
    if image_version is None:
        image_version = version
    
    image_size = len(image_data)
    
    print(f"Using image version: {image_version}")
    print(f"Image size: {image_size} bytes")
    
    # Calculate image CRC
    image_crc = binascii.crc32(image_data) & 0xffffffff
    print(f"Image CRC: 0x{image_crc:08x}")
    
    # Build header with CRC field set to 0 for header CRC calculation
    temp_header = struct.pack("<HH", IMAGE_HDR_MAGIC, image_version)  # magic + version
    temp_header += struct.pack("<L", image_size)  # image size
    temp_header += struct.pack("<L", 0)  # crc placeholder (set to 0)
    
    # Calculate header CRC (only first 12 bytes)
    header_crc = binascii.crc32(temp_header) & 0xffffffff
    print(f"Header CRC (with crc=0): 0x{header_crc:08x}")
    
    # Calculate final CRC
    final_crc = image_crc ^ header_crc
    print(f"Final CRC (image_crc ^ header_crc): 0x{final_crc:08x}")
    
    # Create new file with updated CRC in header
    with open(output_bin_filename, "wb") as f:
        # Write updated header (12 bytes)
        f.write(struct.pack("<HH", IMAGE_HDR_MAGIC, image_version))
        f.write(struct.pack("<L", image_size))
        f.write(struct.pack("<L", final_crc))
        
        # Write the rest of the header partition (padding)
        f.write(header_partition[HEADER_SIZE:])
        
        # Write the image data
        f.write(image_data)
    
    print(f"Created '{output_bin_filename}' with updated CRC")
    print(f"  Header partition: {HEADER_PARTITION_SIZE} bytes")
    print(f"  Image data: {image_size} bytes")
    print(f"  Total file size: {HEADER_PARTITION_SIZE + image_size} bytes")
    
    return output_bin_filename
