import os
import uuid
import tempfile
import shutil
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, BackgroundTasks, Depends
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from db.session import get_db
from db.models import MatchJob, MatchResult, Resume as ResumeModel, AuditLog
from services.file_service import validate_file_upload, extract_text_robust, compute_file_hash
from services.llm_service import extract_resume_with_resilient_llm
from services.jdExtracter import extract_jd_with_llm
from services.matcher import match_resume_to_jd
from workers.queue_manager import process_bulk_match_job
from utils.generatereport import generate_match_report_pdf
from core.config import settings
from core.security import safe_path_join

router = APIRouter(prefix="/resumes", tags=["Resume Screening"])


@router.post("/extract")
async def extract_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Production Resume Extraction Endpoint:
    - Validates file format, size (max 15MB), empty file, and password encryption.
    - Computes SHA-256 hash for duplicate detection.
    - Performs text extraction + PyTesseract OCR fallback if scanned PDF.
    - Runs resilient LLM schema extraction.
    - Enforces deterministic AICTE compliance rules.
    """
    content = await file.read()
    validate_file_upload(file.filename, content)
    
    file_hash = compute_file_hash(content)
    
    # Save temporary file safely
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, file.filename)
    
    try:
        with open(temp_path, "wb") as buffer:
            buffer.write(content)

        print(f"Extracting text for: {file.filename}")
        resume_text = extract_text_robust(temp_path)
        if not resume_text:
            raise HTTPException(status_code=400, detail="Empty or unreadable resume text.")

        extracted_data = extract_resume_with_resilient_llm(resume_text)

        # Audit log entry
        audit = AuditLog(action="SINGLE_RESUME_EXTRACTED", details=f"Extracted resume '{file.filename}' (SHA256: {file_hash[:10]}...)")
        db.add(audit)
        db.commit()

        return {
            "success": True,
            "filename": file.filename,
            "file_hash": file_hash,
            "data": extracted_data
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/match-bulk")
async def match_bulk_resumes(
    background_tasks: BackgroundTasks,
    jd_file: Optional[UploadFile] = File(None),
    jd_text: Optional[str] = Form(None),
    resume_files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    """
    Production Async Bulk Match Endpoint:
    - Accepts Job Description (text or file) + up to N resume files.
    - Validates all uploads synchronously.
    - Creates a background Job ID and processes matching asynchronously so the API remains responsive!
    """
    if not jd_file and not jd_text:
        raise HTTPException(status_code=400, detail="Either jd_file or jd_text must be provided.")

    if not resume_files or len(resume_files) == 0:
        raise HTTPException(status_code=400, detail="At least one resume file must be uploaded.")

    # 1. Parse JD
    parsed_jd_text = ""
    if jd_file:
        jd_content = await jd_file.read()
        validate_file_upload(jd_file.filename, jd_content)
        temp_jd_path = os.path.join(settings.UPLOAD_DIR, f"temp_jd_{uuid.uuid4().hex}_{jd_file.filename}")
        with open(temp_jd_path, "wb") as f:
            f.write(jd_content)
        parsed_jd_text = extract_text_robust(temp_jd_path)
        try:
            os.remove(temp_jd_path)
        except:
            pass
    else:
        parsed_jd_text = (jd_text or "").strip()

    if not parsed_jd_text:
        raise HTTPException(status_code=400, detail="Failed to extract text from provided Job Description.")

    jd_data = extract_jd_with_llm(parsed_jd_text)
    if not jd_data:
        raise HTTPException(status_code=500, detail="Failed to parse Job Description structure via LLM.")

    # 2. Save candidate files to storage and validate
    saved_file_info = []
    job_id = str(uuid.uuid4())

    for r_file in resume_files:
        r_content = await r_file.read()
        validate_file_upload(r_file.filename, r_content)
        
        safe_filename = f"{uuid.uuid4().hex[:8]}_{r_file.filename}"
        dest_path = os.path.join(settings.UPLOAD_DIR, safe_filename)
        with open(dest_path, "wb") as f:
            f.write(r_content)
            
        saved_file_info.append({
            "filename": r_file.filename,
            "path": dest_path
        })

    # 3. Create Job in DB
    new_job = MatchJob(
        id=job_id,
        title=f"Bulk Screening for {jd_data.get('job_title', 'Faculty Post')}",
        total_resumes=len(saved_file_info),
        processed_resumes=0,
        status="QUEUED"
    )
    db.add(new_job)
    db.commit()

    # 4. Trigger Background Worker Task
    background_tasks.add_task(
        process_bulk_match_job,
        job_id=job_id,
        jd_data=jd_data,
        file_info_list=saved_file_info
    )

    return {
        "success": True,
        "job_id": job_id,
        "message": f"Bulk screening job '{job_id}' queued successfully. Total resumes: {len(saved_file_info)}.",
        "status": "QUEUED"
    }


@router.get("/jobs/{job_id}")
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """Poll async background screening job status and fetch results."""
    job = db.query(MatchJob).filter(MatchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job ID '{job_id}' not found.")

    results_entries = db.query(MatchResult).filter(MatchResult.job_id == job_id).all()
    results_list = [r.full_result_json for r in results_entries]

    return {
        "job_id": job.id,
        "title": job.title,
        "status": job.status,
        "total_resumes": job.total_resumes,
        "processed_resumes": job.processed_resumes,
        "report_pdf_url": job.report_pdf_path,
        "report_csv_url": job.report_csv_path,
        "results": results_list,
        "error_message": job.error_message
    }
