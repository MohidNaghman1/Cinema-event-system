from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import get_db, require_role
from app.models.user import Role
from app.models.venue import SeatMap, Venue
from app.repositories.venue_repo import VenueRepository
from app.schemas.venue import VenueCreate, VenueList, VenueRead, VenueUpdate

router = APIRouter(prefix="/api/v1/venues", tags=["Venues"], responses={    401: {"description": "Unauthorized - Invalid or missing authentication token."},    403: {"description": "Forbidden - You do not have the required role permissions."},    422: {"description": "Unprocessable Entity - Schema validation error on the request payload."}})


def get_venue_repo(database: AsyncIOMotorDatabase = Depends(get_db)) -> VenueRepository:
    return VenueRepository(database)


@router.post("", response_model=VenueRead, dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))])
async def create_venue(
    data: VenueCreate,
    venue_repo: VenueRepository = Depends(get_venue_repo),
) -> VenueRead:
    venue = Venue(**data.model_dump())
    await venue_repo.create(venue)
    return VenueRead.model_validate(venue)


@router.get("", response_model=list[VenueList])
async def list_venues(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    city: Optional[str] = None,
    min_capacity: Optional[int] = None,
    venue_repo: VenueRepository = Depends(get_venue_repo),
) -> list[VenueList]:
    venues = await venue_repo.get_paginated(skip, limit, city, min_capacity)
    return [VenueList.model_validate(v) for v in venues]


@router.get("/{id}", response_model=VenueRead)
async def get_venue(
    id: UUID, venue_repo: VenueRepository = Depends(get_venue_repo)
) -> VenueRead:
    venue_dict = await venue_repo.get_by_id(id)
    if not venue_dict or venue_dict.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Venue not found")
    return VenueRead.model_validate(venue_dict)


@router.put("/{id}", response_model=VenueRead, dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))])
async def update_venue(
    id: UUID,
    data: VenueUpdate,
    venue_repo: VenueRepository = Depends(get_venue_repo),
) -> VenueRead:
    venue_dict = await venue_repo.get_by_id(id)
    if not venue_dict or venue_dict.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Venue not found")

    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        await venue_repo.update(id, update_data)
        venue_dict.update(update_data)

    return VenueRead.model_validate(venue_dict)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))])
async def delete_venue(
    id: UUID, venue_repo: VenueRepository = Depends(get_venue_repo)
) -> None:
    venue_dict = await venue_repo.get_by_id(id)
    if not venue_dict or venue_dict.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Venue not found")

    await venue_repo.update(id, {"is_deleted": True})


@router.get("/{id}/seats", response_model=SeatMap)
async def get_venue_seats(
    id: UUID,
    event_id: Optional[UUID] = None,
    venue_repo: VenueRepository = Depends(get_venue_repo),
) -> SeatMap:
    """Return the seat map for a venue. 
    If event_id is supplied, it will overlay live availability over the physical seats.
    """
    venue_dict = await venue_repo.get_by_id(id)
    if not venue_dict or venue_dict.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Venue not found")

    seat_map_data = venue_dict.get("seat_map")
    if not seat_map_data:
        raise HTTPException(
            status_code=404, detail="Seat map not configured for this venue"
        )

    # TODO: Overlay live availability when event_id is provided by querying the bookings module.
    
    return SeatMap.model_validate(seat_map_data)
