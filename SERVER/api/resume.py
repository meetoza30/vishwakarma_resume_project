import tempfile
import os
import shutil
import json
import re
from typing import List
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from core.config import settings
from services.resume_processor import process_resume_file
from services.matcher import match_resume_to_jd, get_permanent_jd_data, normalize_selected_role
from services.report_export import (
    write_tabular_report,
    write_excel_report,
    dated_report_filename,
    aicte_eligible_role,
)
from utils.generatepdf import generate_resume_pdf
from utils.generatereport import generate_match_report_pdf
from middleware.rate_limiter import check_rate_limit, increment_active, decrement_active

router = APIRouter()

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

@router.post("/extract-resume")
async def extract_resume(request: Request, file: UploadFile = File(...)):
    """
    Upload a resume PDF or DOCX and extract structured data from it.
    
    - **file**: Resume PDF or DOCX file to process
    
    Returns:
        dict: Extracted resume data as JSON for the frontend to display/edit
    """
    # ── Rate limit check ─────────────────────────────────────────────
    rate_headers = check_rate_limit(request, cost=1)

    valid_exts = ('.pdf', '.docx', '.doc')
    if not file.filename.lower().endswith(valid_exts):
        raise HTTPException(
            status_code=400, 
            detail="Only PDF and DOCX files are accepted. Please upload a valid resume."
        )
    
    temp_dir = tempfile.mkdtemp()
    temp_input_path = os.path.join(temp_dir, file.filename)
    
    increment_active()
    try:
        with open(temp_input_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        print(f"Processing resume: {file.filename}")
        extracted_data = process_resume_file(temp_input_path)
        
        print(f"Extracted Name: {extracted_data.get('Name', 'Unknown')}")
        
        response_data = {
            "success": True,
            "data": extracted_data
        }
        return JSONResponse(content=response_data, headers=rate_headers)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing resume: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error processing resume: {str(e)}"
        )
    finally:
        decrement_active()
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


