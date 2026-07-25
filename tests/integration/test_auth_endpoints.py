# Integration tests for authentication endpoints

import pytest
from httpx import AsyncClient
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.models.user import User


class TestAuthEndpoints:
    """Test authentication endpoints."""

    @pytest.fixture
    async def client(self):
        """Create test client."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client

    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        user = MagicMock(spec=User)
        user.id = uuid4()
        user.email = "test@example.com"
        user.full_name = "Test User"
        user.is_active = True
        user.is_superuser = False
        user.hashed_password = "hashed_password"
        return user

    @pytest.mark.asyncio
    async def test_register_user(self, client, mock_user):
        """Test user registration."""
        with patch('app.api.v1.endpoints.auth.get_user_by_email', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = None
            with patch('app.api.v1.endpoints.auth.create_user', new_callable=AsyncMock) as mock_create_user:
                mock_create_user.return_value = mock_user

                response = await client.post(
                    "/api/v1/auth/register",
                    json={
                        "email": "test@example.com",
                        "password": "TestPassword123!",
                        "full_name": "Test User"
                    }
                )

                assert response.status_code == 201
                data = response.json()
                assert data["email"] == "test@example.com"
                assert data["full_name"] == "Test User"
                assert "id" in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client, mock_user):
        """Test registration with duplicate email."""
        with patch('app.api.v1.endpoints.auth.get_user_by_email', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user

            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "test@example.com",
                    "password": "TestPassword123!",
                    "full_name": "Test User"
                }
            )

            assert response.status_code == 400
            assert "already registered" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_success(self, client, mock_user):
        """Test successful login."""
        with patch('app.api.v1.endpoints.auth.authenticate_user', new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = mock_user
            with patch('app.api.v1.endpoints.auth.create_access_token') as mock_create_access:
                mock_create_access.return_value = "access_token"
                with patch('app.api.v1.endpoints.auth.create_refresh_token') as mock_create_refresh:
                    mock_create_refresh.return_value = "refresh_token"

                    response = await client.post(
                        "/api/v1/auth/login",
                        data={
                            "username": "test@example.com",
                            "password": "TestPassword123!"
                        }
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert "access_token" in data
                    assert "refresh_token" in data
                    assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials."""
        with patch('app.api.v1.endpoints.auth.authenticate_user', new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = None

            response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": "test@example.com",
                    "password": "WrongPassword"
                }
            )

            assert response.status_code == 401
            assert "incorrect" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_refresh_token(self, client, mock_user):
        """Test token refresh."""
        with patch('app.api.v1.endpoints.auth.decode_token') as mock_decode:
            mock_decode.return_value = {"sub": str(mock_user.id), "type": "refresh"}
            with patch('app.api.v1.endpoints.auth.get_user_by_id', new_callable=AsyncMock) as mock_get_user:
                mock_get_user.return_value = mock_user
                with patch('app.api.v1.endpoints.auth.create_access_token') as mock_create_access:
                    mock_create_access.return_value = "new_access_token"
                    with patch('app.api.v1.endpoints.auth.create_refresh_token') as mock_create_refresh:
                        mock_create_refresh.return_value = "new_refresh_token"

                        response = await client.post(
                            "/api/v1/auth/refresh",
                            json={"refresh_token": "valid_refresh_token"}
                        )

                        assert response.status_code == 200
                        data = response.json()
                        assert "access_token" in data
                        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_refresh_token_invalid(self, client):
        """Test refresh with invalid token."""
        with patch('app.api.v1.endpoints.auth.decode_token') as mock_decode:
            mock_decode.return_value = None

            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "invalid_token"}
            )

            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user(self, client, mock_user):
        """Test getting current user info."""
        with patch('app.api.v1.endpoints.auth.get_current_user', new_callable=AsyncMock) as mock_get_current:
            mock_get_current.return_value = mock_user

            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer valid_token"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["email"] == "test@example.com"
            assert data["full_name"] == "Test User"

    @pytest.mark.asyncio
    async def test_get_current_user_unauthorized(self, client):
        """Test getting current user without auth."""
        response = await client.get("/api/v1/auth/me")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_logout(self, client):
        """Test logout."""
        response = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": "Bearer valid_token"}
        )

        assert response.status_code == 200
        assert "successfully logged out" in response.json()["message"].lower()