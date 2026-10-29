import tempfile
import os
import shutil
import json
from datetime import datetime
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from core.config import settings
from services.resume_processor import process_resume_file
from services.resume_extraction import extract_text_preserving_layout
from services.jdExtracter import extract_jd_with_llm
from services.matcher import match_resume_to_jd
from services.report_export import write_tabular_report, write_excel_report
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
    jd_file: Optional[UploadFile] = File(None),
    jd_text: Optional[str] = Form(None),
    resume_files: List[UploadFile] = File(...)
):
    """
    Bulk match resumes against a single Job Description.

    JD input (provide exactly one):
      - jd_file: The JD as a PDF or DOCX file upload
      - jd_text: The JD as a plain-text form field
      - resume_files: One or more candidate resume PDFs or DOCX files.

    Response:
      - results[]: per-candidate { filename, overall_score, grade, summary }
      - report_url: URL to download the generated PDF report (when >1 resume)
    """
    if not jd_file and not jd_text:
        raise HTTPException(status_code=400, detail="Either jd_file or jd_text must be provided.")

    if not resume_files or len(resume_files) == 0:
        raise HTTPException(status_code=400, detail="At least one resume file must be uploaded.")

    valid_exts = ('.pdf', '.docx', '.doc')
    for rf in resume_files:
        if not rf.filename.lower().endswith(valid_exts):
            raise HTTPException(
                status_code=400,
                detail=f"Only PDF and DOCX files are accepted. Invalid file: {rf.filename}"
            )

    if jd_file and not jd_file.filename.lower().endswith(valid_exts):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are accepted for jd_file.")

    temp_dir = tempfile.mkdtemp()

    try:
        if jd_file:
            print(f"Extracting text from JD file: {jd_file.filename}")
            jd_temp_path = os.path.join(temp_dir, jd_file.filename)
            with open(jd_temp_path, "wb") as buffer:
                buffer.write(await jd_file.read())
            parsed_jd_text = extract_text_preserving_layout(jd_temp_path)
            if not parsed_jd_text:
                raise HTTPException(status_code=400, detail="Failed to read text from uploaded JD file.")
        else:
            parsed_jd_text = (jd_text or "").strip()
            if not parsed_jd_text:
                raise HTTPException(status_code=400, detail="Provided jd_text is empty.")

        print("Extracting JD structure via LLM...")
        jd_data = extract_jd_with_llm(parsed_jd_text)
        if not jd_data:
            raise HTTPException(status_code=500, detail="Failed to extract Job Description data via LLM.")

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
        report_filename = "match_report.pdf"
        csv_filename = "faculty_screening_report.csv"
        excel_filename = "faculty_screening_report.xlsx"
        report_path = os.path.join(STATIC_DIR, report_filename)
        csv_path = os.path.join(STATIC_DIR, csv_filename)
        excel_path = os.path.join(STATIC_DIR, excel_filename)

        try:
            generate_match_report_pdf(
                results=internal_results,
                jd_data=jd_data,
                output_path=report_path,
            )
            report_download_url = "/download-match-report"
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
            excel_download_url = "/download-excel-report"
            print(f"Excel report saved: {excel_path}")
        except Exception as excel_e:
            print(f"Excel report generation failed: {excel_e}")

        response_data = {
            "success": True,
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
async def download_match_report():
    """
    Download the most recently generated bulk match PDF report.
    """
    report_path = os.path.join(STATIC_DIR, "match_report.pdf")
    if not os.path.exists(report_path):
        raise HTTPException(
            status_code=404,
            detail="No match report found. Run /match-bulk first to generate one."
        )
    date_str = datetime.now().strftime("%d_%m_%y")
    return FileResponse(
        path=report_path,
        filename=f"match_report_{date_str}.pdf",
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="match_report_{date_str}.pdf"'},
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
    date_str = datetime.now().strftime("%d_%m_%y")
    return FileResponse(
        path=csv_path,
        filename=f"faculty_screening_report_{date_str}.csv",
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="faculty_screening_report_{date_str}.csv"'},
    )


@router.get("/download-excel-report")
async def download_excel_report():
    """Download the formatted Excel candidate information sheet."""
    excel_path = os.path.join(STATIC_DIR, "faculty_screening_report.xlsx")
    if not os.path.exists(excel_path):
        raise HTTPException(
            status_code=404,
            detail="No Excel match report found. Run /match-bulk first to generate one.",
        )
    date_str = datetime.now().strftime("%d_%m_%y")
    return FileResponse(
        path=excel_path,
        filename=f"faculty_screening_report_{date_str}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="faculty_screening_report_{date_str}.xlsx"'},
    )

@router.post("/extract-jd")
async def extract_jd(request: Request):
    """
    Parse and structure a raw Job Description text.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
 
    jd_text = body.get("jd_text", "").strip()
    if not jd_text:
        raise HTTPException(status_code=400, detail="jd_text is required")
 
    jd_data = extract_jd_with_llm(jd_text)
    if not jd_data:
        raise HTTPException(status_code=500, detail="Failed to extract JD data via LLM.")
 
    return {"success": True, "data": jd_data}
