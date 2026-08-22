import time

import pytest
from core.encryption import JWTHandler, PasswordHandler


class TestPasswordHandler:
    def test_encrypt_produces_a_verifiable_hash_different_from_the_password(self):
        hashed = PasswordHandler.encrypt("correct horse battery staple")

        assert hashed != "correct horse battery staple"
        assert PasswordHandler.verify("correct horse battery staple", hashed) is True

    def test_verify_rejects_wrong_password(self):
        hashed = PasswordHandler.encrypt("correct horse battery staple")

        assert PasswordHandler.verify("wrong password", hashed) is False

    def test_verify_rejects_malformed_hash(self):
        assert PasswordHandler.verify("anything", "not-a-real-hash") is False


class TestJWTHandler:
    def test_encode_decode_roundtrip_preserves_payload(self):
        handler = JWTHandler()
        token = handler.encode(
            {"sub": "user-1"}, secret_key="test-secret-key-long-enough-for-hs256"
        )

        decoded = handler.decode(token, secret_key="test-secret-key-long-enough-for-hs256")

        assert decoded["sub"] == "user-1"
        assert "exp" in decoded

    def test_default_expiration_is_applied(self):
        handler = JWTHandler(default_expiration_minutes=30)
        before = time.time()

        token = handler.encode(
            {"sub": "user-1"}, secret_key="test-secret-key-long-enough-for-hs256"
        )
        decoded = handler.decode(token, secret_key="test-secret-key-long-enough-for-hs256")

        assert 29 * 60 <= decoded["exp"] - before <= 31 * 60

    def test_expires_delta_overrides_default_expiration(self):
        from datetime import timedelta

        handler = JWTHandler(default_expiration_minutes=30)
        token = handler.encode(
            {"sub": "user-1"},
            secret_key="test-secret-key-long-enough-for-hs256",
            expires_delta=timedelta(minutes=5),
        )

        decoded = handler.decode(token, secret_key="test-secret-key-long-enough-for-hs256")

        assert decoded["exp"] - time.time() < 6 * 60

    def test_decode_expired_token_raises_value_error(self):
        from datetime import timedelta

        handler = JWTHandler()
        token = handler.encode(
            {"sub": "user-1"},
            secret_key="test-secret-key-long-enough-for-hs256",
            expires_delta=timedelta(minutes=-1),
        )

        with pytest.raises(ValueError, match="Token has expired"):
            handler.decode(token, secret_key="test-secret-key-long-enough-for-hs256")

    def test_decode_with_wrong_secret_raises_value_error(self):
        handler = JWTHandler()
        token = handler.encode(
            {"sub": "user-1"}, secret_key="test-secret-key-long-enough-for-hs256"
        )

        with pytest.raises(ValueError, match="Invalid token"):
            handler.decode(token, secret_key="a-different-wrong-secret-key-value")

    def test_decode_garbage_token_raises_value_error(self):
        handler = JWTHandler()

        with pytest.raises(ValueError, match="Invalid token"):
            handler.decode("not-a-jwt", secret_key="test-secret-key-long-enough-for-hs256")
