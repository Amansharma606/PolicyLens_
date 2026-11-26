import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  UploadCloud,
  AlertTriangle,
  ArrowRight,
  Eye,
  Copy,
  AlertCircle,
  FileCheck,
  RefreshCw,
  BookOpen,
  ChevronDown,
  ChevronUp,
  Sparkles,
  FileText
} from 'lucide-react';
import { uploadDocument, getDocumentText, getDocumentExplanation, getDocumentStatus } from '../services/api';
import { useToast } from '../context/ToastContext';

const renderFindingBulletWithBadges = (pointText) => {
  if (!pointText) return null;
  const cleanText = pointText.replace(/\*\*/g, '').replace(/\*/g, '').trim();
  const pageMatch = cleanText.match(/^(.*?)\s*\((Pages?\s+[\d,\s&-]+)\)\.?$/i);

  if (!pageMatch) {
    return <span>{cleanText}</span>;
  }

  const body = pageMatch[1].trim();
  const pageTokens = pageMatch[2].match(/\d+/g) || [];

  return (
    <span>
      <span>{body.endsWith('.') ? body : `${body}.`}</span>
      <span className="inline-flex flex-wrap items-center gap-1 ml-1.5 align-baseline">
        {pageTokens.map((pg, idx) => (
          <span
            key={idx}
            className="inline-flex items-center px-1.5 py-0.5 rounded-md text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200/70"
          >
            Page {pg}
          </span>
        ))}
      </span>
    </span>
  );
};

