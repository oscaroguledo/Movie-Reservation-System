from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Initialize a global PasswordHasher instance using default Argon2id parameters
ph = PasswordHasher()

class PasswordHandler:
    @staticmethod
    def encrypt(password: str) -> str:
        """Hashes a plain text password using Argon2id."""
        return ph.hash(password)

    @staticmethod
    def verify(password: str, hashed_password: str) -> bool:
        """Verifies a plain text password against an Argon2id hash."""
        try:
            return ph.verify(hashed_password, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False


class JWTHandler:
    def __init__(self, default_expiration_minutes: int = 30):
        self.default_expiration_minutes = default_expiration_minutes

    def encode(
        self,
        payload: dict,
        secret_key: str,
        algorithm: str = "HS256",
        expires_delta: timedelta | None = None
    ) -> str:
        """
        Encodes a payload dictionary into a JWT token string with an 'exp' claim.
        """
        to_encode = payload.copy()
        
        # Calculate expiration timestamp using UTC
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=self.default_expiration_minutes)
            
        to_encode.update({"exp": expire})
        
        token = jwt.encode(to_encode, secret_key, algorithm=algorithm)
        return token

    def decode(
        self,
        token: str,
        secret_key: str,
        algorithms: list[str] | None = None,
        verify_exp: bool = True
    ) -> dict:
        """
        Decodes and validates a JWT token string.
        """
        if algorithms is None:
            algorithms = ["HS256"]
            
        options = {"verify_exp": verify_exp}

        try:
            decoded_payload = jwt.decode(
                token,
                secret_key,
                algorithms=algorithms,
                options=options
            )
            return decoded_payload
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")