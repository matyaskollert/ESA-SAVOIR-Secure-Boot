"""
ML-DSA (Module-Lattice Digital Signature Algorithm) signature implementation.
Based on NIST FIPS 204 using the wolfcrypt-py library.

Install the dependency with:  pip install wolfcrypt

# Parameter set supported (wolfSSL level number maps directly to firmware ML_DSA_LEVEL):
  ML-DSA-65  — NIST security category 3 (≈192-bit quantum)  wolfSSL level 3
               sig: 3309 B  |  pk: 1952 B  |  sk: 4032 B

NOTE: ML-DSA-87 signatures (4627 B) exceed the current 4096-byte signature
field in image_header_t and are not supported without a header format change.

Key storage format: raw binary (.bin) files.
  - Public key  → imported with wc_dilithium_import_public()  in firmware.
  - Private key → used by wolfcrypt for signing.
"""

from pathlib import Path
from typing import Tuple, Optional
from signature_base import SignatureAlgorithm

# Supported parameter set (ML-DSA-44 is not supported by the BSW firmware)
_PARAM_SETS = {
    "ML-DSA-65": {"level": 3, "sig_size": 3309, "pk_size": 1952, "sk_size": 4032, "wc_type": "ML_DSA_65"},
}


class MLDSASignature(SignatureAlgorithm):
    """
    ML-DSA signature implementation using wolfcrypt-py (pip install wolfcrypt).
    The raw public key bytes produced by wolfcrypt are compatible with wolfSSL's
    wc_dilithium_import_public() used in the firmware.
    """

    SIGNATURE_SIZE = 4096  # bytes reserved in the image header for a signature

    def __init__(self, parameter_set: str = "ML-DSA-65"):
        """
        Initialise an ML-DSA signature handler.

        Args:
            parameter_set: Must be "ML-DSA-65" (the only supported set).
        """
        if parameter_set not in _PARAM_SETS:
            raise ValueError(
                f"Unsupported parameter set '{parameter_set}'. "
                f"Choose from: {list(_PARAM_SETS.keys())}"
            )

        info = _PARAM_SETS[parameter_set]
        if info["sig_size"] > self.SIGNATURE_SIZE:
            raise ValueError(
                f"{parameter_set} signature size ({info['sig_size']} B) exceeds "
                f"the image header field ({self.SIGNATURE_SIZE} B). "
                "Increase image_header_t::signature[] and SIGNATURE_SIZE to use this set."
            )

        self.parameter_set = parameter_set
        self._level: int      = info["level"]
        self._sig_size: int   = info["sig_size"]
        self._pk_size: int    = info["pk_size"]
        self._sk_size: int    = info["sk_size"]
        self._wc_type_name: str = info["wc_type"]

        self._secret_key: Optional[bytes] = None
        self._public_key: Optional[bytes] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_wolfcrypt():
        """Import wolfcrypt with a helpful error message on failure."""
        try:
            from wolfcrypt.ciphers import MlDsaType, MlDsaPrivate, MlDsaPublic
            return MlDsaType, MlDsaPrivate, MlDsaPublic
        except ImportError as exc:
            raise ImportError(
                "wolfcrypt-py is required for ML-DSA.\n"
                "Install it with:  pip install wolfcrypt"
            ) from exc

    def _get_wc_type(self):
        """Return the MlDsaType enum value for this parameter set."""
        MlDsaType, _, _ = self._load_wolfcrypt()
        return getattr(MlDsaType, self._wc_type_name)

    # ------------------------------------------------------------------
    # Key management
    # ------------------------------------------------------------------

    def generate_keys(self, private_key_path: str, public_key_path: str) -> Tuple[str, str]:
        """
        Generate a new ML-DSA key pair and save it as raw binary files.

        Args:
            private_key_path: Destination for the private (secret) key (.bin).
            public_key_path:  Destination for the public key (.bin).

        Returns:
            (private_key_path, public_key_path) as strings.
        """
        MlDsaType, MlDsaPrivate, _ = self._load_wolfcrypt()
        wc_type = getattr(MlDsaType, self._wc_type_name)

        mldsa_priv = MlDsaPrivate.make_key(wc_type)
        self._secret_key = mldsa_priv.encode_priv_key()
        self._public_key = mldsa_priv.encode_pub_key()

        private_path = Path(private_key_path)
        public_path  = Path(public_key_path)
        private_path.parent.mkdir(parents=True, exist_ok=True)
        public_path.parent.mkdir(parents=True, exist_ok=True)

        private_path.write_bytes(self._secret_key)
        public_path.write_bytes(self._public_key)

        print(f"Generated {self.parameter_set} key pair:")
        print(f"  Private key : {private_key_path} ({len(self._secret_key)} bytes)")
        print(f"  Public key  : {public_key_path}  ({len(self._public_key)} bytes)")

        return str(private_path), str(public_path)

    def load_keys(
        self,
        private_key_path: Optional[str] = None,
        public_key_path: Optional[str] = None,
    ) -> None:
        """
        Load existing ML-DSA keys from raw binary files.

        Args:
            private_key_path: Path to the private key binary (needed for signing).
            public_key_path:  Path to the public key binary (needed for verification).
        """
        if private_key_path:
            self._secret_key = Path(private_key_path).read_bytes()
            print(f"Loaded {self.parameter_set} private key from: {private_key_path} "
                  f"({len(self._secret_key)} bytes)")

        if public_key_path:
            self._public_key = Path(public_key_path).read_bytes()
            print(f"Loaded {self.parameter_set} public key from: {public_key_path} "
                  f"({len(self._public_key)} bytes)")

    # ------------------------------------------------------------------
    # Signing / verification
    # ------------------------------------------------------------------

    def sign(self, data: bytes) -> bytes:
        """
        Sign *data* using ML-DSA.

        ML-DSA performs its own internal SHAKE-based hashing, so the full
        message bytes must be passed (not a pre-computed digest).

        Args:
            data: The raw bytes to sign.

        Returns:
            Raw signature bytes (exact algorithm length, no padding).

        Raises:
            ValueError: If the private key has not been loaded.
        """
        if not self._secret_key:
            raise ValueError(
                "Private key not loaded. Call generate_keys() or load_keys() first."
            )

        MlDsaType, MlDsaPrivate, _ = self._load_wolfcrypt()
        wc_type = getattr(MlDsaType, self._wc_type_name)

        mldsa_priv = MlDsaPrivate(wc_type)
        if self._public_key is not None:
            mldsa_priv.decode_key(self._secret_key, self._public_key)
        else:
            mldsa_priv.decode_key(self._secret_key)
        signature = mldsa_priv.sign(data)

        print(f"Generated {self.parameter_set} signature: {len(signature)} bytes")

        if len(signature) > self.SIGNATURE_SIZE:
            raise ValueError(
                f"Signature size {len(signature)} B exceeds header field {self.SIGNATURE_SIZE} B"
            )

        return signature

    def verify(self, data: bytes, signature: bytes) -> bool:
        """
        Verify an ML-DSA signature (strips trailing zero padding if present).

        Args:
            data:      The original message bytes.
            signature: Signature bytes (may be zero-padded to SIGNATURE_SIZE).

        Returns:
            True if the signature is valid, False otherwise.
        """
        if not self._public_key:
            raise ValueError(
                "Public key not loaded. Call generate_keys() or load_keys() first."
            )

        MlDsaType, _, MlDsaPublic = self._load_wolfcrypt()
        wc_type = getattr(MlDsaType, self._wc_type_name)

        # Only pass the meaningful bytes — strip any zero-padding
        actual_sig = signature[: self._sig_size]
        try:
            mldsa_pub = MlDsaPublic(wc_type)
            mldsa_pub.decode_key(self._public_key)
            return mldsa_pub.verify(actual_sig, data)
        except Exception as exc:
            print(f"ML-DSA signature verification failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_algorithm_name(self) -> str:
        return self.parameter_set

    @property
    def level(self) -> int:
        """wolfSSL dilithium level (2 or 3) for this parameter set."""
        return self._level

    @property
    def public_key_bytes(self) -> Optional[bytes]:
        """The raw public key bytes, or None if no key is loaded."""
        return self._public_key
