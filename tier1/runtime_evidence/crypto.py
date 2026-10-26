from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature


class RunnerKeyStore:
    def __init__(self, root: Path):
        self.root = root
        self.private_path = root / "runner-ed25519-private.pem"
        self.public_path = root / "runner-ed25519-public.pem"

    def _private(self) -> Ed25519PrivateKey:
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.private_path.exists():
            key = Ed25519PrivateKey.generate()
            self.private_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            self.public_path.write_bytes(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        return serialization.load_pem_private_key(self.private_path.read_bytes(), password=None)

    def ensure_keypair(self) -> bytes:
        self._private()
        return self.public_key_bytes()

    def public_key_bytes(self) -> bytes:
        self._private()
        return self.public_path.read_bytes()

    def sign(self, payload: bytes) -> str:
        return "ed25519:" + self._private().sign(payload).hex()


def verify_signature(payload: bytes, signature: str, public_key: bytes) -> bool:
    if not signature.startswith("ed25519:"):
        return False
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(bytes.fromhex(signature[8:]), payload)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
