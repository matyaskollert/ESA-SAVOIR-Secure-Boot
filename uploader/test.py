from pathlib import Path
import oqs

secret_key = Path("keys/wolfcryps-ml-dsa-private.bin").read_bytes()
public_key = Path("keys/wolfcryps-ml-dsa-public.bin").read_bytes()

parameter_set = "ML-DSA-44"

with oqs.Signature(parameter_set, secret_key=secret_key) as algo:
    data = b"Hello, world!"
    signature = algo.sign(data)
    print(f"Signature ({len(signature)} bytes): {signature.hex()}")

with oqs.Signature(parameter_set) as algo:
    valid = algo.verify(data, signature, public_key=public_key)
    print(f"Signature valid: {valid}")