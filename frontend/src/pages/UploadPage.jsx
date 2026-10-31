import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  UploadCloud, 
  FileText, 
  AlertTriangle, 
  CheckCircle2, 
  ArrowRight, 
  Eye, 
  Copy, 
  Search, 
  AlertCircle,
  FileCheck,
  RefreshCw,
  BookOpen,
  Shield,
  Layers,
  ChevronDown,
  ChevronUp,
  Sparkles
} from 'lucide-react';
import { uploadDocument, getDocumentText, getDocumentExplanation } from '../services/api';
import { useToast } from '../context/ToastContext';

export const UploadPage = () => {
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [processingStage, setProcessingStage] = useState('');
  const [uploadedDoc, setUploadedDoc] = useState(null);
  const [extractedData, setExtractedData] = useState(null);
  const [explanationData, setExplanationData] = useState(null);
  const [activeTab, setActiveTab] = useState('explanation'); // 'explanation' | 'preview'
  const [selectedPage, setSelectedPage] = useState(1);
  const [expandedSections, setExpandedSections] = useState({});
  const [errorMessage, setErrorMessage] = useState(null);

  const fileInputRef = useRef(null);
  const navigate = useNavigate();
  const toast = useToast();

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processSelectedFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      processSelectedFile(e.target.files[0]);
    }
  };

  const processSelectedFile = async (file) => {
    setErrorMessage(null);

    // Validate extension
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      const msg = 'Invalid file format. Please upload a standard PDF (.pdf) file.';
      setErrorMessage(msg);
      toast.error(msg);
      return;
    }

    // Validate size (30MB max)
    const MAX_MB = 30;
    if (file.size > MAX_MB * 1024 * 1024) {
      const msg = `File is too large (${(file.size / (1024 * 1024)).toFixed(1)}MB). Maximum allowed size is ${MAX_MB}MB.`;
      setErrorMessage(msg);
      toast.error(msg);
      return;
    }

    if (file.size === 0) {
      const msg = 'The selected file is empty (0 bytes). Please select a valid document.';
      setErrorMessage(msg);
      toast.error(msg);
      return;
    }

    try {
      setUploading(true);
      setUploadProgress(15);
      setProcessingStage('Uploading PDF document to server...');

      const response = await uploadDocument(file, (progress) => {
        setUploadProgress(Math.min(progress, 60));
        if (progress > 30) {
          setProcessingStage('Extracting text & preserving page boundaries with PyMuPDF...');
        }
      });

      setUploadProgress(75);
      setProcessingStage('Classifying policy clauses & generating vector embeddings...');

      const doc = response.document;
      setUploadedDoc(doc);

      if (doc.status === 'ready') {
        setUploadProgress(85);
        setProcessingStage('Synthesizing structured 10-point policy explanation...');

        // Parallel fetch for text preview and structured explanation
        const [textResp, explResp] = await Promise.all([
          getDocumentText(doc.id).catch(() => null),
          getDocumentExplanation(doc.id).catch(() => null)
        ]);

        setExtractedData(textResp);
        setExplanationData(explResp);
        setSelectedPage(1);
        setActiveTab('explanation');

        setUploadProgress(100);
        setProcessingStage('Processing complete! Policy is ready for analysis.');
        toast.success(`Successfully processed ${doc.filename}!`);
      } else if (doc.status === 'scanned_ocr_required') {
        toast.warning('Scanned document detected: OCR is required for text search.');
        setUploadProgress(100);
        setProcessingStage('Scanned document flagged.');
      }
    } catch (err) {
      console.error('Upload error:', err);
      const detail = err.response?.data?.detail || err.message || 'Failed to upload and process PDF.';
      setErrorMessage(detail);
      toast.error(detail);
    } finally {
      setUploading(false);
    }
  };

  const copyExtractedText = (text) => {
    navigator.clipboard.writeText(text);
    toast.success('Extracted text copied to clipboard!');
  };

  const toggleSection = (key) => {
    setExpandedSections((prev) => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  const activePageData = extractedData?.pages?.find((p) => p.page === selectedPage);

  return (
    <div className="space-y-8 animate-fadeIn max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">Upload Policy Document</h2>
        <p className="text-slate-500 text-sm mt-1">
          Upload any health insurance policy PDF. The local pipeline extracts clauses, classifies policy dimensions, builds hybrid BGE-M3 + BM25 vectors, and prepares grounded answers.
        </p>
      </div>

      {/* Upload Dropzone */}
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`relative border-2 border-dashed rounded-3xl p-8 sm:p-12 text-center cursor-pointer transition-all ${
          dragActive
            ? 'border-blue-600 bg-blue-50/60 scale-[1.01]'
            : 'border-slate-300 hover:border-blue-500 bg-white hover:bg-slate-50/50'
        } ${uploading ? 'pointer-events-none opacity-80' : ''}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={handleFileChange}
          className="hidden"
        />

        <div className="max-w-md mx-auto space-y-4">
          <div className="w-16 h-16 rounded-2xl bg-blue-50 border border-blue-100 text-blue-600 mx-auto flex items-center justify-center shadow-sm">
            <UploadCloud className="w-8 h-8" />
          </div>

          <div>
            <p className="text-base font-semibold text-slate-800">
              Drag and drop your insurance policy PDF here
            </p>
            <p className="text-xs text-slate-500 mt-1">
              or <span className="text-blue-600 font-semibold underline underline-offset-2">browse files</span> from your computer
            </p>
          </div>

          <div className="flex items-center justify-center gap-4 text-xs text-slate-400 pt-2 border-t border-slate-100">
            <span>Supports standard PDF</span>
            <span>•</span>
            <span>Max size: 30 MB</span>
            <span>•</span>
            <span>Private & Isolated</span>
          </div>
        </div>

        {/* Progress Bar when uploading */}
        {uploading && (
          <div className="absolute inset-0 bg-white/95 rounded-3xl flex flex-col items-center justify-center p-8 backdrop-blur-sm z-20">
            <div className="w-full max-w-md space-y-3">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-700">
                <span className="flex items-center gap-2">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-blue-600" />
                  {processingStage}
                </span>
                <span className="font-mono text-blue-600">{uploadProgress}%</span>
              </div>
              <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-600 transition-all duration-300 ease-out rounded-full"
                  style={{ width: `${uploadProgress}%` }}
                ></div>
              </div>
              <p className="text-[11px] text-slate-400 text-center">
                Preserving page boundaries, classifying clauses, and computing hybrid similarity indices.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Error State Banner */}
      {errorMessage && (
        <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-900 flex items-start gap-3 text-sm animate-fadeIn">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-bold">Upload Notice</p>
            <p className="text-xs text-rose-700 mt-0.5">{errorMessage}</p>
          </div>
        </div>
      )}

      {/* Scanned PDF Warning Banner */}
      {uploadedDoc && uploadedDoc.status === 'scanned_ocr_required' && (
        <div className="p-5 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 space-y-2 animate-fadeIn">
          <div className="flex items-center gap-2 font-bold text-amber-900 text-sm">
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
            <span>Scanned / Image-Only PDF Detected</span>
          </div>
          <p className="text-xs text-amber-800 leading-relaxed">
            {uploadedDoc.error_message ||
              'This PDF appears to be a scanned image or contains non-selectable rasterized pages. Optical Character Recognition (OCR) is required to parse and question non-searchable image PDFs.'}
          </p>
        </div>
      )}

      {/* Uploaded Document Summary & Action */}
      {uploadedDoc && (
        <div className="bg-white rounded-3xl border border-slate-200/80 p-6 sm:p-8 shadow-sm space-y-6 animate-fadeIn">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-100">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-2xl bg-emerald-50 border border-emerald-100 text-emerald-600 flex items-center justify-center shrink-0">
                <FileCheck className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">{uploadedDoc.filename}</h3>
                <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500 mt-1">
                  <span>{uploadedDoc.total_pages} Pages</span>
                  <span>•</span>
                  <span>{uploadedDoc.total_words.toLocaleString()} Words</span>
                  <span>•</span>
                  <span>{(uploadedDoc.file_size / 1024).toFixed(1)} KB</span>
                  <span>•</span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${
                    uploadedDoc.status === 'ready' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
                  }`}>
                    {uploadedDoc.status}
                  </span>
                </div>
              </div>
            </div>

            {uploadedDoc.status === 'ready' && (
              <button
                onClick={() => navigate(`/chat/${uploadedDoc.id}`)}
                className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm transition-all shadow-md shadow-blue-600/30 active:scale-95"
              >
                <span>Start Asking Questions</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* View Mode Switcher Tabs */}
          <div className="flex items-center gap-3 border-b border-slate-100 pb-2">
            <button
              onClick={() => setActiveTab('explanation')}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                activeTab === 'explanation'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Structured Policy Explanation (10 Dimensions)</span>
            </button>
            <button
              onClick={() => setActiveTab('preview')}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                activeTab === 'preview'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              <Eye className="w-3.5 h-3.5" />
              <span>Extracted Text Preview</span>
            </button>
          </div>

          {/* TAB 1: Structured Policy Explanation */}
          {activeTab === 'explanation' && (
            <div className="space-y-4 animate-fadeIn">
              <div className="p-4 rounded-2xl bg-blue-50/50 border border-blue-100 text-xs text-slate-700 flex items-start gap-3">
                <BookOpen className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                <p className="leading-relaxed">
                  {explanationData?.overview ||
                    'Synthesized structured summary grounded strictly in the clauses and pages of this policy.'}
                </p>
              </div>

              <div className="grid grid-cols-1 gap-3">
                {explanationData?.sections?.map((sec) => {
                  const isExpanded = expandedSections[sec.key];
                  const isFound = sec.status === 'found';

                  return (
                    <div
                      key={sec.key}
                      className={`rounded-2xl border transition-all ${
                        isFound
                          ? 'bg-white border-slate-200 hover:border-blue-300 shadow-sm'
                          : 'bg-slate-50/70 border-slate-200/60 opacity-80'
                      }`}
                    >
                      <button
                        onClick={() => toggleSection(sec.key)}
                        className="w-full p-4 flex items-center justify-between text-left"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span
                            className={`w-2 h-2 rounded-full ${
                              isFound ? 'bg-emerald-500' : 'bg-slate-300'
                            }`}
                          />
                          <div>
                            <h4 className="text-sm font-bold text-slate-900 truncate">
                              {sec.title}
                            </h4>
                            <p className="text-xs text-slate-500 mt-0.5 truncate max-w-lg">
                              {sec.summary}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                              isFound
                                ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-slate-200 text-slate-600'
                            }`}
                          >
                            {isFound ? `${sec.sources?.length || 0} Clauses` : 'Not in PDF'}
                          </span>
                          {isExpanded ? (
                            <ChevronUp className="w-4 h-4 text-slate-400" />
                          ) : (
                            <ChevronDown className="w-4 h-4 text-slate-400" />
                          )}
                        </div>
                      </button>

                      {/* Expanded Section Details */}
                      {isExpanded && (
                        <div className="px-5 pb-5 pt-1 border-t border-slate-100 space-y-3 text-xs">
                          {isFound ? (
                            <>
                              {sec.key_points && sec.key_points.length > 0 && (
                                <div className="space-y-1.5 pt-2">
                                  <span className="font-bold text-slate-700">Verified Findings:</span>
                                  <ul className="list-disc pl-5 space-y-1 text-slate-600 leading-relaxed">
                                    {sec.key_points.map((pt, i) => (
                                      <li key={i}>{pt}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}

                              {sec.sources && sec.sources.length > 0 && (
                                <div className="space-y-2 pt-2">
                                  <span className="font-bold text-slate-700">Source Evidence:</span>
                                  {sec.sources.map((src, i) => (
                                    <div
                                      key={i}
                                      className="p-2.5 rounded-xl bg-slate-50 border border-slate-200/80 font-mono text-[11px] text-slate-600"
                                    >
                                      <div className="flex items-center justify-between pb-1 text-[10px] text-blue-700 font-semibold font-sans">
                                        <span>Page {src.page} • {src.section}</span>
                                        <span className="uppercase text-[9px] px-1.5 py-0.2 rounded bg-blue-100/70">
                                          {src.category}
                                        </span>
                                      </div>
                                      "{src.text}"
                                    </div>
                                  ))}
                                </div>
                              )}
                            </>
                          ) : (
                            <p className="text-slate-500 italic pt-2">
                              {sec.limitations || 'This dimension was not found in the uploaded policy text.'}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* TAB 2: Extracted Text Preview Section */}
          {activeTab === 'preview' && extractedData && extractedData.pages && extractedData.pages.length > 0 && (
            <div className="space-y-4 animate-fadeIn">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Eye className="w-4 h-4 text-slate-500" />
                  <h4 className="text-sm font-bold text-slate-800">Extracted Text Preview</h4>
                  <span className="text-xs text-slate-400">({extractedData.total_pages} total pages)</span>
                </div>

                {/* Page Navigation Tabs */}
                <div className="flex items-center gap-1.5 overflow-x-auto pb-1 max-w-full sm:max-w-md">
                  {extractedData.pages.map((p) => (
                    <button
                      key={p.page}
                      onClick={() => setSelectedPage(p.page)}
                      className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors shrink-0 ${
                        selectedPage === p.page
                          ? 'bg-blue-600 text-white font-semibold shadow-sm'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      }`}
                    >
                      P. {p.page}
                    </button>
                  ))}
                </div>
              </div>

              {/* Active Page Text Box */}
              <div className="relative rounded-2xl bg-slate-50 border border-slate-200 p-4 sm:p-5">
                <div className="flex items-center justify-between pb-3 border-b border-slate-200/80 mb-3 text-xs text-slate-500">
                  <span className="font-semibold text-slate-700">
                    Page {selectedPage} ({activePageData?.word_count || 0} words)
                  </span>
                  <button
                    onClick={() => copyExtractedText(activePageData?.text || '')}
                    className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 font-medium"
                  >
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy Page Text</span>
                  </button>
                </div>

                <div className="max-h-72 overflow-y-auto text-xs leading-relaxed text-slate-700 whitespace-pre-wrap font-mono bg-white p-4 rounded-xl border border-slate-200/60 shadow-inner">
                  {activePageData?.text || <span className="text-slate-400 italic">No extractable text on this page.</span>}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
