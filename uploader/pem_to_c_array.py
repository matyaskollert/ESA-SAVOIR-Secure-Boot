"""
Convert a public key file to a C byte array suitable for embedding in firmware.

Supported key formats:
  .pem  — ECDSA P-256 public key (DER-encoded SubjectPublicKeyInfo).
          Consumed by wolfSSL's wc_EccPublicKeyDecode().
  .bin  — ML-DSA raw public key (1312 bytes for ML-DSA-44 / 1952 for ML-DSA-65).
          Consumed by wolfSSL's wc_dilithium_import_public().

Usage:
  python pem_to_c_array.py <key_file> [array_name]
"""
import sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# ML-DSA raw public-key sizes by parameter set
_MLDSA_PK_SIZES = {
    1312: "ML-DSA-44 (NIST level 2)",
    1952: "ML-DSA-65 (NIST level 3)",
    2592: "ML-DSA-87 (NIST level 5)",
}


def _print_c_array(label: str, source_name: str, raw_bytes: bytes, array_name: str) -> None:
    """Print a C byte-array declaration to stdout."""
    print(f"// {label} ({len(raw_bytes)} bytes)")
    print(f"// Generated from: {source_name}")
    print(f"const byte {array_name}[] = {{")

    cols = 12
    for i in range(0, len(raw_bytes), cols):
        chunk = raw_bytes[i : i + cols]
        hex_values = ", ".join(f"0x{b:02x}" for b in chunk)
        comma = "," if (i + cols) < len(raw_bytes) else ""
        print(f"    {hex_values}{comma}")

    print("};")
    print()
    print(f"// Key size: {len(raw_bytes)} bytes")


def pem_to_c_array(pem_file_path: str, array_name: str = "pubKey") -> None:
    """
    Convert an ECDSA PEM public key to a C byte array (DER/SubjectPublicKeyInfo
    format expected by wolfSSL's wc_EccPublicKeyDecode).
    """
    with open(pem_file_path, "rb") as fh:
        pem_data = fh.read()

    public_key = serialization.load_pem_public_key(pem_data, backend=default_backend())

    der_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    _print_c_array(
        label="ECDSA P-256 Public Key — DER-encoded SubjectPublicKeyInfo",
        source_name=Path(pem_file_path).name,
        raw_bytes=der_bytes,
        array_name=array_name,
    )


def mldsa_bin_to_c_array(bin_file_path: str, array_name: str = "pubKey") -> None:
    """
    Convert an ML-DSA raw public-key binary file (.bin) to a C byte array.
    The raw bytes are passed directly to wolfSSL's wc_dilithium_import_public().
    """
    raw_bytes = Path(bin_file_path).read_bytes()

    param_set = _MLDSA_PK_SIZES.get(len(raw_bytes), f"ML-DSA (unknown — {len(raw_bytes)} bytes)")
    label = f"ML-DSA Public Key — raw bytes for wc_dilithium_import_public() — {param_set}"

    _print_c_array(
        label=label,
        source_name=Path(bin_file_path).name,
        raw_bytes=raw_bytes,
        array_name=array_name,
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    key_file = sys.argv[1]
    arr_name = sys.argv[2] if len(sys.argv) > 2 else "pubKey"

    if not Path(key_file).exists():
        print(f"Error: File not found: {key_file}")
        sys.exit(1)

    suffix = Path(key_file).suffix.lower()
    if suffix == ".pem":
        pem_to_c_array(key_file, arr_name)
    elif suffix == ".bin":
        mldsa_bin_to_c_array(key_file, arr_name)
    else:
        print(f"Error: Unsupported file extension '{suffix}'. Use .pem (ECDSA) or .bin (ML-DSA).")
        sys.exit(1)
