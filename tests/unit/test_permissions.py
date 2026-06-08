import uuid

import pytest
from fastapi import HTTPException

from app.core.permissions import (
    CREATE_EVENT,
    ISSUE_REFUND,
    VIEW_EVENT,
    has_permission,
    require_any_permission,
    require_owner_or_admin,
    require_permission,
)
from app.models.user import Role, User


def test_has_permission():
    user_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    super_id = uuid.uuid4()

    user = User(id=user_id, email="user@example.com", role=Role.USER, full_name="User")
    admin = User(id=admin_id, email="admin@example.com", role=Role.ADMIN, full_name="Admin")
    super_admin = User(
        id=super_id, email="super@example.com", role=Role.SUPER_ADMIN, full_name="Super"
    )

    # USER role
    assert has_permission(user, VIEW_EVENT) is True
    assert has_permission(user, CREATE_EVENT) is False
    assert has_permission(user, ISSUE_REFUND) is False

    # ADMIN role
    assert has_permission(admin, CREATE_EVENT) is True
    assert has_permission(admin, ISSUE_REFUND) is False

    # SUPER_ADMIN role
    assert has_permission(super_admin, ISSUE_REFUND) is True


def test_require_permission_success():
    admin = User(
        id=uuid.uuid4(), email="admin@example.com", role=Role.ADMIN, full_name="Admin"
    )
    checker = require_permission(CREATE_EVENT)
    assert checker(current_user=admin) == admin


def test_require_permission_failure():
    user = User(
        id=uuid.uuid4(), email="user@example.com", role=Role.USER, full_name="User"
    )
    checker = require_permission(CREATE_EVENT)
    with pytest.raises(HTTPException) as exc_info:
        checker(current_user=user)
    assert exc_info.value.status_code == 403


def test_require_any_permission():
    user = User(
        id=uuid.uuid4(), email="user@example.com", role=Role.USER, full_name="User"
    )
    # User has VIEW_EVENT but not CREATE_EVENT
    checker = require_any_permission(CREATE_EVENT, VIEW_EVENT)
    assert checker(current_user=user) == user

    # User has neither
    checker_fail = require_any_permission(CREATE_EVENT, ISSUE_REFUND)
    with pytest.raises(HTTPException) as exc_info:
        checker_fail(current_user=user)
    assert exc_info.value.status_code == 403


def test_require_owner_or_admin():
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    owner = User(id=owner_id, email="owner@example.com", role=Role.USER, full_name="Owner")
    other = User(id=other_id, email="other@example.com", role=Role.USER, full_name="Other")
    admin = User(id=admin_id, email="admin@example.com", role=Role.ADMIN, full_name="Admin")

    # Dependency factory just wraps the resource ID fetching func.
    # In test, we can pass the evaluated resource ID directly to the inner func
    checker = require_owner_or_admin(lambda: str(owner_id))

    # Owner should succeed
    assert checker(resource_owner_id=str(owner_id), current_user=owner) == owner

    # Admin should succeed even if not owner
    assert checker(resource_owner_id=str(owner_id), current_user=admin) == admin

    # Other user should fail
    with pytest.raises(HTTPException) as exc_info:
        checker(resource_owner_id=str(owner_id), current_user=other)
    assert exc_info.value.status_code == 403
