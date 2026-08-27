import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Initialize a global PasswordHasher instance using default Argon2id parameters
ph = PasswordHasher()


class PasswordHandler:
    @staticmethod
    async def encrypt(password: str) -> str:
        """Hashes a password with Argon2id, in a worker thread since it's
        deliberately slow (tens to hundreds of ms)."""
        return await asyncio.to_thread(ph.hash, password)

    @staticmethod
    async def verify(password: str, hashed_password: str) -> bool:
        """Verifies a plain text password against an Argon2id hash."""
        try:
            return await asyncio.to_thread(ph.verify, hashed_password, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False


class JWTHandler:
    def __init__(self, default_expiration_minutes: int = 30):
        self.default_expiration_minutes = default_expiration_minutes

    async def encode(
        self,
        payload: dict,
        secret_key: str,
        algorithm: str = "HS256",
        expires_delta: timedelta | None = None,
    ) -> str:
        """Encodes a payload dict into a JWT with 'exp' and 'jti' claims."""
        to_encode = payload.copy()

        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=self.default_expiration_minutes)

        to_encode.setdefault("jti", str(uuid4()))
        to_encode.update({"exp": expire})

        return await asyncio.to_thread(jwt.encode, to_encode, secret_key, algorithm=algorithm)

    async def decode(
        self,
        token: str,
        secret_key: str,
        algorithms: list[str] | None = None,
        verify_exp: bool = True,
    ) -> dict:
        """Decodes and validates a JWT token string."""
        if algorithms is None:
            algorithms = ["HS256"]

        options = {"verify_exp": verify_exp}

        try:
            return await asyncio.to_thread(
                jwt.decode, token, secret_key, algorithms=algorithms, options=options
            )
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")
