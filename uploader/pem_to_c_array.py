"""
Convert PEM public key to C byte array.
"""
import sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend


def pem_to_c_array(pem_file_path, array_name="pubKey"):
    """Convert PEM public key to C byte array."""
    
    # Read PEM file
    with open(pem_file_path, 'rb') as f:
        pem_data = f.read()
    
    # Load public key
    public_key = serialization.load_pem_public_key(pem_data, backend=default_backend())
    
    # Get DER-encoded public key (SubjectPublicKeyInfo format for wolfCrypt)
    der_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # Generate C array
    print(f"// ECDSA P-256 Public Key in DER format ({len(der_bytes)} bytes)")
    print(f"// Generated from: {Path(pem_file_path).name}")
    print(f"const byte {array_name}[] = {{")
    
    # Format as hex bytes, 12 per line
    for i in range(0, len(der_bytes), 12):
        chunk = der_bytes[i:i+12]
        hex_values = ', '.join(f'0x{b:02x}' for b in chunk)
        if i + 12 < len(der_bytes):
            print(f"    {hex_values},")
        else:
            print(f"    {hex_values}")
    
    print("};")
    print()
    print(f"// Key size: {len(der_bytes)} bytes")
    print(f"// Format: DER-encoded SubjectPublicKeyInfo")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        pem_file = sys.argv[1]
    else:
        # Default to the generated key
        pem_file = "keys/public_key_20260128_112221.pem"
    
    if not Path(pem_file).exists():
        print(f"Error: File not found: {pem_file}")
        sys.exit(1)
    
    pem_to_c_array(pem_file)
