"""
Binary processor module for adding header with signature and CRC to binary files.

Binary structure (created by this module):
- First 5120 bytes: Header partition
  - 4 bytes:    CRC  (calculated over header + image data)
  - 2 bytes:    magic (0xABCD)
  - 2 bytes:    version
  - 4 bytes:    image size
  - 4096 bytes: Digital signature (padded to 4096 bytes)
  - Remaining:  padding
- From byte 5120 onwards: Image data

Signature field layout per algorithm:
  ECDSA-P256 only:   [0 .. sigLen-1]  raw DER signature (≤72 bytes)
  ML-DSA only:       [0 .. 3308]      raw ML-DSA signature (3309 bytes)
  Hybrid (both):     [0 .. 71]        ECDSA-P256 DER signature (≤72 bytes)
                     [72 .. 3380]     ML-DSA-65 raw signature  (3309 bytes)
  The firmware reads HYBRID_MLDSA_OFFSET = 72 to locate the ML-DSA blob.

Processing order:
1. Read the binary file (no header present)
2. Build the data-to-sign: header-without-CRC + image data
3. Sign with the chosen algorithm(s)
4. Pack signatures into the 4096-byte signature field
5. Build the full header partition (CRC placeholder at offset 0)
6. Calculate CRC over header partition + image data
7. Write CRC into the header and output the final file
"""
import struct
from pathlib import Path
from typing import Optional
from signature_base import SignatureAlgorithm

# Offsets inside the 4096-byte signature field — must match firmware crypto.c
HYBRID_ECDSA_MAX_BYTES = 72   # ECDSA-P256 DER signatures are at most 72 bytes
HYBRID_MLDSA_OFFSET    = HYBRID_ECDSA_MAX_BYTES  # ML-DSA-65 starts immediately after


_CRC32_MPEG2_POLY = 0x04C11DB7


def _crc32_mpeg2(data: bytes) -> int:
    """CRC32/MPEG-2 with byte-reversed 32-bit words."""
    crc = 0xFFFFFFFF
    for i in range(0, len(data), 4):
        word_bytes = data[i:i + 4]
        if len(word_bytes) < 4:
            word_bytes = word_bytes + b'\x00' * (4 - len(word_bytes))
        word_bytes = word_bytes[::-1]
        word = int.from_bytes(word_bytes, 'big')
        for bit in range(32):
            if (crc ^ (word << bit)) & 0x80000000:
                crc = (crc << 1) ^ _CRC32_MPEG2_POLY
            else:
                crc <<= 1
            crc &= 0xFFFFFFFF
    return crc


