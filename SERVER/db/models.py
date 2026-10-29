import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="recruiter", nullable=False)  # admin, recruiter
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), index=True, nullable=False)  # SHA-256 for duplicate detection
    file_path = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    raw_text = Column(Text, nullable=True)
    extracted_data = Column(JSON, nullable=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)
    key_domain = Column(String(255), nullable=True)
    raw_text = Column(Text, nullable=False)
    structured_jd = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class MatchJob(Base):
    __tablename__ = "match_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), default="Bulk Resume Match")
    total_resumes = Column(Integer, default=0)
    processed_resumes = Column(Integer, default=0)
    status = Column(String(20), default="QUEUED", index=True)  # QUEUED, PROCESSING, COMPLETED, FAILED, PARTIAL_SUCCESS
    error_message = Column(Text, nullable=True)
    report_pdf_path = Column(String(500), nullable=True)
    report_csv_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    results = relationship("MatchResult", back_populates="job", cascade="all, delete-orphan")


class MatchResult(Base):
    __tablename__ = "match_results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("match_jobs.id"), index=True, nullable=False)
    resume_filename = Column(String(255), nullable=False)
    candidate_name = Column(String(255), nullable=True)
    overall_score = Column(Integer, default=0)
    fit_grade = Column(String(50), nullable=True)
    aicte_recommended_status = Column(String(100), nullable=True)
    full_result_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    job = relationship("MatchJob", back_populates="results")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    action = Column(String(100), nullable=False, index=True)
    user_id = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
