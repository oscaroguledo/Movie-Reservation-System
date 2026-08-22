import time
from datetime import timedelta

import pytest
from core.encryption import JWTHandler, PasswordHandler


class TestPasswordHandler:
    async def test_encrypt_produces_a_verifiable_hash_different_from_the_password(self):
        hashed = await PasswordHandler.encrypt("correct horse battery staple")

        assert hashed != "correct horse battery staple"
        assert await PasswordHandler.verify("correct horse battery staple", hashed) is True

    async def test_verify_rejects_wrong_password(self):
        hashed = await PasswordHandler.encrypt("correct horse battery staple")

        assert await PasswordHandler.verify("wrong password", hashed) is False

    async def test_verify_rejects_malformed_hash(self):
        assert await PasswordHandler.verify("anything", "not-a-real-hash") is False


class TestJWTHandler:
    async def test_encode_decode_roundtrip_preserves_payload(self):
        handler = JWTHandler()
        token = await handler.encode(
            {"sub": "user-1"}, secret_key="test-secret-key-long-enough-for-hs256"
        )

        decoded = await handler.decode(token, secret_key="test-secret-key-long-enough-for-hs256")

        assert decoded["sub"] == "user-1"
        assert "exp" in decoded

    async def test_default_expiration_is_applied(self):
        handler = JWTHandler(default_expiration_minutes=30)
        before = time.time()

        token = await handler.encode(
            {"sub": "user-1"}, secret_key="test-secret-key-long-enough-for-hs256"
        )
        decoded = await handler.decode(token, secret_key="test-secret-key-long-enough-for-hs256")

        assert 29 * 60 <= decoded["exp"] - before <= 31 * 60

    async def test_expires_delta_overrides_default_expiration(self):
        handler = JWTHandler(default_expiration_minutes=30)
        token = await handler.encode(
            {"sub": "user-1"},
            secret_key="test-secret-key-long-enough-for-hs256",
            expires_delta=timedelta(minutes=5),
        )

        decoded = await handler.decode(token, secret_key="test-secret-key-long-enough-for-hs256")

        assert decoded["exp"] - time.time() < 6 * 60

    async def test_decode_expired_token_raises_value_error(self):
        handler = JWTHandler()
        token = await handler.encode(
            {"sub": "user-1"},
            secret_key="test-secret-key-long-enough-for-hs256",
            expires_delta=timedelta(minutes=-1),
        )

        with pytest.raises(ValueError, match="Token has expired"):
            await handler.decode(token, secret_key="test-secret-key-long-enough-for-hs256")

    async def test_decode_with_wrong_secret_raises_value_error(self):
        handler = JWTHandler()
        token = await handler.encode(
            {"sub": "user-1"}, secret_key="test-secret-key-long-enough-for-hs256"
        )

        with pytest.raises(ValueError, match="Invalid token"):
            await handler.decode(token, secret_key="a-different-wrong-secret-key-value")

    async def test_decode_garbage_token_raises_value_error(self):
        handler = JWTHandler()

        with pytest.raises(ValueError, match="Invalid token"):
            await handler.decode("not-a-jwt", secret_key="test-secret-key-long-enough-for-hs256")
