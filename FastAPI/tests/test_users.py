from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image
from httpx import AsyncClient

from tests.conftest import auth_header, create_test_user, login_user

@pytest.mark.anyio
async def test_create_user_validation_error(client: AsyncClient):
    response = await client.post(
        "/api/users",
        json={"username": "testuser"},
    )
    assert response.status_code == 422
    assert "email" in response.text
    assert "password" in response.text

@pytest.mark.anyio
async def test_create_user_duplicate_email(client: AsyncClient):
    await create_test_user(client)

    response = await client.post(
        "/api/users",
        json={
            "username": "different_user",
            "email": "test@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"

@pytest.mark.anyio
async def test_create_user_success(client: AsyncClient):
    response = await client.post(
        "/api/users",
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "securepassword123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "newuser"
    assert "id" in data

@pytest.mark.anyio
async def test_upload_profile_picture(client: AsyncClient, mocked_aws):
    # 1. Create user and login
    user_res = await create_test_user(client)
    user_data = user_res.json() 
    token = await login_user(client)

    # 2. Generate a valid 1x1 JPEG image in memory to avoid "Invalid image format" (400)
    file_obj = BytesIO()
    image = Image.new("RGB", (1, 1), color="red")
    image.save(file_obj, format="JPEG")
    file_obj.seek(0)

    # 3. Perform the patch request
    response = await client.patch(
        "/api/users/me/image",
        files={"file": ("profile.jpg", file_obj, "image/jpeg")},
        headers=auth_header(token),
    )

    # 4. Assertions
    assert response.status_code == 200
    data = response.json()
    assert data["image_file"] is not None
    assert "s3" in data["image_path"]

@pytest.mark.anyio
async def test_forgot_password_sends_email(client: AsyncClient):
    await create_test_user(client)

    with patch(
        "routers.users.send_password_reset_email",
        new_callable=AsyncMock,
    ) as mock_send:
        response = await client.post(
            "/api/users/forgot-password",
            json={"email": "test@example.com"},
        )

        assert response.status_code == 202
        mock_send.assert_awaited_once()
        
        _, kwargs = mock_send.call_args
        assert kwargs["to_email"] == "test@example.com"
        assert kwargs["username"] == "testuser"
