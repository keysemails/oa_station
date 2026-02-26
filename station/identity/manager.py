"""
Station Identity Manager - Ed25519 keypair generation and signing.

Uses PyNaCl (libsodium bindings) for Ed25519 operations.
The public key serves as the station's immutable cryptographic ID.

SECURITY: Private key is encrypted at rest using STATION_ENCRYPTION_KEY.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError
from cryptography.fernet import Fernet
from loguru import logger


class StationIdentity:
    """
    Manages Ed25519 keypair for station authentication.
    
    - Public key (64 hex chars) = Station ID
    - Private key stored on disk encrypted, never transmitted
    - All outbound requests signed for authentication
    
    SECURITY: Private key is encrypted using STATION_ENCRYPTION_KEY environment variable.
    """
    
    def __init__(self, identity_file: str = "identity.json", encryption_key: Optional[str] = None):
        """
        Initialize identity manager.
        
        Args:
            identity_file: Path to store/load the keypair (relative to cwd or absolute)
            encryption_key: Optional encryption key for private key at rest
        """
        self.identity_file = Path(identity_file)
        self._signing_key: Optional[SigningKey] = None
        
        # Get encryption key from parameter or environment
        self._encryption_key = encryption_key or os.getenv("STATION_ENCRYPTION_KEY")
        self._cipher = None
        if self._encryption_key:
            try:
                self._cipher = Fernet(self._encryption_key.encode() if isinstance(self._encryption_key, str) else self._encryption_key)
            except Exception as e:
                logger.warning(f"Invalid encryption key format, identity will not be encrypted: {e}")
    
    @property
    def public_key_hex(self) -> str:
        """Get public key as hex string (64 chars). This is the station ID."""
        if not self._signing_key:
            raise RuntimeError("Identity not loaded. Call load_or_create() first.")
        return self._signing_key.verify_key.encode().hex()
    
    @property
    def is_loaded(self) -> bool:
        """Check if identity is loaded."""
        return self._signing_key is not None
    
    def sign_payload(self, payload: dict) -> str:
        """
        Sign a JSON payload with the private key.
        
        Args:
            payload: Dictionary to sign (will be JSON-serialized deterministically)
            
        Returns:
            Hex-encoded signature (128 chars)
        """
        if not self._signing_key:
            raise RuntimeError("Identity not loaded. Call load_or_create() first.")
        
        # Deterministic JSON serialization for consistent signatures
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
        signed = self._signing_key.sign(payload_bytes)
        return signed.signature.hex()
    
    def sign_bytes(self, data: bytes) -> bytes:
        """
        Sign raw bytes with the private key.
        
        Args:
            data: Raw bytes to sign
            
        Returns:
            Raw signature bytes (64 bytes)
        """
        if not self._signing_key:
            raise RuntimeError("Identity not loaded. Call load_or_create() first.")
        signed = self._signing_key.sign(data)
        return signed.signature
    
    def load_or_create(self) -> str:
        """
        Load existing keypair or generate new one.
        
        Returns:
            Public key hex string (station ID)
        """
        if self.identity_file.exists():
            return self._load_existing()
        else:
            return self._create_new()
    
    def _load_existing(self) -> str:
        """Load existing keypair from disk (decrypting if necessary)."""
        try:
            data = json.loads(self.identity_file.read_text())
            
            # Check if private key is encrypted
            if data.get("encrypted", False):
                if not self._cipher:
                    raise RuntimeError(
                        "Identity file is encrypted but STATION_ENCRYPTION_KEY not set. "
                        "Set the encryption key used when creating this identity."
                    )
                # Decrypt private key
                encrypted_key = data["private_key"]
                seed_hex = self._cipher.decrypt(encrypted_key.encode()).decode()
            else:
                seed_hex = data["private_key"]
                # Warn about unencrypted identity (legacy)
                logger.warning(
                    "Identity file is not encrypted. Consider regenerating with "
                    "STATION_ENCRYPTION_KEY set for security."
                )
            
            seed_bytes = bytes.fromhex(seed_hex)
            self._signing_key = SigningKey(seed_bytes)
            
            # Verify stored public key matches derived one
            stored_public = data.get("public_key", "")
            derived_public = self.public_key_hex
            if stored_public and stored_public != derived_public:
                logger.warning("Stored public key doesn't match derived key - using derived")
            
            logger.info(f"Loaded station identity from {self.identity_file}")
            logger.info(f"Station ID: {derived_public[:16]}...{derived_public[-8:]}")
            return derived_public
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to load identity file: {e}")
            raise RuntimeError(f"Invalid identity file: {self.identity_file}") from e
    
    def _create_new(self) -> str:
        """Generate new keypair and save to disk (encrypted if key available)."""
        self._signing_key = SigningKey.generate()
        
        # Get seed bytes (32 bytes) - this is what we store
        seed_bytes = bytes(self._signing_key)
        public_key = self.public_key_hex
        
        # Ensure parent directory exists
        self.identity_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Encrypt private key if encryption key is available
        if self._cipher:
            encrypted_key = self._cipher.encrypt(seed_bytes.hex().encode()).decode()
            identity_data = {
                "private_key": encrypted_key,
                "public_key": public_key,
                "created_at": int(time.time()),
                "encrypted": True
            }
            logger.info("Private key will be encrypted at rest")
        else:
            identity_data = {
                "private_key": seed_bytes.hex(),
                "public_key": public_key,
                "created_at": int(time.time()),
                "encrypted": False
            }
            logger.warning(
                "STATION_ENCRYPTION_KEY not set - private key stored unencrypted. "
                "Set this environment variable for production security."
            )
        
        # Write file with restrictive permissions from the start (avoid TOCTOU race)
        fd = os.open(str(self.identity_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, json.dumps(identity_data, indent=2).encode())
        finally:
            os.close(fd)
        
        logger.info(f"Generated new station identity: {self.identity_file}")
        logger.info(f"Station ID: {public_key[:16]}...{public_key[-8:]}")
        logger.warning("Back up your identity.json file! Loss means new identity required.")
        
        return public_key
    
    @staticmethod
    def verify_signature(public_key_hex: str, payload: dict, signature_hex: str) -> bool:
        """
        Verify a signature (utility method for testing).
        
        Args:
            public_key_hex: Signer's public key
            payload: Original payload dict
            signature_hex: Signature to verify
            
        Returns:
            True if valid, False otherwise
        """
        try:
            verify_key = VerifyKey(bytes.fromhex(public_key_hex))
            payload_bytes = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
            signature = bytes.fromhex(signature_hex)
            verify_key.verify(payload_bytes, signature)
            return True
        except BadSignatureError:
            return False
        except Exception:
            return False
