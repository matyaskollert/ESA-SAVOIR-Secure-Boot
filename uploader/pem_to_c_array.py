"""
Convert a public key file to a C byte array suitable for embedding in firmware.

Supported key formats:
  .pem  — ECDSA P-256 public key (PEM-encoded SubjectPublicKeyInfo).
          Consumed by wolfSSL's wc_EccPublicKeyDecode().
  .der  — DER-encoded SubjectPublicKeyInfo (ECDSA or RSA public key).
          Consumed by wolfSSL's wc_EccPublicKeyDecode() / wc_RsaPublicKeyDecode().
  .bin  — Raw public key bytes (ML-DSA or LMS).
          Consumed by wolfSSL's wc_dilithium_import_public() / wc_LmsKey_ImportPubRaw().

Usage:
  python pem_to_c_array.py <key_file> [array_name]
"""
import sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# Known raw public-key sizes → human-readable label
_RAW_PK_LABELS = {
    60:   "LMS-SHA256-H5-W8 public key — raw bytes for wc_LmsKey_ImportPubRaw()",
    1312: "ML-DSA-44 public key — raw bytes for wc_dilithium_import_public()",
    1952: "ML-DSA-65 public key — raw bytes for wc_dilithium_import_public()",
    2592: "ML-DSA-87 public key — raw bytes for wc_dilithium_import_public()",
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


def bin_to_c_array(bin_file_path: str, array_name: str = "pubKey") -> None:
    """
    Convert a raw public-key binary file (.bin) to a C byte array.
    Supports ML-DSA (wc_dilithium_import_public) and LMS (wc_LmsKey_ImportPubRaw).
    """
    raw_bytes = Path(bin_file_path).read_bytes()
    label = _RAW_PK_LABELS.get(len(raw_bytes), f"raw public key ({len(raw_bytes)} bytes)")
    _print_c_array(label=label, source_name=Path(bin_file_path).name,
                   raw_bytes=raw_bytes, array_name=array_name)


def mldsa_bin_to_c_array(bin_file_path: str, array_name: str = "pubKey") -> None:
    """Alias kept for backwards compatibility."""
    bin_to_c_array(bin_file_path, array_name)


def der_to_c_array(der_file_path: str, array_name: str = "pubKey") -> None:
    """
    Convert a DER-encoded SubjectPublicKeyInfo file (.der) to a C byte array.
    Works for both ECDSA (wc_EccPublicKeyDecode) and RSA (wc_RsaPublicKeyDecode).
    """
    raw_bytes = Path(der_file_path).read_bytes()

    # Try to determine algorithm from the DER for a nicer label
    try:
        from cryptography.hazmat.primitives.asymmetric import ec, rsa
        key = serialization.load_der_public_key(raw_bytes, backend=default_backend())
        if isinstance(key, ec.EllipticCurvePublicKey):
            label = f"ECDSA {key.curve.name} public key — DER SubjectPublicKeyInfo for wc_EccPublicKeyDecode()"
        elif isinstance(key, rsa.RSAPublicKey):
            bits = key.key_size
            label = f"RSA-{bits} public key — DER SubjectPublicKeyInfo for wc_RsaPublicKeyDecode()"
        else:
            label = f"DER SubjectPublicKeyInfo ({len(raw_bytes)} bytes)"
    except Exception:
        label = f"DER SubjectPublicKeyInfo ({len(raw_bytes)} bytes)"

    _print_c_array(label=label, source_name=Path(der_file_path).name,
                   raw_bytes=raw_bytes, array_name=array_name)


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
        bin_to_c_array(key_file, arr_name)
    elif suffix == ".der":
        der_to_c_array(key_file, arr_name)
    else:
        print(f"Error: Unsupported file extension '{suffix}'. Use .pem, .der, or .bin.")
        sys.exit(1)