@router.post("/generate-resume")
async def generate_resume(request: Request):
    """
    Generate a formatted nCircle CV PDF from the provided resume data JSON.
    
    Expects a JSON body with the full resume data structure (same format as extract-resume returns).
    
    Returns:
        FileResponse: The generated nCircle format PDF
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    if not body.get("Name"):
        raise HTTPException(status_code=400, detail="Name is required")
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        candidate_name = body.get("Name", "Unknown")
        output_filename = f"{candidate_name.replace(' ', '_')}_VishwakarmaCV.pdf"
        output_path = os.path.join(temp_dir, output_filename)
        
        generate_resume_pdf(body, output_path)
        print(f"PDF generated: {output_filename}")
        
        return FileResponse(
            path=output_path,
            filename=output_filename,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{output_filename}"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating PDF: {str(e)}")
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
        raise HTTPException(
            status_code=500, 
            detail=f"Error generating PDF: {str(e)}"
        )


@router.post("/match-bulk")
async def match_bulk_resumes(
    request: Request,
    target_position: str = Form(...),
    resume_files: List[UploadFile] = File(...)
):
    """
    Bulk match resumes against the institution's stored norms for a selected role.

    Response:
      - results[]: per-candidate { filename, overall_score, grade, summary }
      - report_url: URL to download the generated PDF report (when >1 resume)
    """
    selected_role = normalize_selected_role(target_position)
    if not selected_role:
        raise HTTPException(status_code=400, detail="Select Assistant Professor, Associate Professor, or Professor.")

    if not resume_files or len(resume_files) == 0:
        raise HTTPException(status_code=400, detail="At least one resume file must be uploaded.")

    valid_exts = ('.pdf', '.docx', '.doc')
    for rf in resume_files:
        if not rf.filename.lower().endswith(valid_exts):
            raise HTTPException(
                status_code=400,
                detail=f"Only PDF and DOCX files are accepted. Invalid file: {rf.filename}"
            )

    temp_dir = tempfile.mkdtemp()

    try:
        jd_data = get_permanent_jd_data(selected_role)

        # 1. Save uploaded resume files to disk asynchronously first
        file_tasks = []
        for idx, file in enumerate(resume_files, start=1):
            file_temp_path = os.path.join(temp_dir, f"{idx}_{file.filename}")
            content = await file.read()
            with open(file_temp_path, "wb") as buffer:
                buffer.write(content)
            file_tasks.append((idx, file.filename, file_temp_path))

        # Helper for isolated worker execution
        def _process_candidate_worker(item):
            idx, filename, file_path = item
            try:
                print(f"[{idx}/{len(file_tasks)}] Concurrently processing resume: {filename}")
                resume_data = process_resume_file(file_path)

                print(f"[{idx}/{len(file_tasks)}] Running matching engine for: {filename}")
                match_result = match_resume_to_jd(resume_data, jd_data)

                internal_res = {
                    "filename": filename,
                    "success": True,
                    "match": match_result,
                }
                frontend_res = {
                    "sr_no": idx,
                    "filename": filename,
                    "success": True,
                    "overall_score": match_result.get("overall_score"),
                    "grade":         match_result.get("grade"),
                    "summary":       match_result.get("summary"),
                    "candidate_name": match_result.get("candidate_name"),
                    # "applied_post": match_result.get("applied_post"),
                    "contact_number": match_result.get("contact_number"),
                    "email_id": match_result.get("email_id"),
                    "qualification": match_result.get("qualification"),
                    "target_position": match_result.get("target_position"),
                    "aicte_eligibility_role": aicte_eligible_role(match_result),
                    "total_publications": match_result.get("total_publications", 0),
                    "total_indexed_publications": match_result.get("total_indexed_publications", 0),
                    "scopus_post_phd_publications": match_result.get("scopus_post_phd_publications"),
                    "research_areas": match_result.get("research_areas", []),
                    "patents": match_result.get("patents"),
                    "grants_funding": match_result.get("grants_funding"),
                    "experience_data": match_result.get("experience_data"),
                    "previous_employers": match_result.get("previous_employers"),
                    "aicte_eligibility": match_result.get("aicte_eligibility"),
                    "extra_academic_fields": match_result.get("extra_academic_fields"),
                    "breakdown": match_result.get("breakdown"),
                }
                return internal_res, frontend_res
            except Exception as candidate_e:
                print(f"[{idx}/{len(file_tasks)}] Failed to process {filename}: {candidate_e}")
                err_msg = str(candidate_e)
                return (
                    {"filename": filename, "success": False, "error": err_msg},
                    {"sr_no": idx, "filename": filename, "success": False, "error": err_msg}
                )

        # 2. Concurrently execute resume extractions & match evaluations
        worker_count = min(settings.MAX_CONCURRENT_RESUME_WORKERS, len(file_tasks))
        print(f"Starting parallel processing pool with {worker_count} worker threads for {len(file_tasks)} resumes...")

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results_pairs = list(executor.map(_process_candidate_worker, file_tasks))

        internal_results = [pair[0] for pair in results_pairs]
        frontend_results = [pair[1] for pair in results_pairs]

        report_download_url = None
        csv_download_url = None
        excel_download_url = None
        report_filename = dated_report_filename("pdf", "pdf")
        csv_filename = "faculty_screening_report.csv"
        excel_filename = dated_report_filename("excel", "xlsx")
        report_path = os.path.join(STATIC_DIR, report_filename)
        csv_path = os.path.join(STATIC_DIR, csv_filename)
        excel_path = os.path.join(STATIC_DIR, excel_filename)

        try:
            generate_match_report_pdf(
                results=internal_results,
                jd_data=jd_data,
                output_path=report_path,
            )
            report_download_url = f"/download-match-report?filename={report_filename}"
            print(f"Match report saved: {report_path}")
        except Exception as pdf_e:
            print(f"PDF report generation failed (non-fatal): {pdf_e}")

        # --- CSV REPORT GENERATION ---
        try:
            write_tabular_report(csv_path, frontend_results)
            csv_download_url = "/download-csv-report"
            print(f"CSV report saved: {csv_path}")
        except Exception as csv_e:
            print(f"CSV report generation failed: {csv_e}")

        try:
            write_excel_report(excel_path, frontend_results)
            excel_download_url = f"/download-excel-report?filename={excel_filename}"
            print(f"Excel report saved: {excel_path}")
        except Exception as excel_e:
            print(f"Excel report generation failed: {excel_e}")

        response_data = {
            "success": True,
            "target_position": selected_role,
            "results": frontend_results,
            "report_download_url": report_download_url,
            "csv_download_url": csv_download_url,
            "excel_download_url": excel_download_url,
        }
        return JSONResponse(content=response_data)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Bulk match API error: {e}")
        raise HTTPException(status_code=500, detail=f"Error in match-bulk: {str(e)}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@router.get("/download-match-report")
async def download_match_report(filename: str = None):
    """
    Download the most recently generated bulk match PDF report.
    """
    expected_filename = dated_report_filename("pdf", "pdf")
    if filename and not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}_match_report_pdf\.pdf", filename):
        raise HTTPException(status_code=400, detail="Invalid report filename.")
    filename = filename or expected_filename
    report_path = os.path.join(STATIC_DIR, filename)
    if not os.path.exists(report_path):
        raise HTTPException(
            status_code=404,
            detail="No match report found. Run /match-bulk first to generate one."
        )
    return FileResponse(
        path=report_path,
        filename=filename,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/download-csv-report")
async def download_csv_report():
    """
    Download the tabular CSV report for faculty screening.
    """
    csv_path = os.path.join(STATIC_DIR, "faculty_screening_report.csv")
    if not os.path.exists(csv_path):
        raise HTTPException(
            status_code=404,
            detail="No CSV match report found. Run /match-bulk first to generate one."
        )
    return FileResponse(
        path=csv_path,
        filename="faculty_screening_report.csv",
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="faculty_screening_report.csv"'},
    )


@router.get("/download-excel-report")
async def download_excel_report(filename: str = None):
    """Download the formatted Excel candidate information sheet."""
    expected_filename = dated_report_filename("excel", "xlsx")
    if filename and not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}_match_report_excel\.xlsx", filename):
        raise HTTPException(status_code=400, detail="Invalid report filename.")
    filename = filename or expected_filename
    excel_path = os.path.join(STATIC_DIR, filename)
    if not os.path.exists(excel_path):
        raise HTTPException(
            status_code=404,
            detail="No Excel match report found. Run /match-bulk first to generate one.",
        )
    return FileResponse(
        path=excel_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
