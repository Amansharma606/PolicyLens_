import os
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import pymupdf  # PyMuPDF
from app.core.logging import logger

class PDFProcessingError(Exception):
    pass

class PDFProcessor:
    """
    Advanced Health Insurance Policy PDF Processor.
    Extracts text page-by-page, detects sections, numbered clauses, tables,
    and identifies scanned image-only PDFs.
    """

    # Common policy section regexes
    SECTION_PATTERNS = [
        re.compile(r"^(?:SECTION|PART|MODULE|ARTICLE|CHAPTER)\s+([0-9IVXLCDM]+|[A-Z])[:\.\-\s]+(.+)$", re.IGNORECASE),
        re.compile(r"^(\d+\.0?|\b[A-Z]\.)\s+([A-Z\s]{3,50})$"),
        re.compile(r"^(COVERAGE(?:S)?|BENEFITS|EXCLUSIONS|WAITING PERIODS?|GENERAL CONDITIONS|DEFINITIONS|CLAIM PROCEDURES?|LIMITS OF LIABILITY|GRIEVANCE REDRESSAL)", re.IGNORECASE)
    ]

    CLAUSE_NUMBER_PATTERN = re.compile(
        r"^(?:Clause\s+|Section\s+|Article\s+)?(\d+(?:\.\d+)*(?:\([a-z0-9]+\))?|[a-z]\)|\([a-z0-9]+\))\s*(?:[:\.\-])?\s*(.+)",
        re.IGNORECASE
    )

    @staticmethod
    def inspect_and_extract(file_path: Path) -> Dict[str, Any]:
        """
        Extracts pages and structure from a PDF file using PyMuPDF.
        """
        if not file_path.exists():
            raise PDFProcessingError(f"File not found: {file_path}")

        try:
            doc = pymupdf.open(str(file_path))
        except Exception as e:
            raise PDFProcessingError(f"Corrupted or invalid PDF file: {str(e)}")

        if doc.is_encrypted:
            doc.close()
            raise PDFProcessingError("Password-protected or encrypted PDF documents are not supported.")

        total_pages = len(doc)
        if total_pages == 0:
            doc.close()
            raise PDFProcessingError("The uploaded PDF has 0 pages.")

        pages_data: List[Dict[str, Any]] = []
        total_words = 0
        total_chars = 0

        current_section = "General Policy Overview"
        all_sections: List[Dict[str, Any]] = []
        all_clauses: List[Dict[str, Any]] = []

        for page_idx in range(total_pages):
            page_num = page_idx + 1
            page = doc[page_idx]

            # Extract structured blocks
            # PyMuPDF blocks: (x0, y0, x1, y1, text, block_no, block_type)
            text_page = page.get_text("text")
            clean_page_text = text_page.strip()
            word_count = len(clean_page_text.split())
            char_count = len(clean_page_text)

            total_words += word_count
            total_chars += char_count

            pages_data.append({
                "page": page_num,
                "word_count": word_count,
                "text": clean_page_text
            })

            # Extract lines and structure
            lines = [l.strip() for l in clean_page_text.splitlines() if l.strip()]
            buffer_clause = []
            active_clause_num = None

            for line in lines:
                # Check for Section Heading
                is_section = False
                for pattern in PDFProcessor.SECTION_PATTERNS:
                    match = pattern.match(line)
                    if match:
                        if buffer_clause:
                            clause_text = " ".join(buffer_clause).strip()
                            if len(clause_text) > 25:
                                all_clauses.append({
                                    "page": page_num,
                                    "section": current_section,
                                    "clause_number": active_clause_num,
                                    "text": clause_text
                                })
                            buffer_clause = []
                            active_clause_num = None

                        current_section = line
                        all_sections.append({
                            "title": line,
                            "page": page_num,
                            "level": 1
                        })
                        is_section = True
                        break

                if is_section:
                    continue

                # Check for numbered clause
                clause_match = PDFProcessor.CLAUSE_NUMBER_PATTERN.match(line)
                if clause_match:
                    if buffer_clause:
                        clause_text = " ".join(buffer_clause).strip()
                        if len(clause_text) > 25:
                            all_clauses.append({
                                "page": page_num,
                                "section": current_section,
                                "clause_number": active_clause_num,
                                "text": clause_text
                            })
                        buffer_clause = []

                    active_clause_num = clause_match.group(1)
                    buffer_clause.append(line)
                else:
                    # Check paragraph break or list item
                    if len(buffer_clause) > 0 and (line.startswith("•") or line.startswith("-") or line.startswith("*")):
                        # New bullet clause
                        clause_text = " ".join(buffer_clause).strip()
                        if len(clause_text) > 25:
                            all_clauses.append({
                                "page": page_num,
                                "section": current_section,
                                "clause_number": active_clause_num,
                                "text": clause_text
                            })
                        buffer_clause = [line]
                    else:
                        buffer_clause.append(line)

            # Flush remaining clause buffer on page
            if buffer_clause:
                clause_text = " ".join(buffer_clause).strip()
                if len(clause_text) > 25:
                    all_clauses.append({
                        "page": page_num,
                        "section": current_section,
                        "clause_number": active_clause_num,
                        "text": clause_text
                    })

        doc.close()

        # Check for scanned PDF
        is_scanned = (total_words < 15 or total_chars < 80) and total_pages > 0

        # If few clauses detected due to non-standard formatting, perform fallback paragraph chunking
        if len(all_clauses) < 5 and not is_scanned:
            all_clauses = PDFProcessor._fallback_paragraph_segmentation(pages_data)

        return {
            "total_pages": total_pages,
            "total_words": total_words,
            "total_chars": total_chars,
            "is_scanned": is_scanned,
            "pages": pages_data,
            "sections": all_sections,
            "clauses": all_clauses
        }

    @staticmethod
    def _fallback_paragraph_segmentation(pages_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fallback structure-aware paragraph segmentation preserving page numbers.
        """
        clauses = []
        for p in pages_data:
            page_num = p["page"]
            text = p["text"]
            # Split by double newline or large paragraph breaks
            paragraphs = re.split(r"\n\s*\n", text)
            for para in paragraphs:
                clean_p = " ".join(para.split()).strip()
                if len(clean_p) > 30:
                    clauses.append({
                        "page": page_num,
                        "section": "General Terms & Clauses",
                        "clause_number": None,
                        "text": clean_p
                    })
        return clauses
