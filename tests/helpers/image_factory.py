"""
image_factory.py – Build test firmware images for E2E tests.

Uses the same logic as uploader/binary_processor.py so the images are
identical to what the GUI tool would produce.  The private key used here
must match the public key embedded in the BSW firmware (crypto.c pubKey[]).

Typical usage in tests::

    from helpers.image_factory import ImageFactory, build_minimal_image

    factory = ImageFactory(private_key_path="keys/private_key.pem")

    # A valid signed image at version 5
    good_img = factory.build(version=5)

    # A valid image with a deliberatley wrong CRC
    bad_crc_img = factory.corrupt_crc(good_img)
"""

import binascii
import struct
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Re-use the signing backend from the uploader package.
# The tests directory is a sibling of uploader/, so we add it to sys.path.
# ---------------------------------------------------------------------------
_UPLOADER_DIR = Path(__file__).resolve().parents[2] / "uploader"
if str(_UPLOADER_DIR) not in sys.path:
    sys.path.insert(0, str(_UPLOADER_DIR))

from signature_ecdsa import ECDSASignature   # noqa: E402
from signature_mldsa import MLDSASignature   # noqa: E402


# ---------------------------------------------------------------------------
# Constants – mirror binary_processor.py exactly
# ---------------------------------------------------------------------------
HEADER_PARTITION_SIZE = 5 * 1024   # 5 120 bytes total
SIGNATURE_SIZE        = 4096       # bytes reserved for the signature
HEADER_FIXED_SIZE     = 12         # crc(4) + magic(2) + version(2) + size(4)
IMAGE_HDR_MAGIC       = 0xABCD


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ImageFactory:
    """Builds signed firmware images for E2E tests.

    Args:
        private_key_path: Path to the private key file.
            - PEM file → ECDSA-P256
            - .bin file → ML-DSA-44 (default) – set mldsa_param_set for -65
        mldsa_param_set: "ML-DSA-44" or "ML-DSA-65" (only used for .bin keys)
        minimal_image_size: Size of the synthetic raw image payload in bytes.
            The payload is filled with 0x5A bytes so the BSW can read it as a
            valid ARM vector table if needed.
    """

    def __init__(
        self,
        private_key_path: str,
        mldsa_param_set: str = "ML-DSA-44",
        minimal_image_size: int = 256,
    ):
        self._key_path = Path(private_key_path)
        self._min_size = minimal_image_size

        suffix = self._key_path.suffix.lower()
        if suffix == ".pem":
            self._algo = ECDSASignature()
            self._algo.load_keys(private_key_path=private_key_path)
        elif suffix == ".bin":
            self._algo = MLDSASignature(mldsa_param_set)
            self._algo.load_keys(private_key_path=private_key_path)
        else:
            raise ValueError(
                f"Unsupported key file extension '{suffix}'. Use .pem (ECDSA) or .bin (ML-DSA)."
            )

    # ------------------------------------------------------------------ build

    def build(
        self,
        version: int = 1,
        image_payload: Optional[bytes] = None,
    ) -> bytes:
        """Build a fully signed image ready for upload or direct flash write.

        Args:
            version:       Image version embedded in the header.
            image_payload: Raw image data (no header). If None a minimal
                           synthetic payload is used.

        Returns:
            bytes – complete image (header partition + image data).
        """
        if image_payload is None:
            image_payload = _minimal_arm_payload(self._min_size)

        return _build_image(image_payload, version, self._algo)

    # ------------------------------------------------------------------ corruption helpers

    @staticmethod
    def corrupt_crc(image: bytes) -> bytes:
        """Return a copy of *image* with its CRC replaced by 0xDEADBEEF."""
        return struct.pack("<I", 0xDEADBEEF) + image[4:]

    @staticmethod
    def corrupt_magic(image: bytes) -> bytes:
        """Return a copy of *image* with its magic number replaced by 0x0000."""
        crc = image[:4]
        rest = image[6:]  # skip 2-byte magic
        return crc + struct.pack("<H", 0x0000) + rest

    @staticmethod
    def corrupt_signature(image: bytes) -> bytes:
        """Return a copy of *image* with the first byte of the signature flipped."""
        # Signature starts at offset 12 (after crc:4, magic:2, version:2, size:4)
        sig_offset = 12
        ba = bytearray(image)
        ba[sig_offset] ^= 0xFF
        return bytes(ba)

    @staticmethod
    def bump_version(image: bytes, new_version: int) -> bytes:
        """Return a copy of *image* with the version field replaced.

        WARNING: this invalidates the CRC and signature – useful to test the
        version-check path where the firmware reads the version before verifying.
        """
        crc    = image[:4]
        magic  = image[4:6]
        _ver   = image[6:8]           # discard
        rest   = image[8:]
        return crc + magic + struct.pack("<H", new_version) + rest


# ---------------------------------------------------------------------------
# Low-level image builder (mirrors binary_processor.process_binary())
# ---------------------------------------------------------------------------

def _build_image(image_data: bytes, version: int, algo) -> bytes:
    image_size = len(image_data)

    # Data signed: header-without-CRC (magic+version+size+zeroed-sig+pad) + image
    sign_data  = struct.pack("<HH", IMAGE_HDR_MAGIC, version)
    sign_data += struct.pack("<I",  image_size)
    sign_data += b'\x00' * (HEADER_PARTITION_SIZE - HEADER_FIXED_SIZE)
    sign_data += image_data

    raw_sig = algo.sign(sign_data)
    if len(raw_sig) > SIGNATURE_SIZE:
        raise ValueError(f"Signature {len(raw_sig)} B exceeds field {SIGNATURE_SIZE} B")
    signature = raw_sig + b'\x00' * (SIGNATURE_SIZE - len(raw_sig))

    # Header without CRC
    temp_hdr  = struct.pack("<HH", IMAGE_HDR_MAGIC, version)
    temp_hdr += struct.pack("<I",  image_size)
    temp_hdr += signature
    temp_hdr += b'\x00' * (HEADER_PARTITION_SIZE - HEADER_FIXED_SIZE - SIGNATURE_SIZE)

    crc = binascii.crc32(temp_hdr + image_data) & 0xFFFFFFFF

    final_hdr  = struct.pack("<I",  crc)
    final_hdr += struct.pack("<HH", IMAGE_HDR_MAGIC, version)
    final_hdr += struct.pack("<I",  image_size)
    final_hdr += signature
    final_hdr += b'\x00' * (HEADER_PARTITION_SIZE - HEADER_FIXED_SIZE - SIGNATURE_SIZE)

    return final_hdr + image_data


def _minimal_arm_payload(size: int) -> bytes:
    """Return a synthetic ARM Cortex-M payload of *size* bytes.

    The first 8 bytes are a pseudo-valid vector table:
        [0] Initial MSP = 0x20018000  (top of SRAM)
        [4] Reset handler = start of payload + 0x09 (thumb bit set)
    The rest is filled with 0x5A repeated.
    """
    payload = bytearray(size)
    struct.pack_into("<II", payload, 0,
                     0x20018000,          # initial MSP
                     0x00000009)          # fake reset handler (thumb)
    for i in range(8, size):
        payload[i] = 0x5A
    return bytes(payload)


# ---------------------------------------------------------------------------
# Convenience: build an image without instantiating ImageFactory
# ---------------------------------------------------------------------------

def build_minimal_image(
    private_key_path: str,
    version: int = 1,
    size: int = 256,
) -> bytes:
    """One-liner helper for tests that just need a quick valid image."""
    factory = ImageFactory(private_key_path, minimal_image_size=size)
    return factory.build(version=version)
