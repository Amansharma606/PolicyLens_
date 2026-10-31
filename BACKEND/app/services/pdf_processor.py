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
    Produces clause-aware, bounded chunks (80-250 words) with sentence-boundary overlaps.
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

    HEADER_FOOTER_PATTERNS = [
        re.compile(r"^(?:Page\s+\d+\s+(?:of\s+\d+)?|\d+\s+of\s+\d+)$", re.IGNORECASE),
        re.compile(r"^CareShield\s+Comprehensive\s+Health\s+Insurance.*$", re.IGNORECASE),
        re.compile(r"^IRDAI\s+Reg(?:istration)?\.?\s*No.*$", re.IGNORECASE),
        re.compile(r"^CIN\s*:\s*[A-Z0-9]+$", re.IGNORECASE),
        re.compile(r"^Policy\s+Wording\s*[-–]\s*.*$", re.IGNORECASE),
    ]

    @classmethod
    def _is_header_footer(cls, line: str) -> bool:
        trimmed = line.strip()
        if not trimmed:
            return True
        for pat in cls.HEADER_FOOTER_PATTERNS:
            if pat.match(trimmed):
                return True
        return False

    @staticmethod
    def _split_into_sentences(text: str) -> List[str]:
        # Split on sentence boundaries preserving abbreviations like Rs., No., etc.
        sentence_end = re.compile(r'(?<!\b(?:Rs|No|Dr|Mr|Ms|Vol|e\.g|i\.e)\.)(?<=\.|\?|!)\s+')
        sentences = [s.strip() for s in sentence_end.split(text) if s.strip()]
        return sentences if sentences else [text.strip()]

    @classmethod
    def _split_oversized_clause(
        cls,
        clause_text: str,
        page_num: int,
        section: str,
        clause_num: Optional[str],
        max_words: int = 240,
        overlap_sentences: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Splits a clause that exceeds max_words into coherent sentence-bounded chunks
        with overlap so context is never severed.
        """
        words = clause_text.split()
        if len(words) <= max_words:
            return [{
                "page": page_num,
                "section": section,
                "clause_number": clause_num,
                "text": clause_text
            }]

        sentences = cls._split_into_sentences(clause_text)
        if len(sentences) <= 1:
            # Cannot split on sentences, split by word count
            chunks = []
            start = 0
            part = 1
            overlap_words = 30
            while start < len(words):
                end = min(len(words), start + max_words)
                sub_text = " ".join(words[start:end])
                num_tag = f"{clause_num} (Part {part})" if clause_num else f"Part {part}"
                chunks.append({
                    "page": page_num,
                    "section": section,
                    "clause_number": num_tag,
                    "text": sub_text
                })
                part += 1
                if end == len(words):
                    break
                start = end - overlap_words
            return chunks

        chunks = []
        current_sentences: List[str] = []
        current_word_count = 0
        part = 1

        for sent in sentences:
            sent_word_count = len(sent.split())
            if current_word_count + sent_word_count > max_words and current_sentences:
                sub_text = " ".join(current_sentences).strip()
                num_tag = f"{clause_num} (Part {part})" if clause_num else f"Part {part}"
                chunks.append({
                    "page": page_num,
                    "section": section,
                    "clause_number": num_tag,
                    "text": sub_text
                })
                part += 1
                # Retain overlap sentences
                current_sentences = current_sentences[-overlap_sentences:]
                current_word_count = sum(len(s.split()) for s in current_sentences)

            current_sentences.append(sent)
            current_word_count += sent_word_count

        if current_sentences:
            sub_text = " ".join(current_sentences).strip()
            num_tag = f"{clause_num} (Part {part})" if (clause_num and part > 1) else clause_num
            chunks.append({
                "page": page_num,
                "section": section,
                "clause_number": num_tag,
                "text": sub_text
            })

        return chunks

    @staticmethod
    def _extract_markdown_tables(page: Any, page_num: int, current_section: str) -> List[Dict[str, Any]]:
        """
        Detects tables on the given page using PyMuPDF and returns them as markdown-formatted clauses.
        """
        table_clauses: List[Dict[str, Any]] = []
        try:
            tabs = page.find_tables()
            if not tabs or not tabs.tables:
                return []

            for idx, tab in enumerate(tabs.tables):
                extracted = tab.extract()
                if not extracted or len(extracted) < 2:
                    continue

                # Filter empty rows
                clean_rows = []
                for row in extracted:
                    cleaned_row = [str(cell or "").strip().replace("\n", " ") for cell in row]
                    if any(c for c in cleaned_row):
                        clean_rows.append(cleaned_row)

                if len(clean_rows) < 2:
                    continue

                # Check number of columns
                num_cols = len(clean_rows[0])
                header = clean_rows[0]
                divider = ["---"] * num_cols

                lines = [
                    "| " + " | ".join(header) + " |",
                    "| " + " | ".join(divider) + " |"
                ]
                for data_row in clean_rows[1:]:
                    # Pad or trim to matching columns
                    padded = (data_row + [""] * num_cols)[:num_cols]
                    lines.append("| " + " | ".join(padded) + " |")

                table_md = "\n".join(lines)
                table_clauses.append({
                    "page": page_num,
                    "section": current_section,
                    "clause_number": f"Table {idx + 1}",
                    "text": f"Policy Benefit & Limit Schedule (Table):\n{table_md}",
                    "is_table": True
                })
        except Exception as e:
            logger.warning(f"Error extracting tables on page {page_num}: {e}")

        return table_clauses

    @classmethod
    def inspect_and_extract(cls, file_path: Path) -> Dict[str, Any]:
        """
        Extracts pages and structure from a PDF file using PyMuPDF.
        Preserves page numbers, section headers, clause identifiers, and tabular structures.
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

            # 1. First extract any structured tables on this page
            table_clauses = cls._extract_markdown_tables(page, page_num, current_section)

            # 2. Extract page text
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

            # 3. Process text line-by-line
            raw_lines = clean_page_text.splitlines()
            lines = [l.strip() for l in raw_lines if not cls._is_header_footer(l)]

            buffer_clause = []
            active_clause_num = None

            for line in lines:
                # Check for Section Heading
                is_section = False
                for pattern in cls.SECTION_PATTERNS:
                    match = pattern.match(line)
                    if match:
                        if buffer_clause:
                            clause_text = " ".join(buffer_clause).strip()
                            if len(clause_text) > 25:
                                sub_chunks = cls._split_oversized_clause(
                                    clause_text, page_num, current_section, active_clause_num
                                )
                                all_clauses.extend(sub_chunks)
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
                clause_match = cls.CLAUSE_NUMBER_PATTERN.match(line)
                if clause_match:
                    if buffer_clause:
                        clause_text = " ".join(buffer_clause).strip()
                        if len(clause_text) > 25:
                            sub_chunks = cls._split_oversized_clause(
                                clause_text, page_num, current_section, active_clause_num
                            )
                            all_clauses.extend(sub_chunks)
                        buffer_clause = []

                    active_clause_num = clause_match.group(1)
                    buffer_clause.append(line)
                else:
                    # Check paragraph break or list bullet
                    if len(buffer_clause) > 0 and (line.startswith("•") or line.startswith("-") or line.startswith("*") or line.startswith("—")):
                        clause_text = " ".join(buffer_clause).strip()
                        if len(clause_text) > 25:
                            sub_chunks = cls._split_oversized_clause(
                                clause_text, page_num, current_section, active_clause_num
                            )
                            all_clauses.extend(sub_chunks)
                        buffer_clause = [line]
                    else:
                        buffer_clause.append(line)

            # Flush remaining clause buffer on page
            if buffer_clause:
                clause_text = " ".join(buffer_clause).strip()
                if len(clause_text) > 25:
                    sub_chunks = cls._split_oversized_clause(
                        clause_text, page_num, current_section, active_clause_num
                    )
                    all_clauses.extend(sub_chunks)

            # Append any extracted tables for this page
            if table_clauses:
                all_clauses.extend(table_clauses)

        doc.close()

        # Check for scanned image-only PDF
        is_scanned = (total_words < 15 or total_chars < 80) and total_pages > 0

        # If few clauses detected due to non-standard formatting, perform fallback paragraph chunking
        if len(all_clauses) < 5 and not is_scanned:
            all_clauses = cls._fallback_paragraph_segmentation(pages_data)

        logger.info(f"PDF extraction complete: {total_pages} pages, {total_words} words, {len(all_clauses)} bounded clauses.")

        return {
            "total_pages": total_pages,
            "total_words": total_words,
            "total_chars": total_chars,
            "is_scanned": is_scanned,
            "pages": pages_data,
            "sections": all_sections,
            "clauses": all_clauses
        }

    @classmethod
    def _fallback_paragraph_segmentation(cls, pages_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Structure-aware paragraph segmentation preserving page numbers and enforcing bounded chunks.
        """
        clauses = []
        for p in pages_data:
            page_num = p["page"]
            text = p["text"]
            # Split by double newline or large paragraph breaks
            paragraphs = re.split(r"\n\s*\n", text)
            para_idx = 1
            for para in paragraphs:
                clean_p = " ".join(para.split()).strip()
                if len(clean_p) > 30:
                    sub_chunks = cls._split_oversized_clause(
                        clean_p, page_num, "General Terms & Clauses", f"Section Item {para_idx}"
                    )
                    clauses.extend(sub_chunks)
                    para_idx += 1
        return clauses
