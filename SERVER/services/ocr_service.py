import io
import pdfplumber
import pytesseract
from PIL import Image
from core.config import settings

# Set pytesseract executable path if specified
if settings.TESSERACT_CMD != "tesseract":
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD


def perform_ocr_on_pdf_page(page) -> str:
    """Render a PDF page to PIL Image and extract text using PyTesseract OCR."""
    try:
        # Render PDF page to image at 200 DPI
        pix = page.to_image(resolution=200)
        pil_img = pix.original
        ocr_text = pytesseract.image_to_string(pil_img, lang="eng")
        return ocr_text.strip()
    except Exception as e:
        print(f"OCR extraction failed for page: {e}")
        return ""


def extract_pdf_with_ocr_fallback(file_path: str) -> str:
    """
    Extracts text from PDF with automatic PyTesseract OCR fallback for scanned/image PDFs.
    If text density < 50 characters per page, triggers OCR on page image.
    """
    extracted_text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
                clean_chars = page_text.strip()
                
                # Check text density threshold
                if len(clean_chars) < settings.OCR_DENSITY_THRESHOLD_CHARS:
                    print(f"Page {i+1} has low text density ({len(clean_chars)} chars). Triggering OCR...")
                    ocr_result = perform_ocr_on_pdf_page(page)
                    if ocr_result:
                        extracted_text += f"\n--- Page {i+1} (OCR) ---\n" + ocr_result + "\n"
                    else:
                        extracted_text += page_text + "\n"
                else:
                    extracted_text += page_text + "\n"
    except Exception as e:
        print(f"PDF extraction error: {e}")
        raise e

    return extracted_text
