import os
import asyncio
import traceback
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session

from db.session import SessionLocal
from db.models import MatchJob, MatchResult, AuditLog
from services.file_service import extract_text_robust
from services.llm_service import extract_resume_with_resilient_llm
from services.matcher import match_resume_to_jd
from services.report_export import (
    write_tabular_report,
    write_excel_report,
    dated_report_filename,
    report_now,
    aicte_eligible_role,
)
from utils.generatereport import generate_match_report_pdf
from core.config import settings


async def process_bulk_match_job(
    job_id: str,
    jd_data: Dict[str, Any],
    file_info_list: List[Dict[str, str]]  # list of {"filename": ..., "path": ...}
):
    """
    Asynchronous Background Worker for Bulk Resume Processing.
    Executes resume extractions and matching in isolation per candidate.
    Guarantees 1 failed resume does not break the bulk processing batch!
    """
    print(f"Background worker started for Job ID: {job_id}")
    db: Session = SessionLocal()

    try:
        # 1. Update job status to PROCESSING
        job = db.query(MatchJob).filter(MatchJob.id == job_id).first()
        if not job:
            print(f"Job {job_id} not found in DB.")
            return

        job.status = "PROCESSING"
        db.commit()

        internal_results = []
        frontend_results = []

        total_files = len(file_info_list)
        worker_count = min(settings.MAX_CONCURRENT_RESUME_WORKERS, total_files)
        print(f"Executing Job {job_id} in parallel with {worker_count} concurrent worker threads...")

        def _process_job_candidate_task(item):
            idx, f_info = item
            filename = f_info["filename"]
            file_path = f_info["path"]
            print(f"[{idx}/{total_files}] Concurrently processing {filename} for Job {job_id}...")
            try:
                # 1. Extract text
                resume_text = extract_text_robust(file_path)
                if not resume_text:
                    raise ValueError("Extracted text is empty or unreadable.")

                # 2. Extract structured candidate data
                resume_data = extract_resume_with_resilient_llm(resume_text)

                # 3. Match against JD
                match_result = match_resume_to_jd(resume_data, jd_data)

                internal_res = {
                    "filename": filename,
                    "success": True,
                    "match": match_result
                }

                frontend_res = {
                    "sr_no": idx,
                    "filename": filename,
                    "success": True,
                    "overall_score": match_result.get("overall_score"),
                    "candidate_category": match_result.get("candidate_category", "Faculty"),
                    "grade": match_result.get("grade"),
                    "summary": match_result.get("summary"),
                    "candidate_name": match_result.get("candidate_name"),
                    "contact_number": match_result.get("contact_number"),
                    "email_id": match_result.get("email_id"),
                    "qualification": match_result.get("qualification"),
                    "target_position": match_result.get("target_position"),
                    "aicte_eligibility_role": aicte_eligible_role(match_result),
                    "total_publications": match_result.get("total_publications", 0),
                    "total_indexed_publications": match_result.get("total_indexed_publications", 0),
                    "research_areas": match_result.get("research_areas", []),
                    "scopus_post_phd_publications": match_result.get("scopus_post_phd_publications"),
                    "patents": match_result.get("patents"),
                    "grants_funding": match_result.get("grants_funding"),
                    "experience_data": match_result.get("experience_data"),
                    "previous_employers": match_result.get("previous_employers"),
                    "aicte_eligibility": match_result.get("aicte_eligibility"),
                    "extra_academic_fields": match_result.get("extra_academic_fields"),
                    "breakdown": match_result.get("breakdown")
                }
                return idx, filename, True, match_result, internal_res, frontend_res, None

            except Exception as candidate_e:
                print(f"[{idx}/{total_files}] Candidate processing error on '{filename}': {candidate_e}")
                err_msg = str(candidate_e)
                internal_res = {
                    "filename": filename,
                    "success": False,
                    "error": err_msg
                }
                frontend_res = {
                    "sr_no": idx,
                    "filename": filename,
                    "success": False,
                    "error": err_msg
                }
                return idx, filename, False, None, internal_res, frontend_res, err_msg

        # Launch parallel workers
        indexed_items = list(enumerate(file_info_list, start=1))
        results_by_idx = {}
        completed_count = 0

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_item = {
                executor.submit(_process_job_candidate_task, item): item
                for item in indexed_items
            }

            for future in as_completed(future_to_item):
                idx, filename, success, match_result, internal_res, frontend_res, err_msg = future.result()
                results_by_idx[idx] = (internal_res, frontend_res)

                if success and match_result:
                    # Record successful match in DB (thread-safe on coordinator)
                    result_entry = MatchResult(
                        job_id=job_id,
                        resume_filename=filename,
                        candidate_name=match_result.get("candidate_name", "Unknown"),
                        overall_score=match_result.get("overall_score", 0),
                        fit_grade=match_result.get("grade", "N/A"),
                        aicte_recommended_status=match_result.get("aicte_eligibility", {}).get("primary_recommended_status", "Unverified"),
                        full_result_json=match_result
                    )
                    db.add(result_entry)

                completed_count += 1
                job.processed_resumes = completed_count
                db.commit()

        # Reconstruct ordered results lists
        internal_results = [results_by_idx[i][0] for i in range(1, total_files + 1)]
        frontend_results = [results_by_idx[i][1] for i in range(1, total_files + 1)]

        # 3. Generate PDF and CSV reports
        report_date = report_now()
        report_pdf_name = dated_report_filename("pdf", "pdf", job_id[:8], report_date)
        report_csv_name = f"faculty_report_{job_id[:8]}.csv"
        report_excel_name = dated_report_filename("excel", "xlsx", job_id[:8], report_date)
        
        pdf_output_path = os.path.join(settings.STATIC_DIR, report_pdf_name)
        csv_output_path = os.path.join(settings.STATIC_DIR, report_csv_name)
        excel_output_path = os.path.join(settings.STATIC_DIR, report_excel_name)

        try:
            generate_match_report_pdf(
                results=internal_results,
                jd_data=jd_data,
                output_path=pdf_output_path
            )
            job.report_pdf_path = f"/static/{report_pdf_name}"
        except Exception as pdf_e:
            print(f"PDF generation warning: {pdf_e}")

        try:
            write_tabular_report(csv_output_path, frontend_results)

            job.report_csv_path = f"/static/{report_csv_name}"
        except Exception as csv_e:
            print(f"CSV generation warning: {csv_e}")

        try:
            write_excel_report(excel_output_path, frontend_results)
        except Exception as excel_e:
            print(f"Excel generation warning: {excel_e}")

        # 4. Finalize Job Status
        successful_count = sum(1 for r in internal_results if r.get("success"))
        if successful_count == total_files:
            job.status = "COMPLETED"
        elif successful_count > 0:
            job.status = "PARTIAL_SUCCESS"
        else:
            job.status = "FAILED"
            job.error_message = "All resumes failed processing."

        # Audit log
        audit = AuditLog(
            action="BULK_SCREENING_JOB_COMPLETED",
            details=f"Job {job_id} finished with status '{job.status}'. Processed {successful_count}/{total_files} resumes."
        )
        db.add(audit)
        db.commit()

        print(f"Job {job_id} execution completed. Status: {job.status}")

    except Exception as e:
        print(f"Fatal error in background worker for Job {job_id}: {e}\n{traceback.format_exc()}")
        try:
            job = db.query(MatchJob).filter(MatchJob.id == job_id).first()
            if job:
                job.status = "FAILED"
                job.error_message = str(e)
                db.commit()
        except:
            pass
    finally:
        db.close()
        # Clean up temporary uploaded files
        for f_info in file_info_list:
            try:
                if os.path.exists(f_info["path"]):
                    os.remove(f_info["path"])
            except:
                pass
