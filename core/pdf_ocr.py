"""PDF text extraction with optional local OCR fallback via Tesseract."""
from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import shutil

@dataclass
class PdfTextResult:
    text: str
    page_count: int
    used_ocr: bool
    message: str = ""

def extract_pdf_text(pdf_bytes: bytes, *, enable_ocr: bool = True, max_ocr_pages: int = 20) -> PdfTextResult:
    """Read embedded text first, OCR empty pages when optional dependencies exist.

    OCR uses local Poppler and Tesseract binaries through pdf2image/pytesseract.
    The file bytes are processed in-process; there is no remote upload.
    """
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(pdf_bytes))
    page_text = [(page.extract_text() or "").strip() for page in reader.pages]
    empty_pages = [i for i, text in enumerate(page_text) if not text]
    if not empty_pages:
        return PdfTextResult("\n\n".join(page_text), len(page_text), False, "Embedded PDF text extracted.")
    if not enable_ocr:
        return PdfTextResult("\n\n".join(page_text), len(page_text), False, "OCR was not requested.")
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except ImportError:
        return PdfTextResult("\n\n".join(page_text), len(page_text), False,
                             "Some pages have no embedded text. Install pdf2image and pytesseract, plus Poppler and Tesseract, to OCR scanned pages.")
    # Prefer PATH, then project-local or standard Windows install locations.
    tess = shutil.which("tesseract")
    project_root = Path(__file__).resolve().parents[1]
    candidates = [project_root / ".tools" / "tesseract" / "tesseract.exe",
                  Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe",
                  Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe"]
    if not tess:
        tess = next((str(path) for path in candidates if path.is_file()), None)
    if not tess:
        return PdfTextResult("\n\n".join(page_text), len(page_text), False,
                             "Scanned pages need Tesseract OCR. Install it or add its folder to PATH, then restart the app.")
    pytesseract.pytesseract.tesseract_cmd = tess
    if len(empty_pages) > max_ocr_pages:
        return PdfTextResult("\n\n".join(page_text), len(page_text), False,
                             f"{len(empty_pages)} pages need OCR; limit is {max_ocr_pages} pages per upload. Split the PDF or adjust the configured limit.")
    try:
        # Render only pages without embedded text (pdf2image page numbers are one-based).
        for index in empty_pages:
            images = convert_from_bytes(pdf_bytes, first_page=index + 1, last_page=index + 1, dpi=200)
            if images:
                page_text[index] = pytesseract.image_to_string(images[0]).strip()
        text = "\n\n".join(page_text)
        extracted = sum(bool(x) for x in page_text)
        note = "Scanned pages processed locally with Tesseract OCR." if extracted else "OCR ran but found no readable text."
        return PdfTextResult(text, len(page_text), True, note)
    except Exception as exc:
        return PdfTextResult("\n\n".join(page_text), len(page_text), False,
                             f"OCR could not run: {exc}. Confirm Poppler and Tesseract are installed and available on PATH.")