def process_binary(
    input_bin_filename: str,
    signature_algo: SignatureAlgorithm,
    hybrid_mldsa_algo: Optional[SignatureAlgorithm] = None,
    output_bin_filename: Optional[str] = None,
    image_version: int = 1,
) -> str:
    """
    Process a raw binary file and add an image header with CRC and signature(s).

    The input file must contain only image data (no header).

    Args:
        input_bin_filename:  Path to the raw input binary.
        signature_algo:      Primary signature algorithm (ECDSA-P256, or ML-DSA in
                             post-quantum-only mode).
        hybrid_mldsa_algo:   Secondary ML-DSA algorithm instance used for hybrid mode.
                             When provided, ``signature_algo`` must be ECDSA-P256 and its
                             signature is placed at offset 0; the ML-DSA signature is placed
                             at offset HYBRID_MLDSA_OFFSET (72) in the 4096-byte field.
        output_bin_filename: Destination path (optional; defaults to
                             ``<stem>_with_header.bin`` next to the input file).
        image_version:       16-bit version number stored in the header (default: 1).

    Returns:
        Absolute path to the output file as a string.
    """
    HEADER_PARTITION_SIZE = 5 * 1024  # 5 KB
    SIGNATURE_SIZE        = 4096      # bytes reserved in the header for signature(s)
    HEADER_SIZE           = 12        # crc(4) + magic(2) + version(2) + size(4)
    IMAGE_HDR_MAGIC       = 0xABCD

    hybrid_mode = hybrid_mldsa_algo is not None

    # ── Derive output path ────────────────────────────────────────────────────
    if output_bin_filename is None:
        input_path = Path(input_bin_filename)
        output_bin_filename = str(
            input_path.parent / f"{input_path.stem}_with_header{input_path.suffix}"
        )

    # ── Read raw image data ───────────────────────────────────────────────────
    image_data = Path(input_bin_filename).read_bytes()
    image_size = len(image_data)

    print(f"Input file  : {input_bin_filename}")
    print(f"Image size  : {image_size} bytes")
    print(f"Image ver.  : {image_version}")
    print(f"Signing mode: {'Hybrid (ECDSA-P256 + ML-DSA-65)' if hybrid_mode else signature_algo.get_algorithm_name()}")

    # ── Build the data buffer that will be signed ─────────────────────────────
    # Layout: magic(2) + version(2) + size(4) + sig_field_zeros(4096) + padding + image_data
    # The CRC field (first 4 bytes of the final header) is NOT included in sign_data
    # so that the CRC can be added after signing without invalidating signatures.
    sign_data  = struct.pack("<HH", IMAGE_HDR_MAGIC, image_version)  # magic + version
    sign_data += struct.pack("<L",  image_size)                       # image size
    sign_data += b'\x00' * (HEADER_PARTITION_SIZE - HEADER_SIZE)      # sig field + padding (zeroed)
    sign_data += image_data

    print(f"Sign buffer : {len(sign_data)} bytes")

    # ── Produce the 4096-byte signature field ─────────────────────────────────
    if hybrid_mode:
        # ── Hybrid: ECDSA at [0..71], ML-DSA-65 at [72..3380] ────────────────
        print(f"\nStep 1 — ECDSA-P256 signature ...")
        ecdsa_sig = signature_algo.sign(sign_data)
        if len(ecdsa_sig) > HYBRID_ECDSA_MAX_BYTES:
            raise ValueError(
                f"ECDSA signature too large for hybrid slot: "
                f"{len(ecdsa_sig)} > {HYBRID_ECDSA_MAX_BYTES} bytes"
            )
        print(f"  ECDSA signature : {len(ecdsa_sig)} bytes (offset 0)")

        print(f"\nStep 2 — ML-DSA-65 signature ...")
        mldsa_sig = hybrid_mldsa_algo.sign(sign_data)
        print(f"  ML-DSA signature: {len(mldsa_sig)} bytes (offset {HYBRID_MLDSA_OFFSET})")

        # Pack into the 4096-byte field
        sig_field  = ecdsa_sig
        sig_field += b'\x00' * (HYBRID_MLDSA_OFFSET - len(ecdsa_sig))  # pad ECDSA slot to 72 bytes
        sig_field += mldsa_sig
        sig_field += b'\x00' * (SIGNATURE_SIZE - len(sig_field))        # zero-pad remainder

        if len(sig_field) != SIGNATURE_SIZE:
            raise ValueError(
                f"Hybrid signature field is {len(sig_field)} bytes; expected {SIGNATURE_SIZE}"
            )
        print(f"\nHybrid signature field: {len(sig_field)} bytes total")

    else:
        # ── Single algorithm ──────────────────────────────────────────────────
        print(f"\nGenerating {signature_algo.get_algorithm_name()} signature ...")
        raw_sig = signature_algo.sign(sign_data)
        if len(raw_sig) > SIGNATURE_SIZE:
            raise ValueError(
                f"Signature ({len(raw_sig)} B) exceeds the {SIGNATURE_SIZE}-byte field"
            )
        sig_field  = raw_sig
        sig_field += b'\x00' * (SIGNATURE_SIZE - len(raw_sig))
        print(f"Signature   : {len(raw_sig)} bytes (padded to {SIGNATURE_SIZE})")

    # ── Build temp header (CRC placeholder = 0x00000000) ─────────────────────
    temp_header  = struct.pack("<HH", IMAGE_HDR_MAGIC, image_version)
    temp_header += struct.pack("<L",  image_size)
    temp_header += sig_field
    temp_header += b'\x00' * (HEADER_PARTITION_SIZE - HEADER_SIZE - SIGNATURE_SIZE)

    # ── Calculate CRC over (temp_header + image_data) ─────────────────────────
    final_crc = _crc32_mpeg2(temp_header + image_data)
    print(f"\nCRC-32/MPEG-2: 0x{final_crc:08x}")

    # ── Build final header with real CRC prepended ────────────────────────────
    final_header  = struct.pack("<L",  final_crc)
    final_header += struct.pack("<HH", IMAGE_HDR_MAGIC, image_version)
    final_header += struct.pack("<L",  image_size)
    final_header += sig_field
    final_header += b'\x00' * (HEADER_PARTITION_SIZE - HEADER_SIZE - SIGNATURE_SIZE)

    # ── Write output file ─────────────────────────────────────────────────────
    with open(output_bin_filename, "wb") as f:
        f.write(final_header)
        f.write(image_data)

    total_size = HEADER_PARTITION_SIZE + image_size
    print(f"\nOutput file : {output_bin_filename}")
    print(f"  Header    : {HEADER_PARTITION_SIZE} bytes")
    print(f"  Image     : {image_size} bytes")
    print(f"  Total     : {total_size} bytes")

    return output_bin_filename

