# PolicyLens — Intelligent System for Structured Analysis and Explainable Understanding of Health Insurance Policy Documents

> **Comprehensive Technical Architecture, Engineering Manual, and Academic Defense Guide**  
> **Project Repository:** Root Directory (`d:\PolicyLens`)  
> **Target Audience:** Evaluators, Academic Faculty, AI/ML Engineers, Software Architects, and Policyholders  
> **Version:** 2.0 (Production-Grade Hybrid RAG Architecture)

---

## Table of Contents

1. [Project Title](#1-project-title)
2. [Project Overview](#2-project-overview)
3. [Problem Statement](#3-problem-statement)
4. [Objectives](#4-objectives)
5. [Key Features](#5-key-features)
6. [Technology Stack](#6-technology-stack)
7. [Project Architecture](#7-project-architecture)
8. [Complete Working Process](#8-complete-working-process)
9. [PDF Processing Pipeline](#9-pdf-processing-pipeline)
10. [Text Preprocessing](#10-text-preprocessing)
11. [Chunking and Data Division](#11-chunking-and-data-division)
12. [Embeddings and Retrieval](#12-embeddings-and-retrieval)
13. [AI / LLM Integration](#13-ai--llm-integration)
14. [Dataset Used in PolicyLens](#14-dataset-used-in-policylens)
15. [Project Folder Structure](#15-project-folder-structure)
16. [Important Code Files](#16-important-code-files)
17. [Installation and Setup](#17-installation-and-setup)
18. [How to Run](#18-how-to-run)
19. [Example Workflow](#19-example-workflow)
20. [Limitations](#20-limitations)
21. [Future Scope](#21-future-scope)
22. [Faculty Presentation Script](#22-faculty-presentation-script)
23. [Faculty Viva Questions and Answers (28 Technical Questions)](#23-faculty-viva-questions-and-answers)

---

## 1. Project Title

**PolicyLens: An Intelligent System for Structured Analysis and Explainable Understanding of Health Insurance Policy Documents**

- **Domain:** Artificial Intelligence (AI), Natural Language Processing (NLP), Information Retrieval (IR), and Retrieval-Augmented Generation (RAG).
- **Application Focus:** Health Insurance Policy Documents, Customer Information Sheets (CIS), and Regulatory Policy Wordings.

---

## 2. Project Overview

### 2.1 What is PolicyLens? (Simple Explanation)
**PolicyLens** is an intelligent web application designed to help ordinary people understand complicated health insurance policies. When someone buys health insurance, the insurance company sends a 30 to 60-page PDF document filled with complex legal terms, fine print, hidden conditions, waiting periods, and exclusions. Most policyholders never read this document because it is too difficult and exhausting to understand.

PolicyLens solves this problem by allowing a user to:
1. **Upload** their health insurance policy PDF.
2. **Read** an automated, clear, 10-point summary of what is covered and what is not.
3. **Ask questions** in simple everyday language (English, Hindi, or Hinglish) such as *"Is cataract covered?"* or *"What is the waiting period for pre-existing diseases?"*.
4. **Receive clear answers** supported by exact **Page Numbers** and **Official Clause Quotes** directly from their own uploaded policy.

### 2.2 Technical Definition
Technically, PolicyLens is an end-to-end **Document-Grounded, Structure-Aware Hybrid Retrieval-Augmented Generation (RAG) System**. It combines:
- Fast, non-blocking asynchronous PDF processing (PyMuPDF).
- Rule-calibrated clause classification across 5 legal dimensions (*Coverage, Exclusion, Waiting Period, Condition, Claim Requirement*).
- Multimodal and multi-lingual dense vector representations (**BAAI/bge-m3** with 1024 dimensions).
- Sparse lexical search using **BM25Okapi** for exact insurance terms, sub-limits, and currency values.
- Question-aware intent classification and dynamic score weighting.
- Neural reranking using a cross-attention transformer (**cross-encoder/ms-marco-MiniLM-L-6-v2**).
- Completeness checking and strict grounding guardrails that eliminate hallucinations and honestly report unmentioned illnesses.

### 2.3 Who Can Use PolicyLens?
- **Policyholders & Families:** To verify whether an emergency or planned medical procedure will be covered before going to the hospital.
- **Insurance Agents & Financial Advisors:** To quickly compare policy wordings, exclusions, and waiting periods across multiple insurers.
- **Hospital TPA & Billing Desks:** To instantly check sub-limits (e.g., room rent capping, ambulance limits, modern treatment ceilings) without manual scanning.
- **Academic Researchers & Students:** As a reference implementation of advanced, production-grade RAG and domain-specific information retrieval.

---

## 3. Problem Statement

Health insurance policies are among the most legally dense and confusing consumer contracts in the world:

1. **Heavy Legal Jargon:** Terms such as *"Constructive Total Loss"*, *"Subrogation"*, *"Morbidity Charge"*, *"Domiciliary Hospitalization"*, and *"Proportionate Deduction"* confuse common policyholders.
2. **Hidden Exclusions and Waiting Periods:** A policy may proudly state on Page 3 that *"In-patient hospitalization is covered up to ₹5,00,000"*, but hide on Page 19 under Clause 4.3 that *"Pre-existing diseases have a mandatory waiting period of 36 continuous months"*.
3. **Failure of Traditional Search (`Ctrl+F`):** Standard keyword search requires the user to know the insurer's exact legal terms. If a user searches *"eye surgery"*, but the document terms it *"disorders of the eye requiring lens replacement"*, keyword search returns zero results.
4. **Failure of Naive AI Chatbots:** Standard ChatGPT-style LLMs suffer from **hallucinations** (guessing standard industry rules rather than checking the specific contract) and **cross-document leakage** (mixing terms between two different policies).
5. **Lack of Verifiable Citations:** A chatbot statement without an exact page and clause number cannot be used by a policyholder to defend a claim at a hospital desk.

---

## 4. Objectives

The primary engineering and research objectives of PolicyLens are:

1. **100% Document Isolation:** Every user query is strictly scoped to the active document ID. Data from Policy A never leaks into Policy B.
2. **Zero-Hallucination Grounding:** If a specific disease, surgery, or medical term is not mentioned in the uploaded PDF, the system must declare insufficient evidence rather than guessing.
3. **Verifiable Page and Clause Citations:** Every claim in the generated answer must be accompanied by the exact page number, section name, and excerpt from the uploaded PDF.
4. **Explainable AI (XAI):** Translate complex legal insurance clauses into clear, plain-language explanations structured into Direct Answers, Explanations, Conditions, and Evidence.
5. **Sub-Second Hybrid Retrieval:** Combine semantic dense search (BGE-M3) and lexical sparse search (BM25) with dynamic weighting to retrieve both conceptual meanings and exact monetary figures.
6. **Robust Multi-Language Support:** Process queries in English, Hindi (Devanagari), and Hinglish (Roman Hindi) against English policy documents.

---

## 5. Key Features

- **Asynchronous Non-Blocking PDF Ingestion:** Upload returns an immediate HTTP 202 Accepted response; heavy AI indexing runs in a background worker thread while the UI polls real-time stage progress (0% to 100%).
- **Digital Native Stream Text Extraction:** Extracts complete text streams from 40-page policies in under 0.2 seconds using PyMuPDF, preserving 1-indexed page numbers.
- **Scanned Document & OCR Detection:** Automatically inspects character-to-word ratios; flags raster/image-only PDFs as `scanned_ocr_required`.
- **Structure-Aware Bounded Chunking:** Splits policies into natural legal clauses (80 to 240 words) preserving section headings and clause numbers, avoiding arbitrary character truncation.
- **5-Dimensional Clause Classification:** Tags extracted clauses into *Coverage*, *Exclusion*, *Waiting Period*, *Condition*, or *Claim Requirement* with confidence scores.
- **Multilingual Dense Vectorization:** Generates 1024-dimensional embeddings via `BAAI/bge-m3` bounded to 512 tokens to prevent CPU memory blowup.
- **Sparse BM25 Indexing:** Builds document-specific inverted indices (`BM25Okapi`) for exact monetary limits, clause IDs, and percentages.
- **Dynamic Intent-Weighted Retrieval:** Automatically detects question intent (*Waiting Period*, *Exclusion*, *Financial Limit*, *Claim Procedure*) and tunes hybrid weights ($\alpha, \beta, \gamma$) dynamically.
- **Two-Stage Cross-Encoder Reranking:** Neural cross-attention reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`) re-scores top candidates with lexical fallback.
- **Completeness Checker:** Detects unmentioned entities to block hallucinations and performs secondary targeted retrieval when essential facets (e.g., waiting periods) are missing.
- **Automated 10-Dimensional Policy Summary:** Automatically synthesizes a 10-dimension overview (Eligibility, Room Rent, Pre-Existing Conditions, Exclusions, Claim Intimation, etc.) upon upload.
- **Full-Screen Modern Chat Interface:** Fully responsive conversational UI with streaming status indicators, badge rendering, and collapsible citation cards.

---

## 6. Technology Stack

Every technology listed below is verified in the actual project source code and configuration files:

### 6.1 Frontend Technologies
| Technology | Version | Purpose in PolicyLens | Implementation Location |
| :--- | :--- | :--- | :--- |
| **React** | `19.0.0` | Declarative component UI library for building single-page interfaces | `frontend/src/` |
| **Vite** | `8.3.4` | Modern, high-speed frontend bundler and development server | `frontend/vite.config.js` |
| **Tailwind CSS** | `4.0.0` | Utility-first CSS framework for responsive full-screen styling | `frontend/src/index.css` |
| **Axios** | `1.7.9` | Promise-based HTTP client for calling backend REST endpoints | `frontend/src/services/api.js` |
| **Lucide React** | `0.475.0` | Clean, modern iconography (Shield, FileText, UploadCloud, MessageSquare) | `frontend/src/pages/` |
| **Framer Motion** | `12.4.7` | Smooth UI transitions, stage progress animations, and modal overlays | `frontend/src/components/` |

### 6.2 Backend Technologies
| Technology | Version | Purpose in PolicyLens | Implementation Location |
| :--- | :--- | :--- | :--- |
| **Python** | `3.11+ / 3.13` | Primary backend programming language | `BACKEND/` |
| **FastAPI** | `0.116.1` | High-performance asynchronous REST API framework (ASGI) | `BACKEND/app/main.py` |
| **Uvicorn** | `0.35.0` | Production ASGI web server running FastAPI | `BACKEND/requirements.txt` |
| **SQLAlchemy** | `2.0.43` | Relational Object-Relational Mapper (ORM) managing database entities | `BACKEND/app/db/database.py` |
| **Pydantic** | `2.11.7` | Strict data validation and schema serialization for requests and responses | `BACKEND/app/models/schemas.py` |
| **Passlib & Bcrypt** | `1.7.4 / 4.0+` | Cryptographic password hashing for user accounts | `BACKEND/app/core/security.py` |
| **Python-JOSE** | `3.3.0` | JSON Web Token (JWT) encoding, decoding, and bearer verification | `BACKEND/app/core/security.py` |

### 6.3 AI, NLP, and Information Retrieval Libraries
| Library / Model | Version / Model ID | Purpose in PolicyLens | Implementation Location |
| :--- | :--- | :--- | :--- |
| **PyMuPDF (`fitz`)** | `2.0` (`1.24+`) | High-speed native digital PDF text stream parser | `BACKEND/app/services/pdf_processor.py` |
| **BGE-M3** | `BAAI/bge-m3` | 1024-dim dense multilingual transformer embedding model | `BACKEND/app/services/embeddings.py` |
| **MiniLM (Fallback)** | `sentence-transformers/all-MiniLM-L6-v2` | Lightweight 384-dim embedding model for low-resource environments | `BACKEND/app/services/embeddings.py` |
| **Sentence-Transformers** | `6.2.0` | Framework for loading and running dense embedding models | `BACKEND/app/services/embeddings.py` |
| **Rank-BM25** | `0.2.2` | Pure-Python BM25Okapi sparse lexical keyword search algorithm | `BACKEND/app/services/bm25_retriever.py` |
| **Cross-Encoder** | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Neural cross-attention reranker for query-clause candidate pairs | `BACKEND/app/services/reranker.py` |
| **Google Generative AI** | `google-generativeai 0.8.5` | SDK for Gemini 1.5 Flash LLM grounded answer generation | `BACKEND/app/services/llm_service.py` |
| **HTTPX** | `0.28.1` | Asynchronous HTTP client for external OpenAI and Ollama calls | `BACKEND/app/services/llm_service.py` |
| **Scikit-Learn** | `1.6.1` | Cosine similarity calculations and dense array normalization | `BACKEND/app/services/embeddings.py` |
| **NumPy** | `2.2.2` | Numerical matrix and vector array manipulations | `BACKEND/app/services/embeddings.py` |

### 6.4 Database and File Storage
- **Primary Database:** SQLite 3 configured with **Write-Ahead Logging (WAL)** mode (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=15000;`).
- **File Storage:** Local disk storage organized into:
  - `BACKEND/data/uploads/`: Original uploaded PDF files.
  - `BACKEND/data/processed/{doc_id}/`: Pickled BM25 indices (`bm25_index.pkl`), FAISS vector caches (`vector_index.faiss`), and serialized clauses (`clauses.json`).

---

## 7. Project Architecture

The following diagram illustrates the complete, implemented architectural relationship between user interactions, the frontend application, the backend API, the background ingestion worker, the retrieval pipeline, storage engines, and the LLM service.

```mermaid
flowchart TD
    subgraph Client["Client Tier (React 19 + Vite + Tailwind CSS)"]
        UI_Upload["Upload Page<br/>(Drag-and-Drop Dropzone)"]
        UI_Progress["Status Poller<br/>(1.5s Interval Progress Bar)"]
        UI_Chat["Full-Screen Chat & Ask<br/>(4-Part Cards + Citations)"]
        UI_Library["Document Library<br/>(List, 10-Dim View, Delete)"]
    end

    subgraph API["FastAPI Application Tier (BACKEND/app/api/)"]
        Auth_API["auth.py<br/>(Login, JWT Token, Profile)"]
        Doc_API["documents.py<br/>(Upload 202, Status, Explanation)"]
        Chat_API["chat.py<br/>(Ask Question, Conversation Thread)"]
    end

    subgraph Worker["Background Ingestion Worker (document_worker.py)"]
        P1["1. PyMuPDF Native Extraction<br/>(Preserves Page & Sections)"]
        P2["2. Bounded Clause Chunking<br/>(80-240 Words Sentence Bounding)"]
        P3["3. Clause Classification<br/>(Coverage/Exclusion/Wait/Condition/Claim)"]
        P4["4. BGE-M3 Dense Embedding<br/>(16-Clause Batches, 1024-Dim)"]
        P5["5. BM25 & FAISS Serialization<br/>(Inverted Index & Vector Cache)"]
        P6["6. 10-Dim Structured Explanation<br/>(Cached in DB)"]
    end

    subgraph Storage["Storage & Persistence Tier"]
        SQLite_DB[("SQLite 3 (WAL Mode)<br/>policylens.db")]
        Disk_Uploads["data/uploads/*.pdf"]
        Disk_Processed["data/processed/{doc_id}/<br/>bm25_index.pkl & vector_index.faiss"]
    end

    subgraph RAG["Advanced RAG Engine (rag_engine.py)"]
        Q_Analyzer["QuestionAnalyzer<br/>(Intent, Language: EN/HI/Hinglish, Category Boost)"]
        Hybrid_Retriever["HybridRetriever<br/>(α·Dense + β·BM25 + γ·Category)"]
        Cross_Encoder["CrossEncoderReranker<br/>(ms-marco-MiniLM Cross-Attention)"]
        Completeness["CompletenessChecker<br/>(Missing Category Expansion & Insufficiency Check)"]
        LLM_Engine["LLMService<br/>(Gemini 1.5 Flash / OpenAI / Ollama / Mock)"]
        Ans_Validator["AnswerValidator<br/>(Numerical & Entity Grounding Audit)"]
    end

    UI_Upload -->|1. POST /api/documents/upload| Doc_API
    Doc_API -->|Save PDF| Disk_Uploads
    Doc_API -->|HTTP 202 Accepted + doc_id| UI_Upload
    Doc_API -->|Spawn Worker Thread| Worker

    Worker --> P1 --> P2 --> P3 --> P4 --> P5 --> P6
    P4 -.->|Update Progress 55%-85%| SQLite_DB
    P5 --> Disk_Processed
    P6 --> SQLite_DB
    P6 -.->|Set status = 'completed'| SQLite_DB

    UI_Progress -->|2. GET /api/documents/{id}/status| Doc_API
    Doc_API -->|Read Progress| SQLite_DB

    UI_Chat -->|3. POST /api/chat/ask| Chat_API
    Chat_API --> Q_Analyzer
    Q_Analyzer --> Hybrid_Retriever
    SQLite_DB -->|Fetch Clause Records| Hybrid_Retriever
    Disk_Processed -->|BM25 Scores| Hybrid_Retriever
    Hybrid_Retriever --> Cross_Encoder
    Cross_Encoder --> Completeness
    Completeness --> LLM_Engine
    LLM_Engine --> Ans_Validator
    Ans_Validator -->|Save Messages| SQLite_DB
    Ans_Validator -->|Return 4-Part Response + Citations| Chat_API
    Chat_API --> UI_Chat
```

---

## 8. Complete Working Process

The entire lifecycle of PolicyLens is divided into two distinct operational phases:
1. **The Document Ingestion Phase:** Triggered once when a PDF is uploaded.
2. **The Question Answering (RAG) Phase:** Triggered every time a user asks a question.

```
PHASE 1: INGESTION
[User Uploads PDF] ──► [HTTP 202 Accepted] ──► [Background Worker]
                                                      │
         ┌────────────────────────────────────────────┘
         ▼
[PyMuPDF Text Extract] ──► [Bounded Chunking] ──► [5-Dim Classification]
         │
         ▼
[BGE-M3 Dense Embedding (1024-dim)] ──► [BM25 Inverted Index] ──► [Status: Completed]

───────────────────────────────────────────────────────────────────────────────────

PHASE 2: QUESTION ANSWERING (RAG)
[User Asks Question] ──► [Language & Intent Detection (EN / HI / Hinglish)]
                                  │
                                  ▼
[Dynamic Hybrid Retrieval (Dense BGE-M3 + Sparse BM25 + Category Boost)]
                                  │
                                  ▼
[Cross-Encoder Neural Reranking] ──► [Completeness Checker Audit]
                                  │
                                  ▼
[Strict Grounded Prompt Assembly] ──► [LLM Generation (Gemini 1.5 Flash)]
                                  │
                                  ▼
[Post-Generation Numerical Validation] ──► [4-Part Structured Answer + Citations]
```

---

## 9. PDF Processing Pipeline

Tracing the implementation in [`BACKEND/app/services/pdf_processor.py`](file:///d:/PolicyLens/BACKEND/app/services/pdf_processor.py) step by step:

### Step 1: PDF Upload & Transport
- **Frontend Component:** [`UploadPage.jsx`](file:///d:/PolicyLens/frontend/src/pages/UploadPage.jsx) provides a drag-and-drop zone. It validates that `file.name.endsWith('.pdf')` and `file.size <= 30 * 1024 * 1024` bytes.
- **API Function:** `uploadDocument(formData)` in [`frontend/src/services/api.js`](file:///d:/PolicyLens/frontend/src/services/api.js).
- **Backend Endpoint:** `POST /api/documents/upload` in [`BACKEND/app/api/documents.py`](file:///d:/PolicyLens/BACKEND/app/api/documents.py).
- **Transport Mechanism:** Sent as an HTTP `multipart/form-data` request. The backend streams the bytes directly to `BACKEND/data/uploads/<timestamp>_<filename>.pdf`.
- **Non-Blocking Handshake:** The backend immediately saves a record in the `documents` table with `status="processing"`, returns an **HTTP 202 Accepted** response with the document UUID, and launches the worker thread.

### Step 2: PDF Text Extraction
- **Library Used:** PyMuPDF (`fitz` / `pymupdf 2.0`).
- **Extraction Function:** `PDFProcessor.inspect_and_extract(file_path)` in `pdf_processor.py`.
- **How Text is Extracted:** The file is opened via `pymupdf.open(str(file_path))`. The code iterates through each page (`doc[page_idx]`) and calls `page.get_text("text")`.
- **Preservation of Page Numbers:** The page loop is 0-indexed, so `page_num = page_idx + 1` is explicitly preserved and attached to every line and clause extracted from that page.
- **Handling Corrupted & Encrypted Files:** The method explicitly checks `doc.is_encrypted` and raises a `PDFProcessingError("Password-protected or encrypted PDF documents are not supported.")`.
- **Resource Management:** Extraction is wrapped in a `try...finally` block that explicitly calls `doc.close()` to prevent file locks on Windows operating systems.
- **Handling Images & Scanned PDFs:** The system calculates:
  $$\text{is\_scanned} = (\text{total\_words} < 15 \lor \text{total\_chars} < 80) \land \text{total\_pages} > 0$$
  If true, the document is flagged as `scanned_ocr_required`. (OCR via Tesseract/PaddleOCR is noted as a planned enhancement).

---

## 10. Text Preprocessing

Raw PDF text streams contain formatting artifacts, broken line breaks, and irregular whitespace that can damage embedding models. Preprocessing in `pdf_processor.py` applies the following operations:

### 10.1 Cleaning and Normalization (`_clean_text`)
1. **Control Characters Removal:** Strips non-printable ASCII and control characters:
   ```python
   text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
   ```
2. **Whitespace Normalization:** Converts form-feeds, vertical tabs, and carriage returns into single spaces:
   ```python
   text = re.sub(r'[\r\t\f\v]+', ' ', text)
   text = re.sub(r' {2,}', ' ', text)
   ```
3. **Typography Standardization:** Standardizes curved quotes and apostrophes (`“`, `”`, `‘`, `’`) to standard ASCII quotes (`"`, `'`).

### 10.2 Header and Footer Removal (`_is_header_footer`)
Before processing text, lines matching repetitive metadata patterns are filtered out using regular expressions:
```python
HEADER_FOOTER_PATTERNS = [
    re.compile(r'^\s*page\s+\d+\s*(?:of\s+\d+)?\s*$', re.IGNORECASE),
    re.compile(r'^\s*\d+\s*(?:of|/)\s*\d+\s*$', re.IGNORECASE),
    re.compile(r'^\s*(?:policy\s+wordings?|prospectus|customer\s+information\s+sheet)\s*$', re.IGNORECASE),
    re.compile(r'^\s*(?:cin|irdai?\s+reg(?:istration)?\s*(?:no\.?)?)\s*[:\-]?\s*[A-Z0-9\-/]+\s*$', re.IGNORECASE)
]
```

### 10.3 Abbreviation and Decimal Protection (`_split_into_sentences`)
Splitting sentences at simple periods (`.`) corrupts insurance clauses containing currency (e.g. `Rs. 5,000`), decimals (e.g. `1.5%`), and abbreviations. PolicyLens replaces these periods with a temporary token (`\u0000DOT\u0000`), performs the sentence split, and restores the periods:
- Protected abbreviations: `Rs.`, `Re.`, `INR.`, `No.`, `Dr.`, `Mr.`, `Ms.`, `Vol.`, `Sec.`, `e.g.`, `i.e.`, `Ltd.`, `Co.`, `Dept.`.
- Protected decimals: `re.sub(r'(\d+)\.(\d+)', r'\1' + DOT_TOKEN + r'\2', temp)`.
- Protected clause numbering: `re.sub(r'\b([A-Za-z0-9]+)\.([A-Za-z0-9]+)\b', r'\1' + DOT_TOKEN + r'\2', temp)`.

---

## 11. Chunking and Data Division

### 11.1 Why Chunking is Necessary
A full insurance policy typically spans 15,000 to 45,000 words. Passing an entire document into an LLM causes multiple problems:
1. **Context Window Exhaustion:** Even large-context LLMs suffer from "lost-in-the-middle" degradation on massive texts.
2. **Loss of Citation Precision:** The LLM cannot report the exact page or clause number if the entire document is passed as a single block.
3. **Embedding Dilution:** An embedding vector representing 30 pages becomes an uninformative average, making similarity matching impossible.

### 11.2 Bounded Clause Chunking Implementation
Instead of arbitrary character chunking (e.g., cutting every 500 characters regardless of word or sentence boundaries), PolicyLens implements **Structure-Aware Bounded Clause Segmentation**:

- **Target Chunk Size:** Bounded between **80 words and 240 words** (`max_words = 240` in `_split_oversized_clause`).
- **Section Boundary Detection:** Lines matching `SECTION`, `PART`, `CLAUSE`, `SCHEDULE`, or short all-caps titles trigger a new section header.
- **Clause Number Detection:** Lines starting with clause patterns (e.g., `4.1`, `Section 3(b)`, `Clause 12.A`) trigger a new clause boundary.
- **Sentence-Bounded Splitting:** If a clause exceeds 240 words, it is split on complete sentences.
- **Overlap Strategy:** When an oversized clause is split across sentences, an overlap of **1 sentence** (`overlap_sentences = 1`) is carried forward. In the rare case of a single sentence exceeding 240 words, it is split by words with an overlap of **30 words** (`overlap_words = 30`).
- **Metadata Association:** Every chunk is saved to the `document_clauses` table with its exact `page_number`, `section_name`, `clause_number`, and `category`.

### 11.3 Concrete Chunking Example
Consider an original clause on Page 12 of a health policy:
```
Section 4: Waiting Periods. 
Clause 4.1: Pre-Existing Diseases (PED).
A waiting period of thirty-six (36) consecutive months of continuous coverage shall apply to all pre-existing conditions, illnesses, or injuries diagnosed by a physician prior to policy inception. No claims shall be payable for hospitalizations directly arising from such conditions during this 36-month period.
```
- **Word count:** 53 words.
- **Result:** Preserved as 1 discrete chunk.
- **Metadata Attached:** `page_number = 12`, `section_name = "Section 4: Waiting Periods"`, `clause_number = "4.1"`, `category = "Waiting Period"`.

---

## 12. Embeddings and Retrieval

### 12.1 What are Embeddings?
Embeddings convert human text into high-dimensional numerical vectors where semantically similar concepts reside near one another in continuous vector space.

### 12.2 Implemented Models
- **Primary Embedding Model:** `BAAI/bge-m3` (1024-dimensional dense vectors, 560M parameters).
  - *Sequence Length Bound:* `model.max_seq_length = 512` (enforced in `embeddings.py` to prevent CPU self-attention stalls).
  - *Batch Processing:* Encoded in micro-batches of 16 clauses.
- **Fallback Embedding Model:** `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional dense vectors).

### 12.3 Vector Storage and Indexing
1. **Relational Database Storage:** Vectors are serialized as JSON float arrays in the `embedding_json` column of the `document_clauses` SQLite table.
2. **FAISS Binary Index:** Saved to `BACKEND/data/processed/{doc_id}/vector_index.faiss`.
3. **BM25 Inverted Index:** Serialized to `BACKEND/data/processed/{doc_id}/bm25_index.pkl` via `pickle`.

### 12.4 Dynamic Hybrid Scoring Formula
[`BACKEND/app/services/hybrid_retriever.py`](file:///d:/PolicyLens/BACKEND/app/services/hybrid_retriever.py) scores candidates using a balanced combination of dense semantic similarity, sparse lexical match, and category alignment:

$$\text{Final Hybrid Score} = \alpha \cdot S_{\text{dense}} + \beta \cdot S_{\text{bm25}} + \gamma \cdot S_{\text{category}}$$

Where:
- $S_{\text{dense}} = \max\left(0.0, \frac{\text{Cosine Similarity} + 1.0}{2.0}\right)$
- $S_{\text{bm25}} = \text{Normalized BM25Okapi Score} \in [0.0, 1.0]$
- $S_{\text{category}} = 1.0$ if the clause matches the intent category, else $0.0$.

#### Configurable Dynamic Weights:
- **Numerical / Limit / Claim Inquiries:** $\alpha = 0.40, \beta = 0.45, \gamma = 0.15$ (high lexical precision for numbers and forms).
- **Waiting Period / Exclusion Inquiries:** $\alpha = 0.35, \beta = 0.30, \gamma = 0.35$ (high category boost).
- **General Coverage Inquiries:** $\alpha = 0.55, \beta = 0.30, \gamma = 0.15$ (high dense semantic coverage).
- **Default Baseline:** $\alpha = 0.50, \beta = 0.35, \gamma = 0.15$.

### 12.5 Cross-Encoder Neural Reranking
Top-15 candidates from hybrid search are passed to [`BACKEND/app/services/reranker.py`](file:///d:/PolicyLens/BACKEND/app/services/reranker.py). The cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) performs cross-attention over `[Query, Clause]` pairs to output refined relevance scores, returning the top-8 most relevant clauses.

---

## 13. AI / LLM Integration

### 13.1 Multi-Provider LLM Architecture
[`BACKEND/app/services/llm_service.py`](file:///d:/PolicyLens/BACKEND/app/services/llm_service.py) supports four distinct LLM backends:
1. **Google Gemini (Default in Production):** Model `gemini-1.5-flash` / `gemini-pro` via `google-generativeai`.
2. **OpenAI:** Model `gpt-4o-mini` / `gpt-3.5-turbo` via async HTTPX calls.
3. **Ollama (Private Local LLM):** Model `llama3.2` / `mistral` via local endpoint `http://localhost:11434`.
4. **Deterministic Local Grounded Synthesizer (Zero-Dependency Offline Fallback):** Assembles a structured summary directly from the top retrieved clauses when no API key or network connection is available.

### 13.2 System Prompt and Grounding Instructions
The LLM is strictly constrained via its system prompt:
> *"You are PolicyLens, an expert AI health insurance policy analyst. The provided policy clauses are your SOLE source of truth. Answer ONLY using facts directly stated in the evidence. Do not extrapolate, assume, or bring in external medical knowledge. If a disease, surgery, or term is not mentioned, you must state that the policy does not contain information on this topic."*

### 13.3 Output Schema
The LLM must format its answer into four mandatory markdown sections:
1. `### Direct Answer`: Clear, binary (Covered / Not Covered) or direct numerical statement.
2. `### Simple Explanation`: Layman explanation of how the clause applies in practice.
3. `### Important Conditions`: Bullet points highlighting waiting periods, sub-limits, and exclusions.
4. `### Evidence from Your Policy`: Grounded summary citing exact page numbers and clause titles.

### 13.4 Post-Generation Answer Validation
[`BACKEND/app/services/answer_validator.py`](file:///d:/PolicyLens/BACKEND/app/services/answer_validator.py) audits the generated text. It extracts numerical values, months, currency figures, and percentages from the answer and verifies that every number exists in the retrieved evidence clauses, preventing numerical hallucinations (e.g. inventing a "24-month" waiting period when the text says "36 months").

---

## 14. Dataset Used in PolicyLens

### 14.1 Is a Separate Dataset Used?
**NO.** PolicyLens **does not use a static training dataset** (such as SQuAD, HotpotQA, or insurance CSV records).

### 14.2 What Serves as the Knowledge Source?
The knowledge source for PolicyLens is **the PDF document uploaded dynamically by the end user at runtime**. Every policy uploaded is unique to that user, and PolicyLens dynamically extracts, indexes, and queries that specific file.

### 14.3 Sample Test Policies in the Repository
For testing and demonstration, two sample policies are included under `BACKEND/sample_policies/`:
1. `CareShield_Health_Insurance_Policy.pdf` (5 Pages, 1,115 words, 44 clauses): Retail health policy used for unit tests.
2. `StarHealth_Optima_Policy.pdf` (3 Pages): Used for multi-tenant document isolation verification.

### 14.4 Evaluation Benchmark Dataset
In [`BACKEND/evaluation/eval_framework.py`](file:///d:/PolicyLens/BACKEND/evaluation/eval_framework.py), there is a curated set of 5 evaluation queries (`q1_maternity_coverage`, `q2_maternity_waiting_period`, `q3_maternity_exclusions`, `q4_claim_documents`, `q5_unmentioned_condition`) used purely for measuring automated benchmark metrics (Precision@K, Recall@K, Faithfulness), not for model training.

### 14.5 Summary Table on Data
| Aspect | Details |
| :--- | :--- |
| **Separate Training Dataset?** | **None.** No fine-tuning or training was conducted. |
| **Model Nature** | All models (BGE-M3, MiniLM, Cross-Encoder, Gemini) are **pre-trained models used for inference**. |
| **Dynamic Knowledge Source** | User-uploaded PDF files stored in `BACKEND/data/uploads/`. |
| **Sample Policies Included** | `CareShield_Health_Insurance_Policy.pdf` (5 pages) & `StarHealth_Optima_Policy.pdf` (3 pages). |

---

## 15. Project Folder Structure

```text
D:\PolicyLens\
├── BACKEND/                             # Python Backend & AI Services
│   ├── app/
│   │   ├── api/                         # FastAPI REST Endpoints
│   │   │   ├── auth.py                  # User registration, login, profile
│   │   │   ├── chat.py                  # Conversation threads & RAG question answering
│   │   │   ├── documents.py             # PDF upload (202 Accepted), status, delete
│   │   │   └── health.py                # Health check & system diagnostics
│   │   ├── core/                        # Configuration & Core Utilities
│   │   │   ├── config.py                # Pydantic BaseSettings & canonical absolute paths
│   │   │   ├── logging.py               # Structured application logger
│   │   │   └── security.py              # JWT token generation & bcrypt password hashing
│   │   ├── db/                          # Database Connection & Engine
│   │   │   └── database.py              # SQLAlchemy engine, WAL-mode pragma, migrations
│   │   ├── models/                      # Database & Pydantic Schemas
│   │   │   ├── db_models.py             # User, Document, DocumentClause, Conversation
│   │   │   └── schemas.py               # Pydantic validation schemas
│   │   ├── services/                    # Core AI, NLP & RAG Pipeline
│   │   │   ├── answer_validator.py      # Numerical consistency audit
│   │   │   ├── bm25_retriever.py        # BM25Okapi sparse keyword indexing
│   │   │   ├── classifier.py            # 5-dimensional rule-calibrated clause classifier
│   │   │   ├── completeness_checker.py  # Missing category expansion & refusal detection
│   │   │   ├── document_worker.py       # Asynchronous ingestion worker thread
│   │   │   ├── embeddings.py            # BGE-M3 singleton & batch vector encoder
│   │   │   ├── explanation_service.py   # 10-dimension structured policy explanation
│   │   │   ├── hybrid_retriever.py      # Dynamic hybrid retrieval engine
│   │   │   ├── llm_service.py           # Grounded multi-provider answer generator
│   │   │   ├── pdf_processor.py         # PyMuPDF text stream extraction & bounded chunking
│   │   │   ├── question_analyzer.py     # Intent classification & synonym expansion
│   │   │   ├── rag_engine.py            # End-to-end RAG orchestrator
│   │   │   └── reranker.py              # Cross-Encoder neural reranker
│   │   └── main.py                      # FastAPI application entrypoint
│   ├── data/                            # Persistent Runtime Data (Ignored by Git)
│   │   ├── uploads/                     # User uploaded PDF files
│   │   └── processed/                   # FAISS indices, BM25 pickles, clause caches
│   ├── evaluation/                      # Research Evaluation Framework
│   │   ├── eval_framework.py            # Metrics engine (Precision@K, Faithfulness, etc.)
│   │   └── run_evaluation.py            # Evaluation test runner
│   ├── sample_policies/                 # Sample PDFs for testing
│   │   ├── CareShield_Health_Insurance_Policy.pdf
│   │   └── StarHealth_Optima_Policy.pdf
│   ├── tests/                           # Automated Verification Tests
│   │   ├── test_api_endpoints.py
│   │   ├── test_document_isolation.py
│   │   ├── test_pdf_extraction.py
│   │   └── test_rag_pipeline.py
│   ├── requirements.txt                 # Backend Python dependencies
│   ├── Dockerfile                       # Backend containerization recipe
│   └── .env.example                     # Environment template
│
├── frontend/                            # React 19 + Vite Frontend Application
│   ├── src/
│   │   ├── components/                  # UI Components (Lamp, LoginForm, ProtectedRoute)
│   │   ├── context/                     # Global State (AuthContext, ToastContext)
│   │   ├── layouts/                     # Layout Wrappers (AppLayout with sidebar)
│   │   ├── pages/                       # Application Views
│   │   │   ├── Dashboard.jsx            # Stats, quick links, recent policy cards
│   │   │   ├── UploadPage.jsx           # Dropzone, real-time stage progress, explanation
│   │   │   ├── DocumentLibrary.jsx      # Policy management, preview modal, deletion
│   │   │   ├── ChatPage.jsx             # Full-screen conversational AI chat
│   │   │   ├── ConversationHistory.jsx  # Past conversation threads
│   │   │   └── LoginPage.jsx            # Authentication interface
│   │   └── services/                    # API Integration
│   │       ├── api.js                   # Axios HTTP client configuration
│   │       └── authService.js           # Session and token storage
│   ├── package.json                     # Frontend dependencies
│   ├── vite.config.js                   # Vite build configuration
│   ├── Dockerfile                       # Frontend containerization recipe
│   └── .env.example                     # Frontend environment template
│
├── .gitignore                           # Git ignore rules for secrets, DBs, and uploads
├── docker-compose.yml                   # Multi-container orchestration
└── README.md                            # Complete Project Master Documentation
```

---

## 16. Important Code Files

| File Path | Role | Key Functions / Classes | Collaborates With |
| :--- | :--- | :--- | :--- |
| `BACKEND/app/api/documents.py` | Handles PDF upload, status polling, and explanation retrieval | `upload_document()`, `get_document_status()`, `get_document_explanation()` | `document_worker.py`, `database.py` |
| `BACKEND/app/services/pdf_processor.py` | Extracts text streams, detects sections, and divides text into bounded clauses | `inspect_and_extract()`, `_split_into_sentences()`, `_split_oversized_clause()` | PyMuPDF (`fitz`), `document_worker.py` |
| `BACKEND/app/services/document_worker.py` | Background ingestion orchestrator running extraction, classification, embedding, and indexing | `process_document_background()`, `on_embed_batch_done()` | `pdf_processor.py`, `embeddings.py`, `bm25_retriever.py`, `database.py` |
| `BACKEND/app/services/classifier.py` | Rule-calibrated clause classifier tagging clauses into 5 categories | `ClauseClassifier.classify()` | `document_worker.py`, `hybrid_retriever.py` |
| `BACKEND/app/services/embeddings.py` | Singleton dense embedding manager generating 1024-dim BGE-M3 vectors | `EmbeddingService.encode_text()`, `encode_clauses_batched()`, `cosine_similarity()` | `sentence-transformers`, `hybrid_retriever.py` |
| `BACKEND/app/services/bm25_retriever.py` | Manages BM25Okapi inverted index serialization and sparse scoring | `BM25Index`, `get_bm25_index()` | `rank-bm25`, `hybrid_retriever.py` |
| `BACKEND/app/services/question_analyzer.py` | Classifies question intent, detects language (EN/HI/Hinglish), and generates domain synonym expansions | `QuestionAnalyzer.analyze()`, `detect_language()` | `hybrid_retriever.py`, `completeness_checker.py` |
| `BACKEND/app/services/hybrid_retriever.py` | Document-isolated dynamic hybrid retriever computing weighted scores | `HybridRetriever.retrieve()` | `embeddings.py`, `bm25_retriever.py`, `rag_engine.py` |
| `BACKEND/app/services/reranker.py` | Cross-encoder neural reranker re-scoring candidate query-clause pairs | `CrossEncoderReranker.rerank()` | `sentence-transformers`, `rag_engine.py` |
| `BACKEND/app/services/completeness_checker.py` | Audits retrieved clauses for required categories and flags unmentioned illnesses | `CompletenessChecker.verify_and_expand()` | `database.py`, `rag_engine.py` |
| `BACKEND/app/services/llm_service.py` | Multi-provider grounded synthesizer generating structured 4-part answers | `LLMService.generate_grounded_answer()` | `google-generativeai`, `httpx`, `rag_engine.py` |
| `BACKEND/app/services/answer_validator.py` | Post-processes generated answers to verify numerical consistency | `AnswerValidator.validate_answer()` | `llm_service.py`, `rag_engine.py` |
| `BACKEND/app/services/rag_engine.py` | Master pipeline coordinator executing full hybrid RAG vs baseline | `RAGEngine.answer_question()` | All services and API layer |
| `frontend/src/pages/UploadPage.jsx` | Upload interface with drag-and-drop dropzone and real-time stage progress polling | `handleDrop()`, `pollStatus()` | `api.js` |
| `frontend/src/pages/ChatPage.jsx` | Full-screen conversational AI chat interface with citation card rendering | `handleSendMessage()` | `api.js` |

---

## 17. Installation and Setup

### 17.1 System Prerequisites
- **Operating System:** Windows 10/11, macOS, or Linux (Ubuntu 20.04+).
- **Python:** Version `3.11` or `3.13`.
- **Node.js:** Version `18.x` or `20.x` (with `npm`).
- **RAM:** Minimum 8 GB (16 GB recommended for BGE-M3 embedding on CPU).

### 17.2 Step-by-Step Installation

#### 1. Clone the Repository
```bash
git clone https://github.com/Amansharma606/PolicyLens_.git
cd PolicyLens_
```

#### 2. Backend Setup
```bash
# Navigate to backend directory
cd BACKEND

# Create Python virtual environment
python -m venv venv

# Activate virtual environment
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On macOS / Linux:
source venv/bin/activate

# Install exact verified dependencies
pip install -r requirements.txt
```

#### 3. Backend Environment Configuration
Copy `.env.example` to create `.env`:
```bash
# On Windows:
copy .env.example .env
# On macOS / Linux:
cp .env.example .env
```
Open `.env` and set your preferred configuration. To use Google Gemini:
```ini
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_actual_gemini_api_key_here
```
*(If no API key is provided, the backend automatically uses its local deterministic grounded fallback engine without failing).*

#### 4. Frontend Setup
```bash
# Open a new terminal and navigate to frontend directory
cd frontend

# Install Node.js packages
npm install
```

#### 5. Frontend Environment Configuration
```bash
# On Windows:
copy .env.example .env
# On macOS / Linux:
cp .env.example .env
```
Ensure `VITE_API_URL=http://localhost:8000` is present.

---

## 18. How to Run

### 18.1 Start the Backend Server
From the `BACKEND/` directory with the virtual environment activated:
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
- **Backend API Root:** `http://127.0.0.1:8000`
- **Interactive Swagger Documentation:** `http://127.0.0.1:8000/docs`
- **ReDoc Documentation:** `http://127.0.0.1:8000/redoc`

### 18.2 Start the Frontend Server
From the `frontend/` directory:
```bash
npm run dev
```
- **Frontend Application URL:** `http://localhost:5173`

### 18.3 How to Test the Complete System
1. Open your browser and navigate to `http://localhost:5173`.
2. Login with the seeded demonstration account:
   - **Email:** `analyst@policylens.ai`
   - **Password:** `PolicyLens@2026`
3. Click **Upload Policy** in the left sidebar.
4. Drag and drop a sample policy PDF (e.g., `BACKEND/sample_policies/CareShield_Health_Insurance_Policy.pdf`).
5. Watch the real-time progress bar smoothly transition through:
   - *Extracting text and structure (PyMuPDF)...*
   - *Classifying policy clauses...*
   - *Generating vector embeddings (BGE-M3)...*
   - *Completed (100%).*
6. Click **Ask Questions** to open the chat interface.
7. Ask: *"What is the waiting period for pre-existing diseases?"* and view the 4-part structured answer and page citations.

---

## 19. Example Workflow

### Scenario: Asking About Insurance Claim Conditions
*User uploads `CareShield_Health_Insurance_Policy.pdf` (5 pages) and asks:*  
**"What are the conditions for claiming insurance?"**

### What Happens Internally:
1. **Question Analysis:** [`question_analyzer.py`](file:///d:/PolicyLens/BACKEND/app/services/question_analyzer.py) detects:
   - Intent: `claim_inquiry`.
   - Topic: `claim_procedure`.
   - Primary Category to boost: `Claim Requirement`.
   - Dynamic Weights: Dense $\alpha = 0.40$, BM25 $\beta = 0.45$, Category $\gamma = 0.15$.
2. **Hybrid Retrieval:** [`hybrid_retriever.py`](file:///d:/PolicyLens/BACKEND/app/services/hybrid_retriever.py) scores all 44 clauses of the document.
   - Clause 5.1 on Page 3 (*"Claim Intimation within 24 hours of emergency hospitalization"*) and Clause 5.2 on Page 3 (*"Submission of original discharge summary, bills, prescriptions within 30 days"*) receive high BM25 and Category scores ($> 0.88$).
3. **Cross-Encoder Reranking:** Candidates are evaluated; Clause 5.1 and 5.2 are ranked at the top.
4. **Completeness Verification:** Confirms that intimation timelines and required documents are both present.
5. **LLM Generation:** Gemini formats the retrieved clauses into the 4-part structure.
6. **Answer Validation:** Verifies that "24 hours" and "30 days" match the exact text.
7. **Frontend Display:**
   ```markdown
   ### Direct Answer
   To claim reimbursement, you must intimate the insurer within 24 hours of emergency admission and submit all original claim documents within 30 days of hospital discharge.

   ### Simple Explanation
   In an emergency, inform the insurance company immediately on the same day. Keep all original hospital bills, prescriptions, and the discharge card safely, and submit them within one month after discharge.

   ### Important Conditions
   - **Emergency Intimation:** Within 24 hours of hospital admission.
   - **Planned Hospitalization:** At least 48 hours prior notice required.
   - **Document Submission Timeline:** Within 30 days from discharge date.
   - **Required Documents:** Original itemized hospital bills, discharge summary, pharmacy receipts, and doctor prescriptions.

   ### Evidence from Your Policy
   This information is grounded in Section 5: Claim Procedure (Clause 5.1 & Clause 5.2) on Page 3 of your uploaded policy.
   ```

---

## 20. Limitations

1. **Scanned Image-Only PDFs (OCR Dependency):** If a PDF contains raster images without an embedded text layer, PyMuPDF cannot extract character streams. The system flags this as `scanned_ocr_required`. Automatic OCR via Tesseract/PaddleOCR is not yet integrated.
2. **Multi-Column Financial Table Layouts:** Complex nested financial matrices (e.g., multi-tier room rent caps across 6 tiers) are extracted as linear text streams, which can occasionally separate column headers from values.
3. **CPU Embedding Latency:** Running BGE-M3 on a standard consumer CPU requires ~70 seconds for 13 pages and ~480 seconds for 37 pages. GPUs with CUDA support reduce this time significantly.
4. **Single-Document Context Per Query:** Conversations are currently isolated to one document at a time. Cross-policy comparison (e.g., comparing Star Health vs CareShield simultaneously in one prompt) is not yet supported.

---

## 21. Future Scope

1. **Integrated Multi-Modal OCR:** Add Tesseract OCR and PaddleOCR pipelines to process scanned physical policy forms and hospital receipts.
2. **Supervised DeBERTa-v3 Fine-Tuning:** Fine-tune `microsoft/deberta-v3-base` on a dataset of 5,000 labeled health insurance clauses to replace regex-based classification heuristics.
3. **Multi-Policy Comparative Analysis:** Allow users to select two uploaded policies and automatically generate side-by-side comparison tables.
4. **Table-to-Graph RAG:** Parse policy tables into structured Knowledge Graph triples for complex sub-limit lookups.
5. **Local 4-Bit GGUF Deployment:** Package quantized local LLMs (e.g. Llama-3.2-3B-Instruct GGUF) via llama.cpp for complete offline, cloud-free privacy.

---

## 22. Faculty Presentation Script

### A. 1-Minute Project Introduction (Elevator Pitch)
> *"Good morning, respected faculty. My project is **PolicyLens**, an intelligent AI system designed to analyze and explain complex health insurance policy documents. Most policyholders never read their 40-page policy agreements due to dense legal jargon, hidden exclusions, and complicated waiting periods. This often leads to claim rejection during medical emergencies. PolicyLens solves this by allowing users to upload their insurance PDF and ask questions in plain English, Hindi, or Hinglish. Instead of using generic AI that hallucinates, PolicyLens uses a Structure-Aware Hybrid RAG architecture combining BGE-M3 dense embeddings and BM25 sparse search. It delivers plain-language answers accompanied by verifiable page numbers and clause citations from their specific policy."*

### B. 2-Minute Technical Explanation
> *"Technically, PolicyLens is built as an asynchronous decoupled architecture with a React 19 frontend and a FastAPI backend. When a PDF is uploaded, the API responds immediately with an HTTP 202 Accepted status, while a background worker processes the document in six sequential stages. First, PyMuPDF extracts native digital text streams while preserving exact page numbers. Second, our bounded chunking algorithm divides the text into natural legal clauses between 80 and 240 words. Third, a rule-calibrated classifier tags each clause into one of five policy dimensions: Coverage, Exclusion, Waiting Period, Condition, or Claim Requirement.*
> 
> *Fourth, we generate 1024-dimensional dense semantic vectors using BAAI/bge-m3 and simultaneously build an inverted BM25 lexical index. When a user asks a question, our Question Analyzer detects intent and query language. We execute dynamic hybrid retrieval using an adaptive scoring formula that balances semantic meaning and exact numerical precision. The top candidates are reranked using a Cross-Encoder transformer, verified for completeness, and passed to Google Gemini 1.5 Flash with strict grounding instructions. Finally, an Answer Validator verifies numerical consistency before delivering a 4-part structured response to the user."*

### C. Complete PDF Processing Explanation
> *"The PDF processing pipeline ensures that text chunking preserves legal meaning. Traditional chunking splits text at fixed character counts, which frequently severs clause titles from their conditions. In PolicyLens, we use structure-aware bounded segmentation. We identify section headings and clause numbers, protect currency figures and decimal numbers using token masking, and split oversized clauses on complete sentence boundaries with a 1-sentence overlap. Every chunk in the database maintains a strict relational foreign key to its document ID and page number, ensuring zero cross-document data leakage."*

### D. Real-Life Example Walkthrough
> *"For instance, when a user uploads a retail health policy and asks: 'What is the waiting period for pre-existing disease?', the system identifies the intent as a waiting period inquiry. The retriever applies a 35% category boost to Waiting Period clauses. It retrieves the exact clause from Page 12 specifying a 36-month waiting period. The cross-encoder ranks this at the top. The LLM then structures the response into Direct Answer, Simple Explanation, Conditions, and Evidence, accurately citing Page 12. If the user asks about an uncovered cosmetic treatment not mentioned in the policy, the system honestly states that no evidence exists in the document, completely eliminating hallucinations."*

---

## 23. Faculty Viva Questions and Answers

#### Q1: What is PolicyLens?
**Ans:** PolicyLens is an AI-powered health insurance policy understanding system that uses document-grounded Retrieval-Augmented Generation (RAG) to explain policy documents in simple English, Hindi, and Hinglish with exact page and clause citations.

#### Q2: Why did you develop this project?
**Ans:** To bridge the gap between complex legal insurance policies and everyday consumers, preventing claim rejections caused by misunderstood waiting periods, exclusions, and financial sub-limits.

#### Q3: What is NLP?
**Ans:** Natural Language Processing (NLP) is a subfield of artificial intelligence focused on enabling computers to understand, interpret, extract, and generate human language text.

#### Q4: What is PDF text extraction?
**Ans:** The automated process of parsing the internal binary structure of a PDF file to extract readable character streams, font metrics, line breaks, and page boundaries into programmatic strings.

#### Q5: What is text preprocessing?
**Ans:** The cleaning and normalization of raw text before indexing, including removing non-printable control characters, standardizing quotes, eliminating headers/footers, and protecting abbreviations and decimals.

#### Q6: What is tokenization?
**Ans:** The process of breaking a continuous sequence of text into smaller discrete linguistic units (tokens), such as words, sub-words, or punctuation marks.

#### Q7: What is chunking?
**Ans:** Dividing a lengthy document into smaller, coherent text segments (chunks) that fit within an embedding model's context window while preserving semantic meaning.

#### Q8: Why is chunk overlap needed?
**Ans:** Chunk overlap ensures that contextual information located at the boundary between two chunks is not lost, maintaining continuity across segment transitions.

#### Q9: What are embeddings?
**Ans:** Dense numerical vectors in continuous high-dimensional space that represent the semantic meaning of text, where words or sentences with similar meanings are positioned close to each other.

#### Q10: What is vector search?
**Ans:** An information retrieval technique that calculates mathematical similarity (such as Cosine Similarity or Dot Product) between a query vector and document vectors to find semantically relevant content.

#### Q11: What is an LLM?
**Ans:** A Large Language Model (LLM) is a deep neural network (typically a Transformer) trained on massive text corpora to understand and generate human-like text based on contextual prompts.

#### Q12: What is the difference between a dataset and a document?
**Ans:** A dataset is a structured collection of multiple data points or annotated examples used to train or evaluate models. A document is an unstructured, single source text (such as a 40-page PDF) used dynamically as a runtime knowledge reference.

#### Q13: Is your model trained or pre-trained?
**Ans:** All AI models in PolicyLens (BGE-M3, MiniLM, Cross-Encoder, Gemini) are **pre-trained models used for inference**. No custom model weights were trained or fine-tuned.

#### Q14: Which embedding model is used?
**Ans:** `BAAI/bge-m3` (1024-dimensional dense representations), with `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional) configured as an automatic fallback.

#### Q15: How does the backend communicate with the frontend?
**Ans:** Through asynchronous RESTful JSON APIs built with FastAPI, using HTTP POST/GET requests and bearer JWT authentication tokens over Axios.

#### Q16: How do you handle large PDFs without timeouts?
**Ans:** By decoupling file upload from AI processing. The upload API returns an immediate HTTP 202 Accepted status in 50 milliseconds, and processing executes in a background worker while the frontend polls progress.

#### Q17: What is RAG?
**Ans:** Retrieval-Augmented Generation (RAG) is an AI architecture that enhances an LLM by retrieving relevant facts from an external knowledge base (e.g. an uploaded PDF) and injecting them into the LLM prompt.

#### Q18: What is Hybrid Retrieval?
**Ans:** An information retrieval technique that combines dense semantic search (vector cosine similarity) and sparse lexical search (BM25 keyword matching) to achieve both conceptual understanding and exact term precision.

#### Q19: What is BM25?
**Ans:** BM25 (Best Matching 25) is a probabilistic ranking algorithm that calculates relevance scores based on term frequency (TF), inverse document frequency (IDF), and document length normalization.

#### Q20: What is a Cross-Encoder reranker?
**Ans:** A transformer model that processes a query and a passage together through cross-attention, producing a single, highly accurate relevance score that reorders initial retrieval candidates.

#### Q21: What is the Completeness Checker?
**Ans:** A validation component that checks whether retrieved evidence covers all required policy dimensions (e.g., ensuring a coverage question also checks waiting periods) and flags unmentioned illnesses to prevent hallucinations.

#### Q22: What is cosine similarity?
**Ans:** A mathematical metric measuring the cosine of the angle between two multi-dimensional vectors:
$$\text{Cosine Similarity}(\vec{u}, \vec{v}) = \frac{\vec{u} \cdot \vec{v}}{\|\vec{u}\| \|\vec{v}\|}$$

#### Q23: How do you prevent hallucinations in LLM answers?
**Ans:** By using a strict system prompt instructing the model to rely solely on retrieved evidence, validating numerical figures against the evidence text, and triggering an insufficient evidence alert when terms are absent from the document.

#### Q24: What database is used?
**Ans:** SQLite 3 configured with Write-Ahead Logging (WAL) mode for multi-threaded concurrency, alongside local disk caches for FAISS binary indices and BM25 pickles.

#### Q25: How does PolicyLens support Hindi and Hinglish queries?
**Ans:** BGE-M3 possesses cross-lingual embedding capabilities that map Hindi and Hinglish queries to English policy concepts in the same vector space, while the LLM generates answers in the user's selected language.

#### Q26: What are the 5 policy dimensions used for classification?
**Ans:** Coverage, Exclusion, Waiting Period, Condition, and Claim Requirement.

#### Q27: What are the main limitations of the current system?
**Ans:** Lack of native OCR for scanned image-only PDFs, linear parsing of complex multi-tier tables, and CPU latency during dense embedding generation for large documents.

#### Q28: What is the future scope of PolicyLens?
**Ans:** Integrating PaddleOCR for scanned claims, fine-tuning DeBERTa-v3 on annotated insurance clauses, table-to-graph Knowledge RAG, and running 4-bit quantized local LLMs for complete offline privacy.

---

*Authored for the PolicyLens Project Repository & Academic Evaluation.*
