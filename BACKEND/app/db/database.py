from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
from app.core.logging import logger
from app.models.db_models import Base, User
from app.core.security import get_password_hash

# Handle SQLite vs PostgreSQL configurations
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=engine)
    
    # Seed default demonstration users if empty
    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        if user_count == 0:
            logger.info("Seeding initial demo analyst accounts...")
            demo_users = [
                User(
                    email="analyst@policylens.ai",
                    name="Sarah Jenkins",
                    role="Lead Policy Analyst",
                    department="Claims & Compliance",
                    avatar="SJ",
                    hashed_password=get_password_hash("PolicyLens@2026")
                ),
                User(
                    email="admin@policylens.ai",
                    name="Marcus Vance",
                    role="Risk & Compliance Manager",
                    department="Risk Operations",
                    avatar="MV",
                    hashed_password=get_password_hash("Admin@2026")
                ),
                User(
                    email="demo@policylens.ai",
                    name="Alex Rivera",
                    role="Underwriting Specialist",
                    department="Policy Review",
                    avatar="AR",
                    hashed_password=get_password_hash("Demo@2026")
                )
            ]
            db.add_all(demo_users)
            db.commit()
            logger.info("Demo accounts seeded successfully.")
    except Exception as e:
        logger.error(f"Error seeding demo accounts: {e}")
        db.rollback()
    finally:
        db.close()
