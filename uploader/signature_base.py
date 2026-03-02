"""
Base signature interface for binary signing.
This module defines the common API that all signature algorithms must implement.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Tuple, Optional


class SignatureAlgorithm(ABC):
    """Abstract base class for signature algorithms."""
    
    @abstractmethod
    def generate_keys(self, private_key_path: str, public_key_path: str) -> Tuple[str, str]:
        """
        Generate a new key pair for signing.
        
        Args:
            private_key_path: Path where the private key will be saved
            public_key_path: Path where the public key will be saved
            
        Returns:
            Tuple of (private_key_path, public_key_path)
        """
        pass
    
    @abstractmethod
    def load_keys(self, private_key_path: Optional[str] = None, public_key_path: Optional[str] = None):
        """
        Load existing keys from files.
        
        Args:
            private_key_path: Path to the private key file (for signing)
            public_key_path: Path to the public key file (for verification)
        """
        pass
    
    @abstractmethod
    def sign(self, data: bytes) -> bytes:
        """
        Sign the given data.
        
        Args:
            data: The data to sign
            
        Returns:
            The signature bytes
        """
        pass
    
    @abstractmethod
    def verify(self, data: bytes, signature: bytes) -> bool:
        """
        Verify a signature.
        
        Args:
            data: The original data
            signature: The signature to verify
            
        Returns:
            True if signature is valid, False otherwise
        """
        pass
    
    @abstractmethod
    def get_algorithm_name(self) -> str:
        """
        Get the name of the signature algorithm.
        
        Returns:
            Name of the algorithm
        """
        pass
