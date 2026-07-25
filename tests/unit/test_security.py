# Unit tests for security module

import pytest
from uuid import uuid4

from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    TokenData,
)


class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_password_hashing(self):
        """Test password hashing produces different hash each time."""
        password = "TestPassword123!"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != password
        assert hash2 != password
        assert hash1 != hash2  # Different salts

    def test_password_verification(self):
        """Test password verification works correctly."""
        password = "TestPassword123!"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed)
        assert not verify_password("WrongPassword", hashed)
        assert not verify_password("", hashed)

    def test_empty_password(self):
        """Test empty password handling."""
        password = ""
        hashed = get_password_hash(password)
        assert verify_password(password, hashed)

    def test_special_characters_password(self):
        """Test password with special characters."""
        password = "P@ssw0rd!#$%^&*()"
        hashed = get_password_hash(password)
        assert verify_password(password, hashed)


class TestTokenCreation:
    """Test JWT token creation and decoding."""

    def test_create_access_token(self):
        """Test access token creation."""
        user_id = uuid4()
        token = create_access_token(subject=str(user_id))

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self):
        """Test refresh token creation."""
        user_id = uuid4()
        token = create_refresh_token(subject=str(user_id))

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_access_token(self):
        """Test decoding access token."""
        user_id = uuid4()
        token = create_access_token(subject=str(user_id))

        payload = decode_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    def test_decode_refresh_token(self):
        """Test decoding refresh token."""
        user_id = uuid4()
        token = create_refresh_token(subject=str(user_id))

        payload = decode_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["type"] == "refresh"
        assert "exp" in payload
        assert "iat" in payload

    def test_token_expiration(self):
        """Test token expiration handling."""
        from datetime import timedelta
        from app.core.security import create_access_token, decode_token
        import jwt

        user_id = uuid4()
        # Create token that expires immediately
        token = create_access_token(subject=str(user_id), expires_delta=timedelta(seconds=-1))

        # Should raise exception for expired token
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_token(token)

    def test_invalid_token(self):
        """Test invalid token handling."""
        import jwt

        with pytest.raises(jwt.InvalidTokenError):
            decode_token("invalid.token.string")

    def test_token_data_model(self):
        """Test TokenData model."""
        user_id = uuid4()
        token_data = TokenData(sub=str(user_id), type="access")

        assert token_data.sub == str(user_id)
        assert token_data.type == "access"