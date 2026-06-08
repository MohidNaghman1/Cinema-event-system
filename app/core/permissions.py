from typing import Any, Callable

from fastapi import Depends, HTTPException, status

from app.models.user import Role, User

# Event Permissions
CREATE_EVENT = "CREATE_EVENT"
EDIT_EVENT = "EDIT_EVENT"
DELETE_EVENT = "DELETE_EVENT"
PUBLISH_EVENT = "PUBLISH_EVENT"
VIEW_EVENT = "VIEW_EVENT"

# Booking Permissions
CREATE_BOOKING = "CREATE_BOOKING"
CANCEL_BOOKING = "CANCEL_BOOKING"
VIEW_OWN_BOOKINGS = "VIEW_OWN_BOOKINGS"
VIEW_ALL_BOOKINGS = "VIEW_ALL_BOOKINGS"

# User Permissions
VIEW_OWN_PROFILE = "VIEW_OWN_PROFILE"
EDIT_OWN_PROFILE = "EDIT_OWN_PROFILE"
MANAGE_USERS = "MANAGE_USERS"

# Payment Permissions
VIEW_OWN_PAYMENTS = "VIEW_OWN_PAYMENTS"
VIEW_ALL_PAYMENTS = "VIEW_ALL_PAYMENTS"
ISSUE_REFUND = "ISSUE_REFUND"

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.USER: {
        VIEW_EVENT,
        CREATE_BOOKING,
        CANCEL_BOOKING,
        VIEW_OWN_BOOKINGS,
        VIEW_OWN_PROFILE,
        EDIT_OWN_PROFILE,
        VIEW_OWN_PAYMENTS,
    },
    Role.ADMIN: {
        VIEW_EVENT,
        CREATE_EVENT,
        EDIT_EVENT,
        PUBLISH_EVENT,
        CREATE_BOOKING,
        CANCEL_BOOKING,
        VIEW_OWN_BOOKINGS,
        VIEW_ALL_BOOKINGS,
        VIEW_OWN_PROFILE,
        EDIT_OWN_PROFILE,
        VIEW_OWN_PAYMENTS,
        VIEW_ALL_PAYMENTS,
    },
    Role.SUPER_ADMIN: {
        CREATE_EVENT,
        EDIT_EVENT,
        DELETE_EVENT,
        PUBLISH_EVENT,
        VIEW_EVENT,
        CREATE_BOOKING,
        CANCEL_BOOKING,
        VIEW_OWN_BOOKINGS,
        VIEW_ALL_BOOKINGS,
        VIEW_OWN_PROFILE,
        EDIT_OWN_PROFILE,
        MANAGE_USERS,
        VIEW_OWN_PAYMENTS,
        VIEW_ALL_PAYMENTS,
        ISSUE_REFUND,
    },
}


def has_permission(user: User, permission: str) -> bool:
    """Check if a user has a specific permission based on their role."""
    if not user or not user.role:
        return False
    return permission in ROLE_PERMISSIONS.get(user.role, set())


def require_permission(permission: str) -> Callable[[User], User]:
    """Dependency that ensures the user has a specific permission."""
    from app.dependencies import get_current_active_user

    def permission_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if not has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
            )
        return current_user

    return permission_checker


def require_any_permission(*permissions: str) -> Callable[[User], User]:
    """Dependency that ensures the user has at least one of the specified permissions."""
    from app.dependencies import get_current_active_user

    def permission_checker(current_user: User = Depends(get_current_active_user)) -> User:
        for perm in permissions:
            if has_permission(current_user, perm):
                return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permissions"
        )

    return permission_checker


def require_owner_or_admin(
    get_resource_owner_id: Callable[..., Any]
) -> Callable[..., User]:
    """Dependency that allows access if user owns the resource or is an admin."""
    from app.dependencies import get_current_active_user

    def permission_checker(
        resource_owner_id: Any = Depends(get_resource_owner_id),
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if current_user.role in (Role.ADMIN, Role.SUPER_ADMIN):
            return current_user

        if str(current_user.id) == str(resource_owner_id):
            return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resource",
        )

    return permission_checker
