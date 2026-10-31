import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.services.pdf_processor import PDFProcessor

def test_pdf_extraction():
    sample_pdf = BASE_DIR / "sample_policies" / "CareShield_Health_Insurance_Policy.pdf"
    assert sample_pdf.exists(), f"Sample PDF missing at {sample_pdf}"

    data = PDFProcessor.inspect_and_extract(sample_pdf)

    print("\n--- TEST: PDF Extraction ---")
    print(f"Total Pages: {data['total_pages']} (Expected: 5)")
    print(f"Total Words: {data['total_words']}")
    print(f"Total Clauses Detected: {len(data['clauses'])}")
    print(f"Total Sections Detected: {len(data['sections'])}")
    print(f"Is Scanned: {data['is_scanned']} (Expected: False)")

    assert data["total_pages"] == 5
    assert data["total_words"] > 500
    assert len(data["clauses"]) >= 8
    assert not data["is_scanned"]
    print("[PASS] PDF Extraction validated successfully!")

if __name__ == "__main__":
    test_pdf_extraction()
