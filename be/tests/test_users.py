"""
Integration tests for GET /users/me.
"""

from httpx import AsyncClient

from tests.fakes import TEST_USER_ID, auth_headers


async def test_me_returns_sub(client: AsyncClient) -> None:
    resp = await client.get("/users/me", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["sub"] == TEST_USER_ID


async def test_me_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/users/me")
    assert resp.status_code == 401


async def test_me_different_users_return_own_sub(client: AsyncClient) -> None:
    uid_a = "00000000-0000-0000-0000-000000000001"
    uid_b = "00000000-0000-0000-0000-000000000002"
    assert (await client.get("/users/me", headers=auth_headers(uid_a))).json()["sub"] == uid_a
    assert (await client.get("/users/me", headers=auth_headers(uid_b))).json()["sub"] == uid_b
