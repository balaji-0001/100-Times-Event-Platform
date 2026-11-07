import sys
from pathlib import Path

# Add artifacts/api-server to sys.path
api_dir = Path("artifacts/api-server").resolve()
sys.path.insert(0, str(api_dir))

from backend.core.config import get_settings
from backend.db import Base, engine
from backend import models

print("Creating database schema...")
Base.metadata.create_all(bind=engine, checkfirst=True)

print("Seeding database...")
from backend.seed import seed
seed()

print("Schema creation and seeding successful!")
