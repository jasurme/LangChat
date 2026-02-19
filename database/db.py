import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

engine = create_engine(
    os.environ["DATABASE_URL"],
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

with engine.connect() as conn:
    version = conn.execute(text("SELECT version()")).scalar_one()
    print(version)
