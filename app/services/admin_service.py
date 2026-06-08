from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException

from app.core.security import redis_client
from app.models.user import Role, User
from app.repositories.booking_repo import BookingRepository
from app.repositories.payment_repo import PaymentRepository
from app.repositories.user_repo import UserRepository


async def send_notification_email(user_email: str, subject: str, message: str) -> None:
    print(f"[BACKGROUND] Email to {user_email}: {subject} - {message}")


class AdminService:
    def __init__(
        self,
        user_repo: UserRepository,
        booking_repo: BookingRepository,
        payment_repo: PaymentRepository,
    ) -> None:
        self.user_repo = user_repo
        self.booking_repo = booking_repo
        self.payment_repo = payment_repo

    async def ban_user(
        self, admin_id: UUID, user_id: UUID, background_tasks: BackgroundTasks
    ) -> dict[str, Any]:
        user_dict = await self.user_repo.get_by_id(user_id)
        if not user_dict or user_dict.get("is_deleted"):
            raise HTTPException(status_code=404, detail="User not found")

        await self.user_repo.update(user_id, {"is_active": False})
        user_dict["is_active"] = False

        # Revoke all active tokens by setting a global ban timestamp marker in Redis
        await redis_client.set(f"banned_user:{user_id}", "true")

        print(f"[AUDIT] Admin {admin_id} banned user {user_id}")

        background_tasks.add_task(
            send_notification_email,
            user_dict["email"],
            "Account Suspended",
            "Your account has been suspended by an administrator.",
        )
        return user_dict

    async def unban_user(self, admin_id: UUID, user_id: UUID) -> dict[str, Any]:
        user_dict = await self.user_repo.get_by_id(user_id)
        if not user_dict or user_dict.get("is_deleted"):
            raise HTTPException(status_code=404, detail="User not found")

        await self.user_repo.update(user_id, {"is_active": True})
        user_dict["is_active"] = True

        await redis_client.delete(f"banned_user:{user_id}")

        print(f"[AUDIT] Admin {admin_id} unbanned user {user_id}")
        return user_dict

    async def change_role(
        self, admin_user: User, target_user_id: UUID, new_role: Role
    ) -> dict[str, Any]:
        if (
            new_role in (Role.ADMIN, Role.SUPER_ADMIN)
            and admin_user.role != Role.SUPER_ADMIN
        ):
            raise HTTPException(
                status_code=403, detail="Only SUPER_ADMIN can assign ADMIN/SUPER_ADMIN roles"
            )

        user_dict = await self.user_repo.get_by_id(target_user_id)
        if not user_dict or user_dict.get("is_deleted"):
            raise HTTPException(status_code=404, detail="User not found")

        await self.user_repo.update(target_user_id, {"role": new_role.value})
        user_dict["role"] = new_role.value

        print(f"[AUDIT] Admin {admin_user.id} changed role of user {target_user_id} to {new_role}")
        return user_dict

    async def delete_user(self, admin_id: UUID, user_id: UUID) -> None:
        user_dict = await self.user_repo.get_by_id(user_id)
        if not user_dict or user_dict.get("is_deleted"):
            raise HTTPException(status_code=404, detail="User not found")

        anonymised_email = f"deleted_{user_id}@removed.com"
        await self.user_repo.update(
            user_id,
            {
                "is_deleted": True,
                "is_active": False,
                "email": anonymised_email,
                "full_name": "Deleted User",
                "phone": None,
                "oauth_accounts": [],
            },
        )

        await redis_client.set(f"banned_user:{user_id}", "true")

        print(f"[AUDIT] Admin {admin_id} deleted and anonymised user {user_id}")

    async def get_user_stats(self, user_id: UUID) -> dict[str, Any]:
        user_dict = await self.user_repo.get_by_id(user_id)
        if not user_dict or user_dict.get("is_deleted"):
            raise HTTPException(status_code=404, detail="User not found")

        # Bookings count
        bookings, booking_count = await self.booking_repo.get_user_bookings(user_id, 0, 1)

        # Total spend calculations
        payments, _ = await self.payment_repo.get_user_payment_history(user_id, 0, 10000)
        from app.models.payment import PaymentStatus

        total_spend = sum(
            p["amount"].to_decimal() if hasattr(p["amount"], "to_decimal") else p["amount"]
            for p in payments
            if p["status"] == PaymentStatus.SUCCEEDED.value
        )

        last_login = user_dict.get("updated_at")

        return {
            "booking_count": booking_count,
            "total_spend": total_spend,
            "last_login": last_login,
        }
