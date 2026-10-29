from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from db.session import get_db
from core.config import settings

router = APIRouter(prefix="/health", tags=["Health & Observability"])


@router.get("/liveness")
def liveness_probe():
    """Kubernetes / Container Liveness Probe."""
    return {
        "status": "alive",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION
    }


@router.get("/readiness")
def readiness_probe(db: Session = Depends(get_db)):
    """Kubernetes / Container Readiness Probe (verifies DB connection)."""
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "connected",
            "environment": settings.ENVIRONMENT
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {str(e)}"
        )