export const UploadPage = () => {
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [processingStage, setProcessingStage] = useState('');
  const [uploadedDoc, setUploadedDoc] = useState(null);
  const [extractedData, setExtractedData] = useState(null);
  const [explanationData, setExplanationData] = useState(null);
  const [loadingExplanation, setLoadingExplanation] = useState(false);
  const [activeTab, setActiveTab] = useState('preview'); // 'preview' | 'explanation'
  const [selectedPage, setSelectedPage] = useState(1);
  const [expandedSections, setExpandedSections] = useState({});
  const [showExactSources, setShowExactSources] = useState({});
  const [errorMessage, setErrorMessage] = useState(null);

  const fileInputRef = useRef(null);
  const pollTimerRef = useRef(null);
  const navigate = useNavigate();
  const toast = useToast();

  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, []);

  const stopPolling = () => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  };

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

  const startStage2BackgroundPolling = (docId) => {
    stopPolling();
    pollTimerRef.current = setInterval(async () => {
      try {
        const statusResp = await getDocumentStatus(docId);
        setUploadedDoc((prev) => ({ ...(prev || {}), ...statusResp }));
        setProcessingStage(statusResp.processing_stage || 'Enriching semantic index & policy summary...');
        setUploadProgress(statusResp.processing_progress || 50);

        if (statusResp.has_explanation || statusResp.status === 'completed' || statusResp.status === 'ready') {
          const explResp = await getDocumentExplanation(docId).catch(() => null);
          if (explResp) {
            setExplanationData(explResp);
          }
          if (statusResp.status === 'completed' || statusResp.status === 'ready') {
            stopPolling();
            toast.success(`10-Dimension policy summary ready for ${statusResp.filename}!`);
          }
        } else if (statusResp.status === 'failed') {
          stopPolling();
        }
      } catch (err) {
        console.warn('Background status poll error:', err);
      }
    }, 1200);
  };

  const processSelectedFile = async (file) => {
    setErrorMessage(null);
    setExplanationData(null);
    setExtractedData(null);
    setShowExactSources({});
    stopPolling();

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      const msg = 'Invalid file format. Please upload a standard PDF (.pdf) file.';
      setErrorMessage(msg);
      toast.error(msg);
      return;
    }

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
      setProcessingStage('Uploading & extracting layout-aware policy text...');

      // Stage 1 runs fast (~1-2.5s) and returns 'chat_ready' or 'completed' immediately
      const response = await uploadDocument(file, (progress) => {
        setUploadProgress(Math.max(15, Math.min(Math.round(progress * 0.4), 40)));
      });

      const initialDoc = response.document;
      setUploadedDoc(initialDoc);
      setSelectedPage(1);

      if (initialDoc.status === 'scanned_ocr_required') {
        toast.warning('Scanned document detected: OCR is required for text search.');
        setUploadProgress(100);
        setProcessingStage('Scanned image document flagged.');
        setUploading(false);
        return;
      }

      if (initialDoc.status === 'failed') {
        const errMsg = initialDoc.error_message || 'PDF processing failed.';
        setErrorMessage(errMsg);
        toast.error(errMsg);
        setUploading(false);
        return;
      }

      // Immediately unlock Chat & Text Preview without waiting on heavy models!
      if (initialDoc.status === 'chat_ready' || initialDoc.status === 'completed' || initialDoc.status === 'ready') {
        setUploading(false);
        setUploadProgress(100);
        setProcessingStage(initialDoc.processing_stage || 'Ready for instant Q&A');
        setActiveTab('preview');
        toast.success(`${initialDoc.filename} extracted & ready for instant Chat & Ask!`);

        // Load extracted page text immediately
        getDocumentText(initialDoc.id)
          .then((textResp) => {
            if (textResp) setExtractedData(textResp);
          })
          .catch(() => null);

        return;
      }

      // Fallback polling if ever returned in pure 'processing' state
      setUploading(false);
      startStage2BackgroundPolling(initialDoc.id);
    } catch (err) {
      console.error('Upload error:', err);
      const detail = err.response?.data?.detail || err.message || 'Failed to upload and process PDF.';
      setErrorMessage(detail);
      toast.error(detail);
      setUploading(false);
    }
  };

  const copyExtractedText = (text) => {
    navigator.clipboard.writeText(text);
    toast.success('Extracted text copied to clipboard!');
  };

  const toggleSection = (key) => {
    setExpandedSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleOpenExplanationTab = async () => {
    setActiveTab('explanation');
    if (explanationData || loadingExplanation || !uploadedDoc?.id) return;
    try {
      setLoadingExplanation(true);
      const explResp = await getDocumentExplanation(uploadedDoc.id);
      if (explResp) setExplanationData(explResp);
    } catch (err) {
      toast.error('Could not generate 10-dimension explanation.');
    } finally {
      setLoadingExplanation(false);
    }
  };

  const toggleExactSource = (key) => {
    setShowExactSources((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const activePageData = extractedData?.pages?.find((p) => p.page === selectedPage);
  const isChatUnlocked =
    uploadedDoc &&
    (uploadedDoc.is_ready_for_chat || ['chat_ready', 'completed', 'ready'].includes(uploadedDoc.status));
  const isStage2Enriching = uploadedDoc && uploadedDoc.status === 'chat_ready';

  return (
    <div className="space-y-8 animate-fadeIn max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">Upload Policy Document</h2>
        <p className="text-slate-500 text-sm mt-1">
          Upload any insurance policy PDF. Stage 1 parses clean text and opens instant Chat &amp; Ask within seconds, while Stage 2 enriches semantic search and plain-English policy insights in the background.
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
            <span>Supports Any Policy PDF</span>
            <span>•</span>
            <span>Max size: 30 MB</span>
            <span>•</span>
            <span>Instant Q&amp;A</span>
          </div>
        </div>

        {/* Fast Stage 1 Upload Overlay */}
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
                />
              </div>
              <p className="text-[11px] text-slate-400 text-center">
                Parsing multi-column text &amp; tables for instant Chat readiness...
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
              'This PDF appears to be a scanned image or contains non-selectable rasterized pages. Optical Character Recognition (OCR) is required to parse non-searchable image PDFs.'}
          </p>
        </div>
      )}

      {/* Uploaded Document Summary & Instant Actions */}
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
                  <span>{(uploadedDoc.total_words || 0).toLocaleString()} Words</span>
                  <span>•</span>
                  <span>{((uploadedDoc.file_size || 0) / 1024).toFixed(1)} KB</span>
                  <span>•</span>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold uppercase ${
                      isChatUnlocked
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-amber-100 text-amber-700'
                    }`}
                  >
                    {uploadedDoc.status === 'chat_ready'
                      ? 'Ready to Chat'
                      : ['completed', 'ready'].includes(uploadedDoc.status)
                      ? 'Ready'
                      : uploadedDoc.status}
                  </span>
                </div>
              </div>
            </div>

            {isChatUnlocked && (
              <button
                onClick={() => navigate(`/chat/${uploadedDoc.id}`)}
                className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm transition-all shadow-md shadow-blue-600/30 active:scale-95 cursor-pointer"
              >
                <span>Start Asking Questions</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Non-blocking Stage 2 Background Progress Banner */}
          {isStage2Enriching && (
            <div className="flex items-center gap-3 px-4 py-3 rounded-2xl bg-blue-50/70 border border-blue-200/70 text-xs text-blue-900">
              <RefreshCw className="w-4 h-4 text-blue-600 animate-spin shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="font-semibold truncate">{processingStage}</span>
                  <span className="font-mono font-bold text-blue-700 shrink-0">{uploadProgress}%</span>
                </div>
                <div className="w-full h-1.5 bg-blue-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-600 transition-all duration-300 rounded-full"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* View Mode Switcher Tabs */}
          <div className="flex items-center gap-3 border-b border-slate-100 pb-2">
            <button
              onClick={() => setActiveTab('preview')}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                activeTab === 'preview'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              <Eye className="w-3.5 h-3.5" />
              <span>Extracted Text Preview</span>
            </button>
            <button
              onClick={handleOpenExplanationTab}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                activeTab === 'explanation'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Structured Policy Explanation (10 Dimensions)</span>
            </button>
          </div>

          {/* TAB 1: Clean, Humanized 10-Dimension Explanation (Lazy Loaded on Tab Click) */}
          {activeTab === 'explanation' && (
            <div className="space-y-4 animate-fadeIn">
              {loadingExplanation || !explanationData ? (
                <div className="p-8 rounded-2xl bg-slate-50 border border-slate-200/80 flex flex-col items-center justify-center text-center gap-2">
                  <RefreshCw className="w-5 h-5 text-blue-600 animate-spin" />
                  <p className="text-xs font-semibold text-slate-700">
                    Generating plain-English 10-dimension policy explanation...
                  </p>
                  <p className="text-[11px] text-slate-400">
                    You can also click "Start Asking Questions" anytime!
                  </p>
                </div>
              ) : (
                <>
                  <div className="p-4 rounded-2xl bg-blue-50/50 border border-blue-100 text-xs text-slate-700 flex items-start gap-3">
                    <BookOpen className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                    <p className="leading-relaxed">
                      {explanationData?.overview ||
                        'Plain-English summary grounded strictly in the pages of this policy document.'}
                    </p>
                  </div>

                  <div className="grid grid-cols-1 gap-3">
                    {explanationData?.sections?.map((sec) => {
                      const isExpanded = expandedSections[sec.key];
                      const isFound = sec.status === 'found';
                      const showingExact = showExactSources[sec.key];

                      return (
                        <div
                          key={sec.key}
                          className={`rounded-2xl border transition-all ${
                            isFound
                              ? 'bg-white border-slate-200 hover:border-blue-300 shadow-sm'
                              : 'bg-slate-50/70 border-slate-200/60 opacity-85'
                          }`}
                        >
                          <button
                            onClick={() => toggleSection(sec.key)}
                            className="w-full p-4 flex items-center justify-between text-left cursor-pointer"
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <span
                                className={`w-2 h-2 rounded-full shrink-0 ${
                                  isFound ? 'bg-emerald-500' : 'bg-slate-300'
                                }`}
                              />
                              <div className="min-w-0">
                                <h4 className="text-sm font-bold text-slate-900 truncate">
                                  {sec.title}
                                </h4>
                                <p className="text-xs text-slate-500 mt-0.5 truncate max-w-xl">
                                  {sec.summary}
                                </p>
                              </div>
                            </div>

                            <div className="flex items-center gap-2 shrink-0 ml-2">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                                  isFound
                                    ? 'bg-emerald-100 text-emerald-800'
                                    : 'bg-slate-200 text-slate-600'
                                }`}
                              >
                                {isFound ? `${sec.key_points?.length || sec.sources?.length || 0} Points` : 'Not in PDF'}
                              </span>
                              {isExpanded ? (
                                <ChevronUp className="w-4 h-4 text-slate-400" />
                              ) : (
                                <ChevronDown className="w-4 h-4 text-slate-400" />
                              )}
                            </div>
                          </button>

                          {/* Clean Expanded Section */}
                          {isExpanded && (
                            <div className="px-5 pb-5 pt-2 border-t border-slate-100 space-y-3 text-xs">
                              {isFound ? (
                                <>
                                  {sec.key_points && sec.key_points.length > 0 && (
                                    <div className="space-y-2 pt-1">
                                      <ul className="space-y-2 text-slate-700 leading-relaxed">
                                        {sec.key_points.map((pt, i) => (
                                          <li key={i} className="flex items-start gap-2.5">
                                            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0 mt-2" />
                                            <div className="flex-1 text-[13px] leading-relaxed">
                                              {renderFindingBulletWithBadges(pt)}
                                            </div>
                                          </li>
                                        ))}
                                      </ul>
                                    </div>
                                  )}

                                  {sec.sources && sec.sources.length > 0 && (
                                    <div className="pt-2 border-t border-slate-100/80">
                                      <button
                                        onClick={() => toggleExactSource(sec.key)}
                                        className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 hover:text-blue-600 transition-colors cursor-pointer"
                                      >
                                        <FileText className="w-3.5 h-3.5" />
                                        <span>
                                          {showingExact
                                            ? 'Hide exact policy text'
                                            : `View exact policy text (${sec.sources.length})`}
                                        </span>
                                        {showingExact ? (
                                          <ChevronUp className="w-3.5 h-3.5" />
                                        ) : (
                                          <ChevronDown className="w-3.5 h-3.5" />
                                        )}
                                      </button>

                                      {showingExact && (
                                        <div className="space-y-2 pt-2.5">
                                          {sec.sources.map((src, i) => (
                                            <div
                                              key={i}
                                              className="p-2.5 rounded-xl bg-slate-50 border border-slate-200/80 font-mono text-[11px] text-slate-600"
                                            >
                                              <div className="flex items-center justify-between pb-1 text-[10px] text-blue-700 font-semibold font-sans">
                                                <span>Page {src.page} • {src.section}</span>
                                              </div>
                                              "{src.text}"
                                            </div>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </>
                              ) : (
                                <p className="text-slate-500 italic pt-1">
                                  {sec.limitations || 'Not specified in this policy document.'}
                                </p>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          )}

          {/* TAB 2: Extracted Text Preview */}
          {activeTab === 'preview' && (
            <div className="space-y-4 animate-fadeIn">
              {!extractedData ? (
                <div className="p-8 rounded-2xl bg-slate-50 border border-slate-200/80 flex flex-col items-center justify-center text-center gap-2">
                  <RefreshCw className="w-5 h-5 text-blue-600 animate-spin" />
                  <p className="text-xs font-semibold text-slate-700">Loading extracted page text preview...</p>
                </div>
              ) : (
                <>
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <Eye className="w-4 h-4 text-slate-500" />
                      <h4 className="text-sm font-bold text-slate-800">Extracted Text Preview</h4>
                      <span className="text-xs text-slate-400">({extractedData.total_pages} total pages)</span>
                    </div>

                    <div className="flex items-center gap-1.5 overflow-x-auto pb-1 max-w-full sm:max-w-md">
                      {extractedData.pages.map((p) => (
                        <button
                          key={p.page}
                          onClick={() => setSelectedPage(p.page)}
                          className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors shrink-0 cursor-pointer ${
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

                  <div className="relative rounded-2xl bg-slate-50 border border-slate-200 p-4 sm:p-5">
                    <div className="flex items-center justify-between pb-3 border-b border-slate-200/80 mb-3 text-xs text-slate-500">
                      <span className="font-semibold text-slate-700">
                        Page {selectedPage} ({activePageData?.word_count || 0} words)
                      </span>
                      <button
                        onClick={() => copyExtractedText(activePageData?.text || '')}
                        className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 font-medium cursor-pointer"
                      >
                        <Copy className="w-3.5 h-3.5" />
                        <span>Copy Page Text</span>
                      </button>
                    </div>

                    <div className="max-h-72 overflow-y-auto text-xs leading-relaxed text-slate-700 whitespace-pre-wrap font-mono bg-white p-4 rounded-xl border border-slate-200/60 shadow-inner">
                      {activePageData?.text || <span className="text-slate-400 italic">No extractable text on this page.</span>}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
