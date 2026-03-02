"""
ECDSA signature implementation.
Uses NIST P-256 curve for ECDSA signing with SHA-256 hash.
"""
from pathlib import Path
from typing import Tuple, Optional, Union
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from signature_base import SignatureAlgorithm


class ECDSASignature(SignatureAlgorithm):
    """ECDSA signature implementation using NIST P-256 curve."""
    
    # Signature size padded to 4096 bytes to support ML-DSA compatibility
    SIGNATURE_SIZE = 4096  # 4096 bytes as specified
    
    def __init__(self):
        """Initialize ECDSA signature handler."""
        self.private_key: Optional[ec.EllipticCurvePrivateKey] = None
        self.public_key: Optional[ec.EllipticCurvePublicKey] = None
    
    def generate_keys(self, private_key_path: str, public_key_path: str) -> Tuple[str, str]:
        """
        Generate a new ECDSA key pair using NIST P-256 curve.
        
        Args:
            private_key_path: Path where the private key will be saved
            public_key_path: Path where the public key will be saved
            
        Returns:
            Tuple of (private_key_path, public_key_path)
        """
        # Generate private key using NIST P-256 curve (secp256r1)
        self.private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        self.public_key = self.private_key.public_key()
        
        # Serialize and save private key
        private_pem = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        private_path = Path(private_key_path)
        private_path.parent.mkdir(parents=True, exist_ok=True)
        with open(private_path, 'wb') as f:
            f.write(private_pem)
        
        # Serialize and save public key
        public_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        public_path = Path(public_key_path)
        public_path.parent.mkdir(parents=True, exist_ok=True)
        with open(public_path, 'wb') as f:
            f.write(public_pem)
        
        print(f"Generated ECDSA key pair:")
        print(f"  Private key: {private_key_path}")
        print(f"  Public key: {public_key_path}")
        
        return (str(private_path), str(public_path))
    
    def load_keys(self, private_key_path: Optional[str] = None, public_key_path: Optional[str] = None):
        """
        Load existing ECDSA keys from PEM files.
        
        Args:
            private_key_path: Path to the private key file (for signing)
            public_key_path: Path to the public key file (for verification)
        """
        if private_key_path:
            with open(private_key_path, 'rb') as f:
                self.private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=default_backend()
                )
            print(f"Loaded ECDSA private key from: {private_key_path}")
        
        if public_key_path:
            with open(public_key_path, 'rb') as f:
                self.public_key = serialization.load_pem_public_key(
                    f.read(),
                    backend=default_backend()
                )
            print(f"Loaded ECDSA public key from: {public_key_path}")
    
    def sign(self, data: bytes) -> bytes:
        """
        Sign data using ECDSA with SHA-256.
        
        Args:
            data: The data to sign
            
        Returns:
            The raw signature bytes (not padded)
            
        Raises:
            ValueError: If private key is not loaded
        """
        if not self.private_key:
            raise ValueError("Private key not loaded. Call generate_keys() or load_keys() first.")
        
        # create the SHA-256 hash of the data
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digest.update(data)
        hashed_data = digest.finalize()

        print(f"Data hashed to SHA-256: {hashed_data.hex()}")
        
        # Sign the data using ECDSA with SHA-256
        signature = self.private_key.sign(
            data,
            ec.ECDSA(hashes.SHA256())
        )

        print(f"Generated raw signature of length {len(signature)} bytes")
        
        # Check signature size doesn't exceed maximum
        if len(signature) > self.SIGNATURE_SIZE:
            raise ValueError(f"Signature size {len(signature)} exceeds maximum {self.SIGNATURE_SIZE}")
        
        return signature
    
    def verify(self, data: bytes, signature: bytes) -> bool:
        """
        Verify an ECDSA signature.
        
        Args:
            data: The original data
            signature: The signature to verify (may be padded)
            
        Returns:
            True if signature is valid, False otherwise
            
        Raises:
            ValueError: If public key is not loaded
        """
        if not self.public_key:
            raise ValueError("Public key not loaded. Call generate_keys() or load_keys() first.")
        
        try:
            # Remove padding - find the actual signature length
            # DER signatures start with 0x30, so we can trim trailing zeros
            actual_signature = signature.rstrip(b'\x00')
            
            # Verify the signature
            self.public_key.verify(
                actual_signature,
                data,
                ec.ECDSA(hashes.SHA256())
            )
            return True
        except Exception as e:
            print(f"Signature verification failed: {e}")
            return False
    
    def get_algorithm_name(self) -> str:
        """
        Get the name of the signature algorithm.
        
        Returns:
            Name of the algorithm
        """
        return "ECDSA-P256-SHA256"
