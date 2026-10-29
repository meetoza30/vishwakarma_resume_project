from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from core.config import settings
from db.models import Base, User
from core.security import hash_password

# Setup Database Engine with Pooling
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI Dependency providing a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables and create default admin user if missing."""
    Base.metadata.create_all(bind=engine)
    
    db: Session = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                username="admin",
                email="admin@vishwakarma.edu.in",
                hashed_password=hash_password("Admin@Vishwakarma2026!"),
                role="admin",
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            print("Database initialized: Default admin created (admin / Admin@Vishwakarma2026!)")
    except Exception as e:
        print(f"Error initializing DB default user: {e}")
        db.rollback()
    finally:
        db.close()
