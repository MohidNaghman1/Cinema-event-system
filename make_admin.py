import asyncio
import sys

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from app.models.user import User, Role
from app.config import get_settings

async def main(email: str):
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri, uuidRepresentation="standard")
    db = client[settings.mongo_db_name]
    
    # Initialize Beanie just for the User model
    await init_beanie(database=db, document_models=[User])
    
    user = await User.find_one(User.email == email)
    if not user:
        print(f"Error: User with email '{email}' not found in the database.")
        return
        
    user.role = Role.ADMIN
    await user.save()
    print(f"Success! {email} has been promoted to ADMIN.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python make_admin.py <email>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
