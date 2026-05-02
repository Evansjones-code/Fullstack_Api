import pytest
from httpx import AsyncClient
from tests.conftest import auth_header, create_test_user, login_user

@pytest.mark.anyio
async def test_get_posts_empty(client: AsyncClient):
    response = await client.get("/api/posts")
    assert response.status_code == 200
    data = response.json()
    assert data["posts"] == []
    assert data["total"] == 0
    assert data["has_more"] is False

@pytest.mark.anyio
async def test_get_post_not_found(client: AsyncClient):
    response = await client.get("/api/posts/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Post not found"

@pytest.mark.anyio
async def test_create_post_success(client: AsyncClient):
    # 1. Create user and extract JSON data
    user_res = await create_test_user(client)
    user_data = user_res.json()
    
    # 2. Login to get token
    token = await login_user(client)
    headers = auth_header(token)

    # 3. Create the post
    response = await client.post(
        "/api/posts",
        json={"title": "My First Post", "content": "This is the content"},
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "My First Post"
    assert data["user_id"] == user_data["id"]
    assert data["author"]["username"] == "testuser"

@pytest.mark.anyio
async def test_create_post_unauthorized(client: AsyncClient):
    response = await client.post(
        "/api/posts",
        json={"title": "Test Post", "content": "Test content"},
    )
    # Should fail because no Authorization header is provided
    assert response.status_code == 401

@pytest.mark.anyio
async def test_update_post_success(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    # Create post first
    create_res = await client.post(
        "/api/posts",
        json={"title": "Original Title", "content": "Original content"},
        headers=headers,
    )
    post_id = create_res.json()["id"]

    # Patch the post
    response = await client.patch(
        f"/api/posts/{post_id}",
        json={"title": "Updated Title"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"

@pytest.mark.anyio
async def test_update_post_wrong_user(client: AsyncClient):
    # User 1 creates a post
    await create_test_user(client, username="user1", email="user1@example.com")
    token1 = await login_user(client, email="user1@example.com")

    post_res = await client.post(
        "/api/posts",
        json={"title": "User 1's Post", "content": "Content"},
        headers=auth_header(token1),
    )
    post_id = post_res.json()["id"]

    # User 2 tries to edit User 1's post
    await create_test_user(client, username="user2", email="user2@example.com")
    token2 = await login_user(client, email="user2@example.com")

    response = await client.patch(
        f"/api/posts/{post_id}",
        json={"title": "Hacked Title"},
        headers=auth_header(token2),
    )
    assert response.status_code == 403

@pytest.mark.anyio
async def test_get_posts_with_pagination(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    # Create 5 posts
    for i in range(5):
        await client.post(
            "/api/posts",
            json={"title": f"Post {i}", "content": "Content"},
            headers=headers,
        )

    # Test limit=2
    response = await client.get("/api/posts?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["posts"]) == 2
    assert data["has_more"] is True
    assert data["total"] == 5
