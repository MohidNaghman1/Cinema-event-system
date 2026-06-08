from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ConfigDict

from app.dependencies import get_current_user, get_db, require_role
from app.models.user import Role, User
from app.repositories.booking_repo import BookingRepository
from app.repositories.payment_repo import PaymentRepository
from app.repositories.user_repo import UserRepository
from app.schemas.booking import PaginatedResponse
from app.services.admin_service import AdminService

router = APIRouter(prefix="/api/v1/admin/users", tags=["Admin — Users"], responses={    401: {"description": "Unauthorized - Invalid or missing authentication token."},    403: {"description": "Forbidden - You do not have the required role permissions."},    422: {"description": "Unprocessable Entity - Schema validation error on the request payload."}})


def get_admin_service(db: AsyncIOMotorDatabase = Depends(get_db)) -> AdminService:
    return AdminService(
        user_repo=UserRepository(db),
        booking_repo=BookingRepository(db),
        payment_repo=PaymentRepository(db),
    )


class UserReadAdmin(BaseModel):
    id: UUID
    email: str
    full_name: str
    phone: Optional[str] = None
    role: Role
    is_active: bool
    is_verified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserProfileRead(UserReadAdmin):
    oauth_accounts: list[dict[str, Any]] = []
    booking_count: int = 0
    total_spend: Decimal = Decimal("0.00")
    last_login: Optional[datetime] = None


class ChangeRoleRequest(BaseModel):
    role: Role


@router.get(
    "",
    response_model=PaginatedResponse[UserReadAdmin],
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    role: Optional[Role] = None,
    is_active: Optional[bool] = None,
    sort_by: str = Query("created_at", pattern="^(created_at|full_name)$"),
    admin_service: AdminService = Depends(get_admin_service),
) -> PaginatedResponse[UserReadAdmin]:
    items_dict, total = await admin_service.user_repo.get_paginated_admin(
        skip=skip,
        limit=limit,
        search=search,
        role_filter=role.value if role else None,
        is_active=is_active,
        sort_by=sort_by,
    )
    items = [UserReadAdmin.model_validate(User(**item)) for item in items_dict]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.get(
    "/{id}",
    response_model=UserProfileRead,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def get_user_profile(
    id: UUID, admin_service: AdminService = Depends(get_admin_service)
) -> UserProfileRead:
    user_dict = await admin_service.user_repo.get_by_id(id)
    if not user_dict or user_dict.get("is_deleted"):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="User not found")

    stats = await admin_service.get_user_stats(id)
    user_obj = User(**user_dict)

    return UserProfileRead(
        **user_obj.model_dump(),
        booking_count=stats["booking_count"],
        total_spend=stats["total_spend"],
        last_login=stats["last_login"],
    )


@router.patch(
    "/{id}/ban",
    response_model=UserReadAdmin,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def ban_user(
    id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    admin_service: AdminService = Depends(get_admin_service),
) -> UserReadAdmin:
    user_dict = await admin_service.ban_user(current_user.id, id, background_tasks)
    return UserReadAdmin.model_validate(User(**user_dict))


@router.patch(
    "/{id}/unban",
    response_model=UserReadAdmin,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def unban_user(
    id: UUID,
    current_user: User = Depends(get_current_user),
    admin_service: AdminService = Depends(get_admin_service),
) -> UserReadAdmin:
    user_dict = await admin_service.unban_user(current_user.id, id)
    return UserReadAdmin.model_validate(User(**user_dict))


@router.patch(
    "/{id}/role",
    response_model=UserReadAdmin,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def change_role(
    id: UUID,
    data: ChangeRoleRequest,
    current_user: User = Depends(get_current_user),
    admin_service: AdminService = Depends(get_admin_service),
) -> UserReadAdmin:
    user_dict = await admin_service.change_role(current_user, id, data.role)
    return UserReadAdmin.model_validate(User(**user_dict))


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def delete_user(
    id: UUID,
    current_user: User = Depends(get_current_user),
    admin_service: AdminService = Depends(get_admin_service),
) -> None:
    await admin_service.delete_user(current_user.id, id)
