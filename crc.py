import argparse
import binascii
import struct
from crccheck.crc import Crc32Mpeg2


def patch_binary_payload(bin_filename):
    """
    Patch crc & data_size fields of image_hdr_t in place in binary
    Raise exception if binary is not a supported type
    """
    IMAGE_HDR_SIZE_BYTES = 16
    IMAGE_HDR_MAGIC = 0xABCD
    IMAGE_HDR_VERSION = 1
    SECTION_COPY_ENTRY_SIZE = 12  # 3 uint32_t fields
    USE_HW_CRC = False  # Set to False to use software CRC32

    with open(bin_filename, "rb") as f:
        image_hdr = f.read(IMAGE_HDR_SIZE_BYTES)
        data = f.read()

    image_magic, image_hdr_version = struct.unpack("<HH", image_hdr[0:4])

    if image_magic != IMAGE_HDR_MAGIC:
        raise Exception(
            "Unsupported Binary Type. Expected 0x{:02x} Got 0x{:02x}".format(
                IMAGE_HDR_MAGIC, image_magic
            )
        )

    # Extract num_sections from header
    num_sections = struct.unpack("<L", image_hdr[12:16])[0]
    print(f"Number of sections: {num_sections}")
    
    # Parse section copy table
    section_table_size = num_sections * SECTION_COPY_ENTRY_SIZE
    section_table = data[:section_table_size]
    
    # Read the entire binary file (including header)
    with open(bin_filename, "rb") as f:
        full_binary = f.read()
    
    # Determine the image base address from the first section's src_lma
    # The binary file layout is: [header][section_table][section_data...]
    # We need to calculate: image_base = first_section_src_lma - first_section_file_offset
    first_src_lma = None
    for i in range(num_sections):
        offset = i * SECTION_COPY_ENTRY_SIZE
        src_lma, dst_vma, size = struct.unpack("<LLL", section_table[offset:offset + 12])
        if size > 0:
            first_src_lma = src_lma
            break
    
    if first_src_lma is None:
        raise Exception("No valid sections found to determine image base")
    
    # The first section data starts right after the header and section table in the file
    # But it might be padded to some alignment. Let's look at actual file structure.
    # The src_lma tells us the absolute FLASH address. 
    # We need to find what file offset corresponds to that address.
    # Since we don't know the base yet, we'll try common known values
    
    # Try known image bases
    possible_bases = [0x08020000, 0x08040000]
    image_base_flash = None
    
    for base in possible_bases:
        expected_offset = first_src_lma - base
        # Check if this makes sense (offset should be reasonable, like 0x400)
        if 0 < expected_offset < len(full_binary):
            image_base_flash = base
            print(f"Detected image base FLASH address: 0x{image_base_flash:08x}")
            break
    
    if image_base_flash is None:
        # Fallback: assume first section is at a typical offset like 0x400
        # and calculate base from that
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
        # The binary file starts at the image base, so:
        section_offset_in_file = src_lma - image_base_flash
        
        # Read section data from the correct offset
        section_data = full_binary[section_offset_in_file:section_offset_in_file + size]

        if (size < 100):
            # print the whole section data in hex for small sections
            print(f"  Section data (hex): {section_data.hex()}")

        if not USE_HW_CRC:
            section_crc = binascii.crc32(section_data) & 0xffffffff
        else:
            section_crc = Crc32Mpeg2.calc(section_data)


        print(f"Section {i}: src_lma=0x{src_lma:08x}, size={size}, file_offset=0x{section_offset_in_file:x}, crc=0x{section_crc:08x}")
        # print first 32 byte word of section data for verification
        first_word = struct.unpack("<L", section_data[0:4])[0]
        print(f"  First word of section data: 0x{first_word:08x}")
        print("")
        
        # Combine CRCs using XOR
        combined_crc ^= section_crc
    
    data_size = len(data)
    
    print(f"Combined CRC: 0x{combined_crc:08x}")

    image_hdr_crc_data_size = struct.pack("<LL", data_size, combined_crc)
    print(
        "Adding crc:0x{:08x} data_size:{} to '{}'".format(
            combined_crc, data_size, bin_filename
        )
    )
    with open(bin_filename, "r+b") as f:
        # Seek to beginning of "uint32_t crc"
        f.seek(4)
        # Write correct values into crc & data_size
        f.write(image_hdr_crc_data_size)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("bin", action="store")
    args = parser.parse_args()

    patch_binary_payload(args.bin)