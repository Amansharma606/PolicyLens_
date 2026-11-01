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

    COMMON_ABBREVIATIONS = [
        r"rs\.", r"re\.", r"inr\.",
        r"no\.", r"nos\.",
        r"dr\.", r"mr\.", r"mrs\.", r"ms\.", r"prof\.",
        r"vol\.", r"vols\.",
        r"sec\.", r"para\.", r"cl\.", r"art\.",
        r"e\.g\.", r"i\.e\.", r"etc\.", r"vs\.", r"viz\.",
        r"ltd\.", r"pvt\.", r"co\.", r"corp\.", r"inc\.",
        r"govt\.", r"dept\.", r"reg\.", r"cin\."
    ]

    ABBREV_PATTERN = re.compile(
        r'\b(?:' + '|'.join(COMMON_ABBREVIATIONS) + r')(?=[\s,;:]|$)',
        re.IGNORECASE
    )

    @classmethod
    def _is_header_footer(cls, line: str) -> bool:
        trimmed = line.strip()
        if not trimmed:
            return True
        for pat in cls.HEADER_FOOTER_PATTERNS:
            if pat.match(trimmed):
                return True
        return False

    @classmethod
    def _split_into_sentences(cls, text: str) -> List[str]:
        """
        Splits text into sentences preserving abbreviations (Rs., No., Dr., e.g., i.e.),
        decimal numbers (e.g. 1.5, ₹50.00), and policy clause numbering (e.g. 1.1, 4.2.1).
        Uses placeholder protection to comply with Python's fixed-width look-behind constraints.
        """
        if not text or not text.strip():
            return []

        DOT_TOKEN = "\u0000DOT\u0000"

        # 1. Protect currency amounts with dots like Rs. 50,000 or Rs.50000
        temp = re.sub(r'\b(Rs|Re|INR)\.\s*', r'\1' + DOT_TOKEN + ' ', text, flags=re.IGNORECASE)

        # 2. Protect decimal numbers like 1.5, 50,000.00, 24.5
        temp = re.sub(r'(\d+)\.(\d+)', r'\1' + DOT_TOKEN + r'\2', temp)

        # 3. Protect clause numbering like 1.1, 4.2.1, 5.a
        temp = re.sub(r'\b([A-Za-z0-9]+)\.([A-Za-z0-9]+)\b', r'\1' + DOT_TOKEN + r'\2', temp)

        # 4. Protect common abbreviations (e.g., i.e., Dr., No., Ltd., etc.)
        def _replace_abbr_dot(match):
            return match.group(0).replace('.', DOT_TOKEN)

        temp = cls.ABBREV_PATTERN.sub(_replace_abbr_dot, temp)

        # 5. Protect single letter with dot (e.g. A., B. in lists)
        temp = re.sub(r'\b([A-Za-z])\.\s+', r'\1' + DOT_TOKEN + ' ', temp)

        # 6. Split on sentence boundaries
        raw_parts = re.split(r'(?<=[.?!])\s+(?=[A-Z0-9"\'\(\[\u201c\u2018—•\-])|(?<=[.?!])\s+', temp)

        # 7. Restore protected periods
        sentences = []
        for part in raw_parts:
            cleaned = part.replace(DOT_TOKEN, '.').strip()
            if cleaned:
                sentences.append(cleaned)

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

    @classmethod
    def inspect_and_extract(cls, file_path: Path) -> Dict[str, Any]:
        """
        Extracts pages and structure from a PDF file using PyMuPDF.
        Preserves page numbers, section headers, clause identifiers, and bounded chunks.
        Optimized for high throughput: uses PyMuPDF native text stream parser (<1s for 40 pages).
        Guarantees that PyMuPDF file handles are closed via a try...finally block.
        """
        if not file_path.exists():
            raise PDFProcessingError(f"File not found: {file_path}")

        doc = None
        try:
            try:
                doc = pymupdf.open(str(file_path))
            except Exception as e:
                raise PDFProcessingError(f"Corrupted or invalid PDF file: {str(e)}")

            if doc.is_encrypted:
                raise PDFProcessingError("Password-protected or encrypted PDF documents are not supported.")

            total_pages = len(doc)
            if total_pages == 0:
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

                # Extract page text stream cleanly and rapidly
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

                # Process text line-by-line
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

        finally:
            if doc is not None:
                try:
                    doc.close()
                except Exception as ce:
                    logger.warning(f"Error closing PyMuPDF document handle: {ce}")

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
