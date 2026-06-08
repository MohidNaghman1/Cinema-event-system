from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.dependencies import get_db, require_role
from app.models.booking import BookingStatus
from app.models.payment import PaymentStatus
from app.models.user import Role

router = APIRouter(prefix="/api/v1/admin/reports", tags=["Admin — Reports"], responses={    401: {"description": "Unauthorized - Invalid or missing authentication token."},    403: {"description": "Forbidden - You do not have the required role permissions."},    422: {"description": "Unprocessable Entity - Schema validation error on the request payload."}})


class ChartData(BaseModel):
    labels: List[str]
    values: List[float]


@router.get(
    "/revenue",
    response_model=ChartData,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def get_revenue_report(
    period: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> ChartData:
    payment_collection = db["payments"]

    filters: dict[str, Any] = {"status": PaymentStatus.SUCCEEDED.value}
    if from_date or to_date:
        date_filter: dict[str, Any] = {}
        if from_date:
            date_filter["$gte"] = from_date
        if to_date:
            date_filter["$lte"] = to_date
        filters["created_at"] = date_filter

    date_format = "%Y-%m-%d"
    if period == "monthly":
        date_format = "%Y-%m"
    elif period == "weekly":
        date_format = "%Y-%U"

    pipeline = [
        {"$match": filters},
        {
            "$group": {
                "_id": {"$dateToString": {"format": date_format, "date": "$created_at"}},
                "total": {"$sum": "$amount"},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    cursor = payment_collection.aggregate(pipeline)
    results = await cursor.to_list(length=None)

    labels = []
    values = []
    for r in results:
        labels.append(r["_id"])
        val = r["total"].to_decimal() if hasattr(r["total"], "to_decimal") else r["total"]
        values.append(float(val))

    return ChartData(labels=labels, values=values)


@router.get(
    "/events",
    response_model=ChartData,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def get_top_events_report(
    metric: str = Query("revenue", pattern="^(revenue|occupancy)$"),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> ChartData:
    if metric == "occupancy":
        event_collection = db["events"]
        pipeline = [
            {"$match": {"total_seats": {"$gt": 0}}},
            {
                "$project": {
                    "title": 1,
                    "occupancy": {
                        "$divide": [
                            {"$subtract": ["$total_seats", "$available_seats"]},
                            "$total_seats",
                        ]
                    },
                }
            },
            {"$sort": {"occupancy": -1}},
            {"$limit": 10},
        ]

        cursor = event_collection.aggregate(pipeline)
        results = await cursor.to_list(length=None)

        labels = [r["title"] for r in results]
        values = [round(float(r["occupancy"]) * 100, 2) for r in results]
        return ChartData(labels=labels, values=values)

    else:
        booking_collection = db["bookings"]
        pipeline = [
            {"$match": {"status": BookingStatus.CONFIRMED.value}},
            {"$group": {"_id": "$event_id", "revenue": {"$sum": "$total_amount"}}},
            {
                "$lookup": {
                    "from": "events",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "event",
                }
            },
            {"$unwind": "$event"},
            {"$sort": {"revenue": -1}},
            {"$limit": 10},
        ]

        cursor = booking_collection.aggregate(pipeline)
        results = await cursor.to_list(length=None)

        labels = [r["event"]["title"] for r in results]
        values = [
            float(
                r["revenue"].to_decimal()
                if hasattr(r["revenue"], "to_decimal")
                else r["revenue"]
            )
            for r in results
        ]

        return ChartData(labels=labels, values=values)


@router.get(
    "/users",
    response_model=ChartData,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def get_user_signups_report(
    period: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> ChartData:
    user_collection = db["users"]

    filters: dict[str, Any] = {"is_deleted": False}
    if from_date or to_date:
        date_filter: dict[str, Any] = {}
        if from_date:
            date_filter["$gte"] = from_date
        if to_date:
            date_filter["$lte"] = to_date
        filters["created_at"] = date_filter

    date_format = "%Y-%m-%d"
    if period == "monthly":
        date_format = "%Y-%m"
    elif period == "weekly":
        date_format = "%Y-%U"

    pipeline = [
        {"$match": filters},
        {
            "$group": {
                "_id": {"$dateToString": {"format": date_format, "date": "$created_at"}},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    cursor = user_collection.aggregate(pipeline)
    results = await cursor.to_list(length=None)

    labels = [r["_id"] for r in results]
    values = [float(r["count"]) for r in results]

    return ChartData(labels=labels, values=values)
