"""
CRC processor module for patching binary files with header and CRC.
This version creates a new file instead of modifying the original.
"""
import struct
import binascii
from pathlib import Path


def process_binary_with_crc(input_bin_filename, output_bin_filename=None, image_version=1):
    """
    Process binary file and add CRC & data_size fields to image_hdr_t.
    Creates a new file instead of modifying the original.
    
    Args:
        input_bin_filename: Path to input binary file
        output_bin_filename: Path to output binary file (optional, defaults to input_patched.bin)
        image_version: Version number to include in the header (1-255)
    
    Returns:
        Path to the output file
        
    Raises:
        Exception if binary is not a supported type
    """
    IMAGE_HDR_SIZE_BYTES = 16
    IMAGE_HDR_MAGIC = 0xABCD
    SECTION_COPY_ENTRY_SIZE = 12  # 3 uint32_t fields
    USE_HW_CRC = False  # Set to False to use software CRC32

    # Generate output filename if not provided
    if output_bin_filename is None:
        input_path = Path(input_bin_filename)
        output_bin_filename = str(input_path.parent / f"{input_path.stem}_patched{input_path.suffix}")

    with open(input_bin_filename, "rb") as f:
        image_hdr = f.read(IMAGE_HDR_SIZE_BYTES)
        data = f.read()

    image_magic, _ = struct.unpack("<HH", image_hdr[0:4])

    if image_magic != IMAGE_HDR_MAGIC:
        raise Exception(
            "Unsupported Binary Type. Expected 0x{:02x} Got 0x{:02x}".format(
                IMAGE_HDR_MAGIC, image_magic
            )
        )

    print(f"Using image version: {image_version}")

    # Extract num_sections from header
    num_sections = struct.unpack("<L", image_hdr[12:16])[0]
    print(f"Number of sections: {num_sections}")
    
    # Parse section copy table
    section_table_size = num_sections * SECTION_COPY_ENTRY_SIZE
    section_table = data[:section_table_size]
    
    # Read the entire binary file (including header)
    with open(input_bin_filename, "rb") as f:
        full_binary = f.read()
    
    # Determine the image base address from the first section's src_lma
    first_src_lma = None
    for i in range(num_sections):
        offset = i * SECTION_COPY_ENTRY_SIZE
        src_lma, dst_vma, size = struct.unpack("<LLL", section_table[offset:offset + 12])
        if size > 0:
            first_src_lma = src_lma
            break
    
    if first_src_lma is None:
        raise Exception("No valid sections found to determine image base")
    
    # Try known image bases
    image_base_flash = 0x08020000
    
    if image_base_flash is None:
        # Fallback: assume first section is at a typical offset like 0x400
        typical_offset = 0x400
        image_base_flash = first_src_lma - typical_offset
        print(f"Assumed image base FLASH address: 0x{image_base_flash:08x}")
    
    # Compute CRC for each section and combine them
    combined_crc = 0
    for i in range(num_sections):
        offset = i * SECTION_COPY_ENTRY_SIZE
        src_lma, dst_vma, size = struct.unpack("<LLL", section_table[offset:offset + 12])
        
        if size == 0:
            print(f"Section {i}: empty, skipping")
            continue
        
        # Calculate offset in binary file using src_lma
        section_offset_in_file = src_lma - image_base_flash
        
        # Read section data from the correct offset
        section_data = full_binary[section_offset_in_file:section_offset_in_file + size]

        if size < 100:
            print(f"  Section data (hex): {section_data.hex()}")

        section_crc = binascii.crc32(section_data) & 0xffffffff

        print(f"Section {i}: src_lma=0x{src_lma:08x}, size={size}, file_offset=0x{section_offset_in_file:x}, crc=0x{section_crc:08x}")
        first_word = struct.unpack("<L", section_data[0:4])[0]
        print(f"  First word of section data: 0x{first_word:08x}")
        print("")
        
        # Combine CRCs using XOR
        combined_crc ^= section_crc
    
    data_size = len(data)
    
    print(f"Combined CRC of sections: 0x{combined_crc:08x}")
    
    # Now build the complete header with version and compute final CRC
    # Header structure: [magic:2][version:2][data_size:4][crc:4][num_sections:4]
    # We need to compute CRC over the complete header (with CRC field set to 0) + data
    
    # Build header with CRC initially set to 0
    temp_header = struct.pack("<HH", IMAGE_HDR_MAGIC, image_version)  # magic + version
    temp_header += struct.pack("<L", data_size)  # data_size
    temp_header += struct.pack("<L", 0)  # crc placeholder (set to 0)
    temp_header += image_hdr[12:]  # num_sections (last 4 bytes of original header)
    
    # Compute CRC over complete header + data
    header_and_data = temp_header + data
    final_crc = binascii.crc32(header_and_data) & 0xffffffff
    
    print(f"Final CRC (including header): 0x{final_crc:08x}")
    print(f"Adding crc:0x{final_crc:08x} data_size:{data_size} version:{image_version} to '{output_bin_filename}'")
    
    # Create new file with patched header
    with open(output_bin_filename, "wb") as f:
        # Write magic and version
        f.write(struct.pack("<HH", IMAGE_HDR_MAGIC, image_version))
        # Write data size and CRC
        f.write(struct.pack("<LL", data_size, final_crc))
        # Write remaining header bytes (num_sections)
        f.write(image_hdr[12:])
        # Write the rest of the data
        f.write(data)
    
    return output_bin_filename
