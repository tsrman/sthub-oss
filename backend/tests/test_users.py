import uuid

import pytest

from app.api.users import get_me
from app.models.user import User


def test_user_model_allows_duplicate_username():
    """``username`` no longer has a unique constraint or unique index."""
    index_names = {idx.name for idx in User.__table__.indexes}
    assert "ix_users_username" not in index_names

    constraint_names = {
        c.name for c in User.__table__.constraints if hasattr(c, "name")
    }
    assert "users_username_key" not in constraint_names

    # Login uniqueness is still enforced.
    assert "uq_users_login" in constraint_names


@pytest.mark.asyncio
async def test_get_me_returns_first_allowed_group():
    user = User(
        id=uuid.uuid4(),
        login="alice",
        username="Alice A",
        email="alice@example.com",
    )
    claims = {"groups": ["streamlit-users", "streamlit-admins"]}

    response = await get_me(current=(user.id, user.login, user, claims))

    assert response.login == "alice"
    assert response.display_name == "Alice A"
    assert response.email == "alice@example.com"
    assert response.group == "streamlit-users"


@pytest.mark.asyncio
async def test_get_me_no_allowed_group_returns_empty_group():
    user = User(
        id=uuid.uuid4(),
        login="bob",
        username="Bob",
        email=None,
    )
    claims = {"groups": ["other-group"]}

    response = await get_me(current=(user.id, user.login, user, claims))

    assert response.login == "bob"
    assert response.display_name == "Bob"
    assert response.email == ""
    assert response.group == ""


@pytest.mark.asyncio
async def test_get_me_no_groups_returns_empty_group():
    user = User(
        id=uuid.uuid4(),
        login="carol",
        username="Carol",
        email="carol@example.com",
    )
    claims = {}

    response = await get_me(current=(user.id, user.login, user, claims))

    assert response.group == ""
