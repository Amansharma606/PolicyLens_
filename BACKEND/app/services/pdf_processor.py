import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Set
import pymupdf  # PyMuPDF (fitz)
from app.core.logging import logger


class PDFProcessingError(Exception):
    pass


class PDFProcessor:
    """
    Universal Layout-Aware Insurance Policy PDF Processor.
    Combines PyMuPDF bounding-box XY-cut column sorting with pdfplumber + PyMuPDF
    geometric table extraction, font-guided heading detection, universal text/ligature
    normalization, repeated header/footer/watermark stripping, and structure-aware
    semantic clause chunking (80-250 words with sentence-boundary overlaps).
    Works across Health, Motor, Life/Term, Travel, Personal Accident, and Brochures.
    """

    # Ligature and PDF glyph artifact repair map (handles standard Unicode & custom CMap substitutions)
    LIGATURE_MAP = {
        "\u0123": "ff",
        "\u0124": "fi",
        "\u0125": "fl",
        "\u0126": "ffi",
        "\u0127": "ffl",
        "\ufb00": "ff",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\ufb03": "ffi",
        "\ufb04": "ffl",
        "\ufb05": "st",
        "\ufb06": "st",
        "\u00a0": " ",
        "\u200b": "",
        "\ufeff": "",
        "\u00ad": "",
    }

    SECTION_PATTERNS = [
        re.compile(r"^(?:SECTION|PART|MODULE|ARTICLE|CHAPTER|ANNEXURE)\s+([0-9IVXLCDM]+|[A-Z])(?:[:\.\-\s]+(.+))?$", re.IGNORECASE),
        re.compile(r"^(\d+(?:\.\d+)?|\b[A-Z]\.)\s+([A-Z][A-Za-z0-9\s,&/\-()]{2,70})$"),
        re.compile(
            r"^(?:COVERAGE(?:S)?|BENEFITS?|KEY\s+FEATURES|EXCLUSIONS?|KEY\s+EXCLUSIONS?|PERMANENT\s+EXCLUSIONS?|"
            r"WAITING\s+PERIODS?|GENERAL\s+CONDITIONS?|STANDARD\s+CONDITIONS?|DEFINITIONS?|STANDARD\s+DEFINITIONS?|"
            r"CLAIM\s+(?:PROCEDURES?|PROCESS)|LIMITS?\s+OF\s+LIABILITY|GRIEVANCE\s+REDRESSAL|"
            r"ELIGIBILITY|PREAMBLE|OPERATING\s+CLAUSE|OPTIONAL\s+COVER(?:S)?)(?:\s*[:\-–].{0,40})?$",
            re.IGNORECASE,
        ),
    ]

    CLAUSE_NUMBER_PATTERN = re.compile(
        r"^(?:Clause\s+|Section\s+|Article\s+|Def\.?\s+)?(\d+(?:\.\d+)*(?:\([a-z0-9]+\))?|[a-z]\)|\([a-z0-9]+\)|[ivxlcdm]+\.)\s*(?:[:\.\-])?\s*(.+)",
        re.IGNORECASE,
    )

    HEADER_FOOTER_PATTERNS = [
        re.compile(r"^(?:Page\s+\d+(?:\s+of\s+\d+)?|\d+\s+of\s+\d+|P\.\s*\d+)$", re.IGNORECASE),
        re.compile(r"^IRDAI\s+Reg(?:istration)?\.?\s*No.*$", re.IGNORECASE),
        re.compile(r"^CIN\s*:\s*[A-Z0-9]+$", re.IGNORECASE),
        re.compile(r"^(?:Policy\s+Wording\s*[-–|]\s*.*|UIN\s*:\s*[A-Z0-9\-]+)$", re.IGNORECASE),
    ]

    COMMON_ABBREVIATIONS = [
        r"rs\.", r"re\.", r"inr\.",
        r"no\.", r"nos\.",
        r"dr\.", r"mr\.", r"mrs\.", r"ms\.", r"prof\.",
        r"vol\.", r"vols\.",
        r"sec\.", r"para\.", r"cl\.", r"art\.", r"def\.",
        r"e\.g\.", r"i\.e\.", r"etc\.", r"vs\.", r"viz\.",
        r"ltd\.", r"pvt\.", r"co\.", r"corp\.", r"inc\.",
        r"govt\.", r"dept\.", r"reg\.", r"cin\.", r"sr\.", r"sl\."
    ]

    ABBREV_PATTERN = re.compile(
        r"\b(?:" + "|".join(COMMON_ABBREVIATIONS) + r")(?=[\s,;:]|$)",
        re.IGNORECASE,
    )

    COMPOUND_HYPHEN_PREFIXES = {
        "pre", "post", "non", "co", "self", "sub", "anti", "re", "semi",
        "day", "in", "out", "all", "one", "two", "three", "multi", "year",
        "no", "life", "long", "short", "full", "half", "third", "first",
    }

    TABLE_HEADER_KEYWORDS = (
        "sum insured", "sum assured", "sr. no", "sr no", "s.no", "s no", "sl no", "si no",
        "limit", "benefit", "coverage", "item", "points", "discount", "package",
        "office details", "jurisdiction", "areas of jurisdiction", "helpline",
        "type of claim", "time limit", "description", "particulars", "age", "email", "contact"
    )

    OMBUDSMAN_HINTS = ("ombudsman", "bimalokpal", "cioins", "areas of jurisdiction", "office details")
    NON_MEDICAL_HINTS = ("baby food", "admission/registration", "hair removal", "non-medical", "non-payable", "eye pad", "oxygen cylinder", "clean sheet")
    TOC_HINTS = ("table of contents", "page no.", "page no")

    @classmethod
    def normalize_text(cls, text: str) -> str:
        if not text:
            return ""
        for k, v in cls.LIGATURE_MAP.items():
            if k in text:
                text = text.replace(k, v)
        # Replace middle dot between letters used as separator (e.g. from·the)
        text = re.sub(r"(?<=[A-Za-z])\u00b7(?=[A-Za-z])", " ", text)
        # Clean stray whitespace around slashes/commas/currency artifacts
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    @classmethod
    def _normalize_margin_key(cls, line: str) -> str:
        s = cls.normalize_text(line).lower()
        s = re.sub(r"\d+", "#", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @classmethod
    def _is_header_footer(cls, line: str) -> bool:
        trimmed = cls.normalize_text(line)
        if not trimmed:
            return True
        for pat in cls.HEADER_FOOTER_PATTERNS:
            if pat.match(trimmed):
                return True
        return False

    @classmethod
    def _detect_document_profile(cls, doc: pymupdf.Document) -> Tuple[Set[str], float, Dict[str, str], List[Dict[str, Any]]]:
        """
        Single-pass lightweight inspection across pages (caches get_text('dict') once per page):
        1. Collect repeated running headers & footers (appearing in top/bottom 13% on >= 30% of pages).
        2. Estimate median body font size for font-guided section heading detection.
        3. Extract Page 1 cover/header metadata before headers get stripped from body clauses.
        """
        total_pages = len(doc)
        threshold = max(3, int(total_pages * 0.30)) if total_pages >= 3 else total_pages + 1

        margin_counts: Dict[str, int] = {}
        font_size_weights: Dict[float, int] = {}
        page1_top_lines: List[str] = []
        cached_dicts: List[Dict[str, Any]] = []

        for p_idx, page in enumerate(doc):
            h = page.rect.height
            seen_margin: Set[str] = set()
            text_dict = page.get_text("dict")
            cached_dicts.append(text_dict)
            for b in text_dict.get("blocks", []):
                if b.get("type") != 0:
                    continue
                for ln in b.get("lines", []):
                    if ln.get("dir", (1, 0)) != (1, 0):
                        continue
                    y0, y1 = ln["bbox"][1], ln["bbox"][3]
                    txt = cls.normalize_text("".join(s.get("text", "") for s in ln.get("spans", [])))
                    if not txt:
                        continue

                    if p_idx == 0 and y0 < h * 0.25:
                        page1_top_lines.append(txt)

                    if y0 < h * 0.13 or y1 > h * 0.87:
                        key = cls._normalize_margin_key(txt)
                        if key and key not in seen_margin:
                            seen_margin.add(key)
                            margin_counts[key] = margin_counts.get(key, 0) + 1
                    else:
                        for s in ln.get("spans", []):
                            st = s.get("text", "").strip()
                            if st:
                                sz = round(float(s.get("size", 10.0)), 1)
                                font_size_weights[sz] = font_size_weights.get(sz, 0) + len(st)

        repeated_headers = {k for k, v in margin_counts.items() if v >= threshold}

        # Weighted mode = body font size
        body_font_size = 10.0
        if font_size_weights:
            body_font_size = max(font_size_weights.items(), key=lambda kv: kv[1])[0]

        metadata = cls._extract_cover_metadata(page1_top_lines, doc[0] if total_pages > 0 else None)
        return repeated_headers, body_font_size, metadata, cached_dicts

    @classmethod
    def _extract_cover_metadata(cls, top_lines: List[str], page1: Optional[pymupdf.Page]) -> Dict[str, str]:
        meta: Dict[str, str] = {}
        if page1 is None:
            return meta
        full_p1 = " ".join(cls.normalize_text(page1.get_text("text")).splitlines())
        full_p1 = re.sub(r"\s+", " ", full_p1)
        uin_m = re.search(r"\bUIN\s*[:\-]?\s*(?:[A-Za-z0-9\s]+-\s*)?([A-Z0-9]{10,25})\b", full_p1, re.IGNORECASE)
        if not uin_m:
            uin_m = re.search(r"\bUIN\s*[:\-]?\s*([A-Z0-9\- ]{8,35})", full_p1, re.IGNORECASE)
        if uin_m:
            meta["uin"] = uin_m.group(1).strip()
        irdai_m = re.search(r"IRDAI\s+Reg(?:istration)?\.?\s*No\.?\s*[:\-]?\s*(\d+)", full_p1, re.IGNORECASE)
        if irdai_m:
            meta["irdai_reg"] = irdai_m.group(1).strip()
        if top_lines:
            meta["header_sample"] = " | ".join(top_lines[:4])
        return meta

    @classmethod
    def _extract_dict_lines(cls, text_dict: Dict[str, Any]) -> List[Tuple[float, float, float, float, str]]:
        lines: List[Tuple[float, float, float, float, str]] = []
        for b in text_dict.get("blocks", []):
            if b.get("type") != 0:
                continue
            for ln in b.get("lines", []):
                if ln.get("dir", (1, 0)) != (1, 0):
                    continue
                lx0, ly0, lx1, ly1 = ln["bbox"]
                txt = cls.normalize_text("".join(s.get("text", "") for s in ln.get("spans", [])))
                if txt:
                    lines.append((ly0, lx0, lx1, ly1, txt))
        return lines

    @classmethod
    def _extract_clip_lines(cls, page_lines: List[Tuple[float, float, float, float, str]], bbox: Tuple[float, float, float, float]) -> List[Tuple[float, float, float, float, str]]:
        """
        Filters cached page lines strictly belonging inside a cell/region in microseconds.
        """
        x0, y0, x1, y1 = bbox
        matched = [
            ln for ln in page_lines
            if (x0 - 3.0 <= ((ln[1] + ln[2]) / 2.0) <= x1 + 3.0)
            and (y0 - 3.0 <= ((ln[0] + ln[3]) / 2.0) <= y1 + 3.0)
        ]
        matched.sort(key=lambda item: (round(item[0], 1), round(item[1], 1)))
        return matched

    @classmethod
    def _clean_cell_lines(cls, lines: List[Tuple[float, float, float, float, str]]) -> str:
        if not lines:
            return ""
        # Check whether lines form spaced items vs wrapped sentence
        joined = " ".join(item[4] for item in lines)
        joined = re.sub(r"\s+([,.;:?!])", r"\1", joined)
        joined = re.sub(r"\(\s+", "(", joined)
        joined = re.sub(r"\s+\)", ")", joined)
        # Fix spaced currency separators like "5 ,00 ,000/ -" -> "5,00,000/-"
        joined = re.sub(r"(\d)\s*,\s*(\d)", r"\1,\2", joined)
        joined = re.sub(r"(\d)\s*/\s*-", r"\1/-", joined)
        return re.sub(r"\s+", " ", joined).strip()

    @classmethod
    def _cluster_coords(cls, vals: List[float], tol: float = 3.5) -> List[float]:
        if not vals:
            return []
        svals = sorted(vals)
        groups = [[svals[0]]]
        for v in svals[1:]:
            if v - groups[-1][-1] <= tol:
                groups[-1].append(v)
            else:
                groups.append([v])
        return [sum(g) / len(g) for g in groups]

    @classmethod
    def _extract_tables_from_page(
        cls,
        fpage: pymupdf.Page,
        page_lines: List[Tuple[float, float, float, float, str]],
        page_num: int,
        repeated_headers: Set[str],
    ) -> Tuple[List[Dict[str, Any]], List[Tuple[float, float, float, float]]]:
        """
        Pure-PyMuPDF (~1-5ms/page) geometric multi-column table extractor using C-speed vector
        drawings + CMap-faithful span clipping. Replaces slow pure-Python pdfplumber/pdfminer.
        """
        page_h, page_w = fpage.rect.height, fpage.rect.width
        try:
            drawings = fpage.get_drawings()
        except Exception:
            return [], []

        if not drawings or len(drawings) > 1200:
            return [], []

        h_segs: List[Tuple[float, float, float]] = []
        v_segs: List[Tuple[float, float, float]] = []
        card_boxes: List[Tuple[float, float, float, float]] = []

        for d in drawings:
            rc = d.get("rect")
            if rc is None:
                continue
            rw, rh = rc.x1 - rc.x0, rc.y1 - rc.y0
            if (rw > 0.92 * page_w and rh > 0.85 * page_h) or rc.y1 < 0.07 * page_h or rc.y0 > 0.91 * page_h:
                continue
            if rw >= 60 and rh >= 30 and rh <= 0.80 * page_h:
                card_boxes.append((rc.x0, rc.y0, rc.x1, rc.y1))

            for it in d.get("items", []):
                kind = it[0]
                if kind == "re":
                    r = it[1]
                    rrw, rrh = r.x1 - r.x0, r.y1 - r.y0
                    if r.y1 < 0.07 * page_h or r.y0 > 0.91 * page_h or rrw > 0.94 * page_w:
                        continue
                    if rrh <= 4.0 and rrw >= 25.0:
                        h_segs.append((r.x0, r.x1, (r.y0 + r.y1) / 2.0))
                    elif rrw <= 4.0 and rrh >= 10.0:
                        v_segs.append(((r.x0 + r.x1) / 2.0, r.y0, r.y1))
                    elif rrw >= 20.0 and 8.0 <= rrh <= 0.65 * page_h:
                        h_segs.extend([(r.x0, r.x1, r.y0), (r.x0, r.x1, r.y1)])
                        v_segs.extend([(r.x0, r.y0, r.y1), (r.x1, r.y0, r.y1)])
                elif kind == "l":
                    p1, p2 = it[1], it[2]
                    if abs(p1.y - p2.y) <= 1.5 and abs(p1.x - p2.x) >= 25.0 and 0.07 * page_h <= p1.y <= 0.91 * page_h:
                        h_segs.append((min(p1.x, p2.x), max(p1.x, p2.x), (p1.y + p2.y) / 2.0))
                    elif abs(p1.x - p2.x) <= 1.5 and abs(p1.y - p2.y) >= 10.0 and 0.04 * page_w <= p1.x <= 0.96 * page_w:
                        v_segs.append(((p1.x + p2.x) / 2.0, min(p1.y, p2.y), max(p1.y, p2.y)))

        if len(h_segs) < 3 or len(v_segs) < 2:
            return [], []

        # Group vertical intervals of table grid primitives into separate table regions on this page
        y_spans: List[Tuple[float, float]] = [(y, y) for _, _, y in h_segs] + [(y0, y1) for _, y0, y1 in v_segs]
        y_spans.sort(key=lambda s: s[0])
        regions: List[Tuple[float, float]] = []
        for s0, s1 in y_spans:
            if not regions or s0 > regions[-1][1] + 10.0:
                regions.append((s0, s1))
            else:
                regions[-1] = (regions[-1][0], max(regions[-1][1], s1))

        extracted_tables: List[Dict[str, Any]] = []
        table_bboxes: List[Tuple[float, float, float, float]] = []

        for reg_y0, reg_y1 in regions:
            if (reg_y1 - reg_y0) < 16.0:
                continue
            reg_h = [s for s in h_segs if reg_y0 - 2.0 <= s[2] <= reg_y1 + 2.0]
            reg_v = [s for s in v_segs if not (s[2] < reg_y0 - 2.0 or s[1] > reg_y1 + 2.0)]
            if len(reg_h) < 3 or len(reg_v) < 2:
                continue

            xs = cls._cluster_coords([v[0] for v in reg_v] + [x for h0, h1, _ in reg_h for x in (h0, h1)], tol=4.5)
            ys = cls._cluster_coords([h[2] for h in reg_h] + [y for _, v0, v1 in reg_v for y in (v0, v1)], tol=3.5)

            if len(xs) < 3 or len(ys) < 3:
                continue

            tx0, tx1 = xs[0], xs[-1]
            ty0, ty1 = ys[0], ys[-1]
            if (tx1 - tx0) < 60 or (ty1 - ty0) < 14:
                continue

            col_bounds = [(xs[i], xs[i + 1]) for i in range(len(xs) - 1) if (xs[i + 1] - xs[i]) >= 12.0]
            row_bounds = [(ys[i], ys[i + 1]) for i in range(len(ys) - 1) if (ys[i + 1] - ys[i]) >= 6.0]
            if len(col_bounds) < 2 or len(row_bounds) < 2:
                continue

            # Enclosing colored card box check
            encl_top, encl_bot = ty0, ty1
            for sx0, stop, sx1, sbot in card_boxes:
                if abs(sx0 - tx0) <= 10 and abs(sx1 - tx1) <= 10 and (sbot - stop) > (ty1 - ty0):
                    if stop <= ty0 + 4 and sbot >= ty1 - 4:
                        encl_top = min(encl_top, stop)
                        encl_bot = max(encl_bot, sbot)

            rows: List[List[str]] = []
            banner_title: Optional[str] = None

            if encl_top < ty0 - 4:
                top_lines = cls._extract_clip_lines(page_lines, (tx0 - 2, encl_top - 1, tx1 + 2, ty0 - 1))
                bands: List[List[Tuple[float, float, float, float, str]]] = []
                for ln in top_lines:
                    if not bands or (ln[0] - bands[-1][-1][3]) > 3.5:
                        bands.append([ln])
                    else:
                        bands[-1].append(ln)
                for band in bands:
                    col_cells = [[] for _ in col_bounds]
                    unassigned = []
                    for ln in band:
                        cx = (ln[1] + ln[2]) / 2.0
                        matched_cx = [ci for ci, (c0, c1) in enumerate(col_bounds) if c0 - 6 <= cx <= c1 + 6]
                        if len(matched_cx) == 1 and (ln[2] - ln[1]) <= (col_bounds[matched_cx[0]][1] - col_bounds[matched_cx[0]][0] + 18):
                            col_cells[matched_cx[0]].append(ln)
                        else:
                            unassigned.append(ln[4])
                    if sum(1 for cc in col_cells if cc) >= 2:
                        rows.append([cls._clean_cell_lines(cc) for cc in col_cells])
                    elif unassigned:
                        cand_title = " ".join(unassigned).strip()
                        if cand_title:
                            banner_title = f"{banner_title} — {cand_title}".strip(" —") if banner_title else cand_title

            for ry0, ry1 in row_bounds:
                r_cells = []
                for cx0, cx1 in col_bounds:
                    clines = cls._extract_clip_lines(page_lines, (cx0, ry0, cx1, ry1))
                    r_cells.append(cls._clean_cell_lines(clines))

                if rows == [] and (ry0 < page_h * 0.13 or ry1 > page_h * 0.87):
                    if all((cls._normalize_margin_key(c) in repeated_headers or not c) for c in r_cells):
                        continue

                if any(c for c in r_cells):
                    rows.append(r_cells)

            if not rows:
                continue

            non_empty_cols = [
                ci for ci in range(len(rows[0]))
                if any((ci < len(r) and bool(r[ci].strip())) for r in rows)
            ]
            if len(non_empty_cols) < 2:
                continue
            rows = [[r[ci] if ci < len(r) else "" for ci in non_empty_cols] for r in rows]

            flat_sample = " ".join(" ".join(r) for r in rows[:6]).lower() + " " + (banner_title or "").lower()
            if any(h in flat_sample for h in cls.TOC_HINTS) and ("page" in flat_sample or page_num <= 2):
                table_role = "toc"
            elif any(h in flat_sample for h in cls.OMBUDSMAN_HINTS):
                table_role = "ombudsman"
            elif any(h in flat_sample for h in cls.NON_MEDICAL_HINTS):
                table_role = "non_medical_list"
            else:
                table_role = "policy_table"

            full_bbox = (tx0 - 2, encl_top - 2, tx1 + 2, encl_bot + 2)
            table_bboxes.append(full_bbox)
            extracted_tables.append({
                "bbox": full_bbox,
                "y0": encl_top,
                "title": banner_title,
                "rows": rows,
                "role": table_role,
            })

        return extracted_tables, table_bboxes

    @classmethod
    def _format_table_markdown_and_statements(
        cls,
        table: Dict[str, Any],
        active_section: str,
    ) -> Tuple[str, List[str]]:
        """
        Converts a cleaned multi-column table into:
        1. A clean Markdown table (for readable page text preview).
        2. Self-contained Key: Value semantic statements pairing row cells with headers
           so embeddings, BM25, and LLM readers never lose column context.
        """
        rows = table["rows"]
        title = table.get("title") or active_section
        ncols = len(rows[0])

        # Clean Markdown representation
        md_lines = []
        if table.get("title"):
            md_lines.append(f"**{table['title']}**")

        # Detect whether Row 0 is a genuine column header row vs a 2-column Key-Value data row
        row0_lower = " ".join(rows[0]).lower()
        row0_has_long_prose = any(len(c.strip()) > 50 or ": " in c or c.strip().endswith(".") for c in rows[0] if c.strip())
        row0_is_header = False
        if not row0_has_long_prose:
            if any(kw in row0_lower for kw in cls.TABLE_HEADER_KEYWORDS):
                row0_is_header = True
            elif ncols >= 3 and len(rows) >= 2 and all(len(c) <= 65 for c in rows[0]):
                row0_is_header = True

        # Build Markdown table
        hdr = rows[0] if row0_is_header else (["Attribute", "Details"] if ncols == 2 else [f"Column {i+1}" for i in range(ncols)])
        data_rows = rows[1:] if row0_is_header else rows

        # Handle double-row table headers like ["", "Limit for Delivery", "", "Limit of Company's"] + ["Sum Insured", "Normal...", "Caesarean...", "New Born..."]
        if row0_is_header and len(data_rows) >= 1:
            r0_nonempty = sum(1 for c in hdr if c)
            r1_nonempty = sum(1 for c in data_rows[0] if c)
            r1_has_data = any(
                re.search(r"\d[\d,]*/-|\b\d+\s*(?:years?|months?|days?|%)\b", c, re.IGNORECASE)
                or len(c.strip()) > 55
                for c in data_rows[0]
            )
            r1_lower = " ".join(data_rows[0]).lower()
            if not r1_has_data and (
                (r0_nonempty < ncols and r1_nonempty >= r0_nonempty)
                or any(kw in r1_lower for kw in ("normal", "caesarean", "sum insured", "delivery", "cover"))
            ):
                merged_hdr = []
                for ci in range(ncols):
                    p0 = hdr[ci].strip() if ci < len(hdr) else ""
                    p1 = data_rows[0][ci].strip() if ci < len(data_rows[0]) else ""
                    if p0 and p1:
                        if p0.lower() in p1.lower():
                            merged_hdr.append(p1)
                        elif p1.lower() in p0.lower():
                            merged_hdr.append(p0)
                        else:
                            # Combine cleanly without duplicating overlapping words
                            merged_hdr.append(f"{p0} ({p1})" if len(p1) < len(p0) else f"{p0} - {p1}")
                    else:
                        merged_hdr.append(p1 or p0 or f"Column {ci+1}")
                hdr = merged_hdr
                data_rows = data_rows[1:]

        md_lines.append("| " + " | ".join(hdr) + " |")
        md_lines.append("| " + " | ".join(["---"] * ncols) + " |")
        for dr in data_rows:
            md_lines.append("| " + " | ".join(dr) + " |")
        markdown_str = "\n".join(md_lines)

        # Build self-contained semantic Key: Value statements
        statements: List[str] = []
        role = table.get("role", "policy_table")

        if role == "toc":
            return markdown_str, []

        if role == "non_medical_list":
            # Condense 2-col or 4-col item lists cleanly
            items = []
            for dr in data_rows:
                for ci in range(0, len(dr)):
                    val = dr[ci].strip()
                    if val and not re.fullmatch(r"\d{1,3}\.?", val):
                        items.append(val)
            if items:
                for start in range(0, len(items), 15):
                    batch_items = "; ".join(items[start:start + 15])
                    statements.append(f"Non-medical / non-payable items listed in {title}: {batch_items}.")
            return markdown_str, statements

        if ncols == 2 and not row0_is_header:
            # Direct Key: Value table (e.g. CIS Benefit Table, Claim Requirements, Escalation Levels)
            for dr in data_rows:
                k = dr[0].strip().rstrip(":")
                v = dr[1].strip() if len(dr) > 1 else ""
                if k and v:
                    statements.append(f"[{title}] {k}: {v}")
                elif v:
                    statements.append(f"[{title}] {v}")
        else:
            # Headered multi-column table -> pair every cell with its explicit column header!
            for dr in data_rows:
                pairs = []
                for ci in range(min(len(hdr), len(dr))):
                    h_label = hdr[ci].strip() or f"Column {ci+1}"
                    val = dr[ci].strip()
                    if val:
                        pairs.append(f"{h_label}: {val}")
                if pairs:
                    prefix = f"[{title}] " if title else ""
                    statements.append(prefix + "; ".join(pairs) + ".")

        return markdown_str, statements

    @classmethod
    def _xy_cut_sort_lines(cls, lines: List[Dict[str, Any]], page_width: float, page_height: float, depth: int = 0) -> List[Dict[str, Any]]:
        """
        Recursive XY-Cut geometric reading-order sorter:
        1. Separates full-width banners/titles sitting above multi-column regions.
        2. Uses a 1D horizontal occupancy histogram to find true vertical column gutters (>= 4pt)
           and reads Left Column top-to-bottom BEFORE Right Column top-to-bottom.
        3. Re-orders out-of-order brochure text blocks purely top-to-bottom when single-column.
        """
        if len(lines) <= 1 or depth > 10:
            return sorted(lines, key=lambda l: (round(l["y0"], 1), round(l["x0"], 1)))

        y_sorted = sorted(lines, key=lambda l: (l["y0"], l["y1"]))

        # Step 1: Identify wide/large centered title banner lines at top of page (depth == 0)
        # so they sit first and never bridge/block a two-column vertical gutter underneath.
        if depth == 0 and len(y_sorted) >= 6:
            banner_lines = []
            remaining = []
            for ln in y_sorted:
                is_top_banner = (
                    ln["y0"] < page_height * 0.22
                    and (
                        (ln["x0"] < page_width * 0.44 and ln["x1"] > page_width * 0.56 and ln.get("size", 10.0) >= 10.5)
                        or ln.get("size", 10.0) >= 12.5
                    )
                    and len(ln["text"]) <= 80
                )
                if is_top_banner and not remaining:
                    banner_lines.append(ln)
                else:
                    remaining.append(ln)
            if banner_lines and remaining and len(banner_lines) <= 4:
                return (
                    sorted(banner_lines, key=lambda l: (round(l["y0"], 1), round(l["x0"], 1)))
                    + cls._xy_cut_sort_lines(remaining, page_width, page_height, depth + 1)
                )

        # Step 2: Horizontal occupancy projection to detect clean multi-column gutters
        W = max(int(page_width) + 4, int(max(l["x1"] for l in lines)) + 4)
        occ = [0] * W
        for l in lines:
            sx0 = max(0, int(l["x0"]) + 1)
            sx1 = min(W - 1, int(l["x1"]) - 1)
            if sx1 < sx0:
                sx0 = max(0, int(l["x0"]))
                sx1 = min(W - 1, int(l["x1"]))
            for x in range(sx0, sx1 + 1):
                occ[x] += 1

        non_zero = [x for x, v in enumerate(occ) if v > 0]
        best_gutter = None
        if non_zero:
            x_lo, x_hi = non_zero[0], non_zero[-1]
            if (x_hi - x_lo) > page_width * 0.42:
                in_gap = False
                g_start = 0
                for x in range(x_lo, x_hi + 1):
                    if occ[x] == 0:
                        if not in_gap:
                            in_gap = True
                            g_start = x
                    else:
                        if in_gap:
                            g_len = x - g_start
                            if g_len >= 4:
                                mid = (g_start + x) / 2.0
                                left = [l for l in lines if (l["x0"] + l["x1"]) / 2.0 < mid]
                                right = [l for l in lines if (l["x0"] + l["x1"]) / 2.0 >= mid]
                                l_chars = sum(len(l["text"]) for l in left)
                                r_chars = sum(len(l["text"]) for l in right)
                                if len(left) >= 2 and len(right) >= 2 and l_chars >= 30 and r_chars >= 30:
                                    if best_gutter is None or g_len > best_gutter[0]:
                                        best_gutter = (g_len, mid, left, right)
                            in_gap = False

        if best_gutter is not None:
            _, _, left, right = best_gutter
            return (
                cls._xy_cut_sort_lines(left, page_width, page_height, depth + 1)
                + cls._xy_cut_sort_lines(right, page_width, page_height, depth + 1)
            )

        # Step 3: Split on clean Y-gaps >= 16pt (separates top headings/cards from lower blocks)
        max_y_end = y_sorted[0]["y1"]
        for i in range(1, len(y_sorted)):
            if (y_sorted[i]["y0"] - max_y_end) >= 16.0:
                return (
                    cls._xy_cut_sort_lines(y_sorted[:i], page_width, page_height, depth + 1)
                    + cls._xy_cut_sort_lines(y_sorted[i:], page_width, page_height, depth + 1)
                )
            if y_sorted[i]["y1"] > max_y_end:
                max_y_end = y_sorted[i]["y1"]

        return sorted(lines, key=lambda l: (round(l["y0"], 1), round(l["x0"], 1)))

    @classmethod
    def _join_wrapped_lines(cls, lines_text: List[str]) -> str:
        """
        Intelligently joins wrapped lines into smooth prose, de-hyphenating broken
        end-of-line word wraps while preserving genuine compound hyphens (pre-existing).
        """
        if not lines_text:
            return ""
        out = lines_text[0].strip()
        for raw_next in lines_text[1:]:
            nxt = raw_next.strip()
            if not nxt:
                continue
            if not out:
                out = nxt
                continue
            if out.endswith("-") and len(out) >= 2 and out[-2].isalpha() and nxt[0].isalpha():
                # Check last word before hyphen
                m = re.search(r"([A-Za-z]+)-$", out)
                prefix = m.group(1).lower() if m else ""
                if prefix in cls.COMPOUND_HYPHEN_PREFIXES or not nxt[0].islower():
                    out = out + nxt
                else:
                    # De-hyphenate broken line-wrap word (e.g. "hospita-" + "lization")
                    out = out[:-1] + nxt
            else:
                out = out + " " + nxt
        return re.sub(r"\s+", " ", out).strip()

    @classmethod
    def _is_section_heading(cls, line_obj: Dict[str, Any], body_font_size: float) -> bool:
        txt = line_obj["text"].strip()
        if not txt or len(txt) > 95 or len(txt.split()) > 13:
            return False
        # Reject prose lead-in lines ending with semicolon/comma or sentence verbs
        if txt.endswith((";", ",")) or re.search(r"\b(?:is|are|shall\s+be|will\s+be|has\s+been)\s+(?:available|applicable|payable|covered|excluded)\b", txt, re.IGNORECASE):
            return False
        # Do not mistake clause body sentences ending in period for headings (except "Section 1." style)
        if txt.endswith(".") and not re.match(r"^(?:Section|Part|Chapter|Article|Annexure)\b", txt, re.IGNORECASE):
            return False
        # Do not treat pure numeric/bullet tokens as headings
        if re.fullmatch(r"[\d.\-•*]+", txt):
            return False

        for pat in cls.SECTION_PATTERNS:
            if pat.match(txt):
                return True

        # Font-guided heading detection (larger font or bold short standalone label without clause 'means')
        sz = line_obj.get("size", body_font_size)
        is_bold = line_obj.get("bold", False)
        if sz >= body_font_size + 0.85 and len(txt) >= 3:
            if not re.search(r"\b(?:means|shall\s+mean)\b", txt, re.IGNORECASE):
                return True
        if is_bold and len(txt.split()) <= 8 and not txt[0].islower():
            if not re.search(r"\b(?:means|shall\s+mean)\b", txt, re.IGNORECASE) and not re.match(r"^[a-z]\)|^\([a-z0-9]+\)", txt):
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
        temp = re.sub(r"\b(Rs|Re|INR)\.\s*", r"\1" + DOT_TOKEN + " ", text, flags=re.IGNORECASE)

        # 2. Protect decimal numbers like 1.5, 50,000.00, 24.5
        temp = re.sub(r"(\d+)\.(\d+)", r"\1" + DOT_TOKEN + r"\2", temp)

        # 3. Protect clause numbering like 1.1, 4.2.1, 5.a
        temp = re.sub(r"\b([A-Za-z0-9]+)\.([A-Za-z0-9]+)\b", r"\1" + DOT_TOKEN + r"\2", temp)

        # 4. Protect common abbreviations (e.g., i.e., Dr., No., Ltd., etc.)
        def _replace_abbr_dot(match):
            return match.group(0).replace(".", DOT_TOKEN)

        temp = cls.ABBREV_PATTERN.sub(_replace_abbr_dot, temp)

        # 5. Protect single letter with dot (e.g. A., B. in lists)
        temp = re.sub(r"\b([A-Za-z])\.\s+", r"\1" + DOT_TOKEN + " ", temp)

        # 6. Split on sentence boundaries
        raw_parts = re.split(r"(?<=[.?!])\s+(?=[A-Z0-9\"'\(\[\u201c\u2018—•\-])|(?<=[.?!])\s+", temp)

        # 7. Restore protected periods
        sentences = []
        for part in raw_parts:
            cleaned = part.replace(DOT_TOKEN, ".").strip()
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
        chunk_type: str = "clause",
        max_words: int = 240,
        overlap_sentences: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Splits a clause exceeding max_words into coherent sentence-bounded chunks
        with sentence overlap so rules or conditions are never severed.
        """
        clean_text = re.sub(r"\s+", " ", clause_text).strip()
        words = clean_text.split()
        if len(words) <= max_words:
            return [{
                "page": page_num,
                "section": section,
                "clause_number": clause_num,
                "text": clean_text,
                "chunk_type": chunk_type,
            }]

        sentences = cls._split_into_sentences(clean_text)
        if len(sentences) <= 1:
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
                    "text": sub_text,
                    "chunk_type": chunk_type,
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
                    "text": sub_text,
                    "chunk_type": chunk_type,
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
                "text": sub_text,
                "chunk_type": chunk_type,
            })

        return chunks

    @classmethod
    def _batch_table_statements(
        cls,
        statements: List[str],
        page_num: int,
        section: str,
        chunk_type: str,
        max_words: int = 210,
    ) -> List[Dict[str, Any]]:
        """
        Groups related table key-value statements into coherent 80-210 word chunks
        so each chunk keeps dense policy facts without fragmenting into tiny rows.
        """
        chunks: List[Dict[str, Any]] = []
        buf: List[str] = []
        wc = 0
        part = 1

        for st in statements:
            st_wc = len(st.split())
            if wc + st_wc > max_words and buf:
                chunks.append({
                    "page": page_num,
                    "section": section,
                    "clause_number": f"Table Item {part}" if len(statements) > 1 else None,
                    "text": " ".join(buf),
                    "chunk_type": chunk_type,
                })
                buf = []
                wc = 0
                part += 1
            buf.append(st)
            wc += st_wc

        if buf:
            chunks.append({
                "page": page_num,
                "section": section,
                "clause_number": f"Table Item {part}" if part > 1 else None,
                "text": " ".join(buf),
                "chunk_type": chunk_type,
            })
        return chunks

    @classmethod
    def _page_may_have_table(cls, fpage: pymupdf.Page) -> bool:
        """
        Ultra-fast (~1ms/page) PyMuPDF vector geometry pre-filter to avoid calling
        pdfminer/pdfplumber on plain text/prose pages that only have header/footer lines.
        """
        h, w = fpage.rect.height, fpage.rect.width
        try:
            drawings = fpage.get_drawings()
        except Exception:
            return True
        if not drawings:
            return False

        body_h_segs = 0
        body_v_segs = 0
        body_boxes = 0

        for d in drawings:
            rect = d.get("rect")
            if rect is None:
                continue
            rw = rect.x1 - rect.x0
            rh = rect.y1 - rect.y0
            # Skip full-page frames or top/bottom page header/footer rules
            if rw > 0.92 * w and rh > 0.85 * h:
                continue
            if rect.y1 < 0.08 * h or rect.y0 > 0.90 * h:
                continue

            # Large rectangular boxes/cards inside body (e.g. brochure cards or cell grids)
            if rw >= 50 and rh >= 12 and rh < 0.78 * h:
                body_boxes += 1
            for item in d.get("items", []):
                if item[0] == "l":
                    p1, p2 = item[1], item[2]
                    if abs(p1.y - p2.y) <= 1.5 and abs(p1.x - p2.x) >= 25 and 0.08 * h <= p1.y <= 0.90 * h:
                        body_h_segs += 1
                    elif abs(p1.x - p2.x) <= 1.5 and abs(p1.y - p2.y) >= 16 and 0.06 * w <= p1.x <= 0.94 * w:
                        body_v_segs += 1
                elif item[0] == "re":
                    r = item[1]
                    if (r.x1 - r.x0) >= 40 and 10 <= (r.y1 - r.y0) <= 0.78 * h and 0.08 * h <= r.y0 <= 0.90 * h:
                        body_boxes += 1

        return (body_h_segs >= 2 and body_v_segs >= 1) or body_boxes >= 2

    @classmethod
    def inspect_and_extract(cls, file_path: Path) -> Dict[str, Any]:
        """
        Extracts normalized layout-sorted pages, structured tables, section hierarchy,
        and coherent semantic clauses from any insurance policy PDF.
        """
        if not file_path.exists():
            raise PDFProcessingError(f"File not found: {file_path}")

        doc = None
        pl_pdf = None
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

            repeated_headers, body_font_size, doc_metadata, cached_dicts = cls._detect_document_profile(doc)

            # Pure PyMuPDF extraction (zero slow pdfplumber/pdfminer overhead)
            pages_data: List[Dict[str, Any]] = []
            total_words = 0
            total_chars = 0

            current_section = "General Policy Overview"
            all_sections: List[Dict[str, Any]] = []
            all_clauses: List[Dict[str, Any]] = []
            in_toc_block = False

            for page_idx in range(total_pages):
                page_num = page_idx + 1
                fpage = doc[page_idx]
                page_h = fpage.rect.height
                page_w = fpage.rect.width
                text_dict = cached_dicts[page_idx]
                page_lines = cls._extract_dict_lines(text_dict)

                # 1. Extract structured multi-column tables cleanly using PyMuPDF vector geometry + cached lines
                extracted_tables, table_bboxes = cls._extract_tables_from_page(
                    fpage, page_lines, page_num, repeated_headers
                )

                # 2. Extract remaining body text lines outside table bboxes
                raw_lines: List[Dict[str, Any]] = []
                for b in text_dict.get("blocks", []):
                    if b.get("type") != 0:
                        continue
                    for ln in b.get("lines", []):
                        # Skip diagonal/rotated watermarks
                        if ln.get("dir", (1, 0)) != (1, 0):
                            continue
                        lx0, ly0, lx1, ly1 = ln["bbox"]
                        cx, cy = (lx0 + lx1) / 2.0, (ly0 + ly1) / 2.0
                        if any(bx0 <= cx <= bx1 and by0 <= cy <= by1 for bx0, by0, bx1, by1 in table_bboxes):
                            continue

                        txt = cls.normalize_text("".join(s.get("text", "") for s in ln.get("spans", [])))
                        if not txt:
                            continue

                        # Skip repeated margin headers / footers & page numbers
                        if (ly0 < page_h * 0.13 or ly1 > page_h * 0.87) and cls._normalize_margin_key(txt) in repeated_headers:
                            continue
                        if (ly0 < page_h * 0.08 or ly1 > page_h * 0.89) and re.fullmatch(r"\d{1,4}", txt):
                            continue
                        if cls._is_header_footer(txt):
                            continue

                        sizes = [float(s.get("size", 10.0)) for s in ln.get("spans", []) if s.get("text", "").strip()]
                        flags = [int(s.get("flags", 0)) for s in ln.get("spans", []) if s.get("text", "").strip()]
                        raw_lines.append({
                            "x0": lx0,
                            "y0": ly0,
                            "x1": lx1,
                            "y1": ly1,
                            "text": txt,
                            "size": max(sizes) if sizes else body_font_size,
                            "bold": any(f & 16 for f in flags),
                        })

                # 3. Sort body lines cleanly in multi-column XY-cut reading order
                sorted_lines = cls._xy_cut_sort_lines(raw_lines, page_w, page_h)

                # 4. Interleave tables into page flow at their geometric Y-position for clean Page Preview
                preview_items: List[Tuple[float, str]] = []
                body_idx = 0
                sorted_tables = sorted(extracted_tables, key=lambda t: t["y0"])

                # Construct page preview text with tables in vertical flow (approximate placement on 2-col vs 1-col)
                page_preview_parts: List[str] = []
                # Simple top-to-bottom preview merge when single column; otherwise show ordered body + formatted tables
                body_preview_lines = []
                prev_y = None
                for ln in sorted_lines:
                    # Insert blank line on column switch or large paragraph break
                    if prev_y is not None and (ln["y0"] - prev_y > 14.0 or ln["y0"] < prev_y - 30.0):
                        body_preview_lines.append("")
                    body_preview_lines.append(ln["text"])
                    prev_y = ln["y1"]

                if body_preview_lines:
                    page_preview_parts.append("\n".join(body_preview_lines).strip())

                for tbl in sorted_tables:
                    md_tbl, _ = cls._format_table_markdown_and_statements(tbl, current_section)
                    if md_tbl.strip():
                        page_preview_parts.append(md_tbl)

                clean_page_text = "\n\n".join(p for p in page_preview_parts if p).strip()
                word_count = len(clean_page_text.split())
                char_count = len(clean_page_text)
                total_words += word_count
                total_chars += char_count

                pages_data.append({
                    "page": page_num,
                    "word_count": word_count,
                    "text": clean_page_text,
                })

                # 5. Semantic Section & Clause Segmentation from sorted lines + structured tables
                buffer_lines: List[str] = []
                active_clause_num: Optional[str] = None
                prev_ln_y0: Optional[float] = None
                prev_ln_x0: Optional[float] = None
                pending_orphan_bullet = False

                def _flush_buffer():
                    nonlocal buffer_lines, active_clause_num
                    if not buffer_lines or in_toc_block:
                        buffer_lines = []
                        active_clause_num = None
                        return
                    joined = cls._join_wrapped_lines(buffer_lines)
                    buffer_lines = []
                    # Skip TOC lines like "5 I Accidental Death 6" or lone page artifacts
                    if re.fullmatch(r"[\d.\s]+", joined):
                        active_clause_num = None
                        return
                    if len(joined) >= 24:
                        chunk_type = "definition" if (
                            "definition" in current_section.lower()
                            or re.match(r"^(?:Def\.?\s*\d+|\d+\.\d+(?:\([a-z0-9]+\))?\.?\s+[A-Z][\w\s/\-()]{1,45}\s+(?:means|shall\s+mean|refers\s+to)\b)", joined)
                        ) else "clause"
                        sub_chunks = cls._split_oversized_clause(
                            joined,
                            page_num=page_num,
                            section=current_section,
                            clause_num=active_clause_num,
                            chunk_type=chunk_type,
                        )
                        all_clauses.extend(sub_chunks)
                    active_clause_num = None

                for ln in sorted_lines:
                    txt = ln["text"]

                    # Skip orphan bullet marker alone on a line (attach directly to next line)
                    if txt in ("•", "-", "*", "—", "▪", "●", "o"):
                        pending_orphan_bullet = True
                        continue
                    if pending_orphan_bullet:
                        txt = f"• {txt}"
                        pending_orphan_bullet = False

                    # Detect TOC blocks cleanly so they don't pollute Exclusions/Coverage
                    if re.match(r"^TABLE\s+OF\s+CONTENTS\b", txt, re.IGNORECASE):
                        _flush_buffer()
                        in_toc_block = True
                        current_section = "Table of Contents"
                        continue

                    # Check Section Heading
                    if cls._is_section_heading(ln, body_font_size):
                        # Ignore tiny bullet label like "Note:"? Keep "Note:" attached to following text unless section
                        if txt.lower().rstrip(":") in ("note", "example", "illustration"):
                            _flush_buffer()
                            buffer_lines.append(txt)
                            prev_ln_y0 = ln["y0"]
                            prev_ln_x0 = ln["x0"]
                            continue

                        _flush_buffer()
                        in_toc_block = False
                        current_section = txt.rstrip(":").strip()
                        all_sections.append({
                            "title": current_section,
                            "page": page_num,
                            "level": 1,
                        })
                        prev_ln_y0 = ln["y0"]
                        prev_ln_x0 = ln["x0"]
                        continue

                    if in_toc_block:
                        # Exit TOC mode as soon as substantive multi-sentence prose or Section 1 starts
                        if len(txt) > 85 or re.match(r"^(?:1\.\s+Preamble|Section\s+1)\b", txt, re.IGNORECASE):
                            in_toc_block = False
                        else:
                            continue

                    # Check column reset (big jump upward in y0 means moved to next column -> flush incomplete bullet/heading if long)
                    if prev_ln_y0 is not None and ln["y0"] < prev_ln_y0 - 40.0 and len(" ".join(buffer_lines).split()) >= 60:
                        _flush_buffer()

                    # Check Numbered Clause Start (e.g., 2.1(a), Def 1., 4.2, a))
                    clause_match = cls.CLAUSE_NUMBER_PATTERN.match(txt)
                    is_sub_roman_or_letter = bool(re.match(r"^(?:[ivxlcdm]+\.|[a-z]\)|\([a-z0-9]+\))\s+", txt, re.IGNORECASE))

                    if clause_match and not is_sub_roman_or_letter:
                        # New top-level or sub-numbered clause (e.g. 2.1(a), 5.2, Def 3)
                        if buffer_lines:
                            _flush_buffer()
                        active_clause_num = clause_match.group(1)
                        buffer_lines.append(txt)
                    elif is_sub_roman_or_letter or txt.startswith(("•", "-", "*", "—", "▪", "●")):
                        # Start new chunk for a list item only if buffer is already substantial (>= 55 words),
                        # keeping short lead-in sentences together with their bullet list!
                        cur_wc = len(" ".join(buffer_lines).split())
                        if buffer_lines and cur_wc >= 90:
                            _flush_buffer()
                        buffer_lines.append(txt)
                    elif prev_ln_y0 is not None and (ln["y0"] - prev_ln_y0 > 24.0) and len(" ".join(buffer_lines).split()) >= 65:
                        # Visual paragraph break
                        _flush_buffer()
                        buffer_lines.append(txt)
                    else:
                        buffer_lines.append(txt)

                    prev_ln_y0 = ln["y0"]
                    prev_ln_x0 = ln["x0"]

                _flush_buffer()

                # 6. Process tables on this page into structured semantic clauses
                for tbl in sorted_tables:
                    role = tbl["role"]
                    if role == "toc":
                        continue
                    tbl_sec = tbl.get("title") or current_section
                    if role == "ombudsman":
                        tbl_sec = "Insurance Ombudsman & Grievance Redressal Directory"
                    elif role == "non_medical_list":
                        tbl_sec = "List of Non-Medical / Non-Payable Items"
                    _, statements = cls._format_table_markdown_and_statements(tbl, tbl_sec)
                    if statements:
                        tbl_chunks = cls._batch_table_statements(
                            statements,
                            page_num=page_num,
                            section=tbl_sec,
                            chunk_type=role,
                        )
                        all_clauses.extend(tbl_chunks)

        finally:
            if doc is not None:
                try:
                    doc.close()
                except Exception as ce:
                    logger.warning(f"Error closing PyMuPDF document handle: {ce}")

        # Scanned PDF detection
        is_scanned = (total_words < 15 or total_chars < 80) and total_pages > 0

        # Fallback paragraph chunking if non-standard layout produced very few clauses
        if len(all_clauses) < 5 and not is_scanned:
            all_clauses = cls._fallback_paragraph_segmentation(pages_data)

        logger.info(
            f"PDF extraction complete: {total_pages} pages, {total_words} words, "
            f"{len(all_clauses)} bounded clauses, {len(all_sections)} sections."
        )

        return {
            "total_pages": total_pages,
            "total_words": total_words,
            "total_chars": total_chars,
            "is_scanned": is_scanned,
            "metadata": doc_metadata,
            "pages": pages_data,
            "sections": all_sections,
            "clauses": all_clauses,
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
