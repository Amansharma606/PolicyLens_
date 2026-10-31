import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { 
  Files, 
  Search, 
  UploadCloud, 
  MessageSquare, 
  Eye, 
  Trash2, 
  LayoutGrid, 
  Table as TableIcon, 
  Clock, 
  FileText, 
  X, 
  Copy, 
  AlertTriangle,
  CheckCircle2,
  Filter,
  Sparkles,
  BookOpen,
  ChevronDown,
  ChevronUp
} from 'lucide-react';
import { getDocuments, deleteDocument, getDocumentText, getDocumentExplanation } from '../services/api';
import { useToast } from '../context/ToastContext';

export const DocumentLibrary = () => {
  const [documents, setDocuments] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [viewMode, setViewMode] = useState('grid'); // 'grid' | 'table'
  const [loading, setLoading] = useState(true);

  // Modal for previewing text and explanation
  const [previewDoc, setPreviewDoc] = useState(null);
  const [modalTab, setModalTab] = useState('explanation'); // 'explanation' | 'text'
  const [previewTextData, setPreviewTextData] = useState(null);
  const [previewExplanation, setPreviewExplanation] = useState(null);
  const [selectedPage, setSelectedPage] = useState(1);
  const [expandedSections, setExpandedSections] = useState({});
  const [loadingPreview, setLoadingPreview] = useState(false);

  // Modal for delete confirmation
  const [docToDelete, setDocToDelete] = useState(null);

  const navigate = useNavigate();
  const toast = useToast();

  const fetchDocs = async () => {
    try {
      setLoading(true);
      const data = await getDocuments();
      setDocuments(data);
    } catch (err) {
      console.error('Error fetching documents:', err);
      toast.error('Could not load policy library.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocs();
  }, []);

  const handleOpenPreview = async (doc, initialTab = 'explanation') => {
    setPreviewDoc(doc);
    setModalTab(initialTab);
    setSelectedPage(1);
    setLoadingPreview(true);
    try {
      const [textData, explData] = await Promise.all([
        getDocumentText(doc.id).catch(() => null),
        getDocumentExplanation(doc.id).catch(() => null)
      ]);
      setPreviewTextData(textData);
      setPreviewExplanation(explData);
    } catch (err) {
      toast.error('Failed to load document preview.');
    } finally {
      setLoadingPreview(false);
    }
  };

  const closePreview = () => {
    setPreviewDoc(null);
    setPreviewTextData(null);
    setPreviewExplanation(null);
  };

  const toggleSection = (key) => {
    setExpandedSections((prev) => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  const confirmDelete = async () => {
    if (!docToDelete) return;
    try {
      await deleteDocument(docToDelete.id);
      toast.success(`Deleted ${docToDelete.filename}`);
      setDocuments((prev) => prev.filter((d) => d.id !== docToDelete.id));
      setDocToDelete(null);
    } catch (err) {
      toast.error('Failed to delete document.');
    }
  };

  const filteredDocs = documents.filter((doc) => {
    const matchesSearch = doc.filename.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || doc.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const activePageText = previewTextData?.pages?.find((p) => p.page === selectedPage);

  return (
    <div className="space-y-8 animate-fadeIn max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">Policy Library</h2>
          <p className="text-slate-500 text-sm mt-1">
            Browse, manage, and explore all uploaded policy documents.
          </p>
        </div>

        <Link
          to="/upload"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm transition-all shadow-md shadow-blue-600/30 self-start sm:self-auto"
        >
          <UploadCloud className="w-4 h-4" />
          <span>Upload Policy</span>
        </Link>
      </div>

      {/* Filter and View Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white p-4 rounded-2xl border border-slate-200/80 shadow-sm">
        <div className="flex flex-wrap items-center gap-3 flex-1">
          {/* Search Bar */}
          <div className="relative flex-1 min-w-[220px]">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search policies by name..."
              className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-50 border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600"
            />
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-slate-400 hidden sm:inline">Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs font-medium text-slate-700 focus:outline-none"
            >
              <option value="all">All Documents</option>
              <option value="ready">Ready (Indexed)</option>
              <option value="scanned_ocr_required">Scanned (OCR Required)</option>
            </select>
          </div>
        </div>

        {/* View Toggle */}
        <div className="flex items-center gap-1 border-t sm:border-t-0 pt-2 sm:pt-0 border-slate-100">
          <button
            onClick={() => setViewMode('grid')}
            className={`p-2 rounded-xl text-xs font-medium transition-colors ${
              viewMode === 'grid' ? 'bg-blue-50 text-blue-600' : 'text-slate-400 hover:text-slate-600'
            }`}
            title="Grid View"
          >
            <LayoutGrid className="w-4 h-4" />
          </button>
          <button
            onClick={() => setViewMode('table')}
            className={`p-2 rounded-xl text-xs font-medium transition-colors ${
              viewMode === 'table' ? 'bg-blue-50 text-blue-600' : 'text-slate-400 hover:text-slate-600'
            }`}
            title="Table View"
          >
            <TableIcon className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Document Listing */}
      {loading ? (
        <div className="p-16 text-center text-slate-400 text-sm bg-white rounded-3xl border border-slate-200">
          Loading policy documents...
        </div>
      ) : filteredDocs.length === 0 ? (
        <div className="p-16 text-center space-y-4 bg-white rounded-3xl border border-slate-200 shadow-sm">
          <FileText className="w-12 h-12 text-slate-300 mx-auto" />
          <h3 className="text-base font-bold text-slate-800">No policy documents found</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            {searchQuery
              ? `No policies matched "${searchQuery}". Try adjusting your filters.`
              : 'Upload health insurance policy PDFs to start querying.'}
          </p>
          <Link
            to="/upload"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 text-white text-xs font-semibold"
          >
            <UploadCloud className="w-4 h-4" />
            <span>Upload Now</span>
          </Link>
        </div>
      ) : viewMode === 'grid' ? (
        /* Grid Layout */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredDocs.map((doc) => (
            <div
              key={doc.id}
              className="bg-white rounded-3xl border border-slate-200/90 p-6 flex flex-col justify-between shadow-sm hover:shadow-md transition-all group"
            >
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="w-12 h-12 rounded-2xl bg-blue-50 border border-blue-100 text-blue-600 flex items-center justify-center shrink-0 group-hover:bg-blue-600 group-hover:text-white transition-colors">
                    <FileText className="w-6 h-6" />
                  </div>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${
                      doc.status === 'ready'
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : 'bg-amber-50 text-amber-700 border border-amber-200'
                    }`}
                  >
                    {doc.status === 'ready' ? 'Ready' : 'OCR Required'}
                  </span>
                </div>

                <div>
                  <h3 className="font-bold text-slate-900 text-sm leading-snug line-clamp-2" title={doc.filename}>
                    {doc.filename}
                  </h3>
                  <div className="flex items-center gap-2 text-xs text-slate-400 mt-2">
                    <Clock className="w-3.5 h-3.5" />
                    <span>{new Date(doc.upload_date).toLocaleDateString()}</span>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2 py-3 px-3.5 rounded-xl bg-slate-50 border border-slate-100 text-center">
                  <div>
                    <span className="block text-[10px] text-slate-400 uppercase font-semibold">Pages</span>
                    <span className="text-xs font-bold text-slate-800">{doc.total_pages}</span>
                  </div>
                  <div>
                    <span className="block text-[10px] text-slate-400 uppercase font-semibold">Words</span>
                    <span className="text-xs font-bold text-slate-800">
                      {doc.total_words > 1000 ? `${(doc.total_words / 1000).toFixed(1)}k` : doc.total_words}
                    </span>
                  </div>
                  <div>
                    <span className="block text-[10px] text-slate-400 uppercase font-semibold">Size</span>
                    <span className="text-xs font-bold text-slate-800">
                      {(doc.file_size / 1024).toFixed(0)} KB
                    </span>
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2 pt-5 border-t border-slate-100 mt-5">
                <button
                  onClick={() => navigate(`/chat/${doc.id}`)}
                  className="flex-1 inline-flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold transition-colors shadow-sm"
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  <span>Ask Questions</span>
                </button>
                <button
                  onClick={() => handleOpenPreview(doc, 'explanation')}
                  className="p-2 rounded-xl bg-blue-50 hover:bg-blue-100 text-blue-600 transition-colors border border-blue-200/60"
                  title="View Policy Explanation"
                >
                  <Sparkles className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handleOpenPreview(doc, 'text')}
                  className="p-2 rounded-xl bg-slate-50 hover:bg-slate-100 text-slate-600 transition-colors border border-slate-200/60"
                  title="Preview Extracted Text"
                >
                  <Eye className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setDocToDelete(doc)}
                  className="p-2 rounded-xl bg-slate-50 hover:bg-rose-50 text-slate-400 hover:text-rose-600 transition-colors border border-slate-200/60"
                  title="Delete Document"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Table Layout */
        <div className="bg-white rounded-3xl border border-slate-200/90 overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs text-slate-500 uppercase font-semibold">
                <tr>
                  <th className="px-6 py-4">Policy Document</th>
                  <th className="px-6 py-4">Pages</th>
                  <th className="px-6 py-4">Words</th>
                  <th className="px-6 py-4">File Size</th>
                  <th className="px-6 py-4">Upload Date</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredDocs.map((doc) => (
                  <tr key={doc.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <FileText className="w-5 h-5 text-blue-600 shrink-0" />
                        <span className="font-semibold text-slate-900 truncate max-w-xs" title={doc.filename}>
                          {doc.filename}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 font-mono text-xs">{doc.total_pages}</td>
                    <td className="px-6 py-4 font-mono text-xs">{doc.total_words.toLocaleString()}</td>
                    <td className="px-6 py-4 font-mono text-xs">{(doc.file_size / 1024).toFixed(0)} KB</td>
                    <td className="px-6 py-4 text-xs text-slate-500">{new Date(doc.upload_date).toLocaleDateString()}</td>
                    <td className="px-6 py-4">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${
                          doc.status === 'ready'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}
                      >
                        {doc.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => navigate(`/chat/${doc.id}`)}
                          className="px-3 py-1.5 rounded-lg bg-blue-50 text-blue-600 hover:bg-blue-100 text-xs font-semibold"
                        >
                          Chat
                        </button>
                        <button
                          onClick={() => handleOpenPreview(doc, 'explanation')}
                          className="p-1.5 rounded-lg text-blue-600 hover:bg-blue-50"
                          title="Policy Explanation"
                        >
                          <Sparkles className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleOpenPreview(doc, 'text')}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600"
                          title="Preview Text"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => setDocToDelete(doc)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Structured Preview / Explanation Modal */}
      {previewDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={closePreview} />
          <div className="relative bg-white rounded-3xl max-w-4xl w-full max-h-[85vh] flex flex-col z-10 shadow-2xl border border-slate-200 overflow-hidden animate-scaleIn">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3 className="font-bold text-slate-900 text-base">{previewDoc.filename}</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {previewDoc.total_pages} total pages • {previewDoc.total_words.toLocaleString()} indexed words
                </p>
              </div>
              <button onClick={closePreview} className="p-1 rounded-lg text-slate-400 hover:text-slate-700">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Tabs */}
            <div className="px-6 pt-3 bg-slate-50 border-b border-slate-200/80 flex items-center gap-3">
              <button
                onClick={() => setModalTab('explanation')}
                className={`pb-2.5 text-xs font-bold transition-all border-b-2 flex items-center gap-1.5 ${
                  modalTab === 'explanation'
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Policy Explanation (10 Dimensions)</span>
              </button>
              <button
                onClick={() => setModalTab('text')}
                className={`pb-2.5 text-xs font-bold transition-all border-b-2 flex items-center gap-1.5 ${
                  modalTab === 'text'
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
              >
                <Eye className="w-3.5 h-3.5" />
                <span>Page-by-Page Text</span>
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {loadingPreview ? (
                <div className="p-12 text-center text-slate-400 text-xs">Loading document data...</div>
              ) : modalTab === 'explanation' ? (
                <div className="space-y-3">
                  <div className="p-3.5 rounded-2xl bg-blue-50/60 border border-blue-100 text-xs text-slate-700">
                    {previewExplanation?.overview || 'Structured evidence breakdown across 10 key insurance dimensions.'}
                  </div>

                  <div className="space-y-2.5">
                    {previewExplanation?.sections?.map((sec) => {
                      const isExpanded = expandedSections[sec.key];
                      const isFound = sec.status === 'found';

                      return (
                        <div
                          key={sec.key}
                          className={`rounded-2xl border transition-all ${
                            isFound ? 'bg-white border-slate-200 shadow-sm' : 'bg-slate-50/70 border-slate-200/60'
                          }`}
                        >
                          <button
                            onClick={() => toggleSection(sec.key)}
                            className="w-full p-3.5 flex items-center justify-between text-left"
                          >
                            <div className="flex items-center gap-2.5 min-w-0">
                              <span className={`w-2 h-2 rounded-full ${isFound ? 'bg-emerald-500' : 'bg-slate-300'}`} />
                              <div>
                                <h4 className="text-xs font-bold text-slate-900">{sec.title}</h4>
                                <p className="text-[11px] text-slate-500 mt-0.5 truncate max-w-md">{sec.summary}</p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                                isFound ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'
                              }`}>
                                {isFound ? `${sec.sources?.length || 0} Clauses` : 'Not in PDF'}
                              </span>
                              {isExpanded ? <ChevronUp className="w-3.5 h-3.5 text-slate-400" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-400" />}
                            </div>
                          </button>

                          {isExpanded && (
                            <div className="px-4 pb-4 pt-1 border-t border-slate-100 space-y-2 text-xs">
                              {isFound ? (
                                <>
                                  {sec.key_points && sec.key_points.length > 0 && (
                                    <ul className="list-disc pl-5 space-y-1 text-slate-600 text-[11px] leading-relaxed">
                                      {sec.key_points.map((pt, i) => (
                                        <li key={i}>{pt}</li>
                                      ))}
                                    </ul>
                                  )}
                                  {sec.sources && sec.sources.length > 0 && (
                                    <div className="space-y-1.5 pt-1">
                                      {sec.sources.map((src, i) => (
                                        <div key={i} className="p-2 rounded-xl bg-slate-50 border border-slate-200/80 font-mono text-[10px] text-slate-600">
                                          <div className="flex items-center justify-between pb-0.5 text-[10px] text-blue-700 font-semibold font-sans">
                                            <span>Page {src.page} • {src.section}</span>
                                            <span className="uppercase text-[9px] px-1 rounded bg-blue-100/70">{src.category}</span>
                                          </div>
                                          "{src.text}"
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </>
                              ) : (
                                <p className="text-slate-500 italic text-[11px] pt-1">
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
              ) : previewTextData && previewTextData.pages ? (
                <>
                  <div className="flex items-center gap-1.5 overflow-x-auto pb-2">
                    {previewTextData.pages.map((p) => (
                      <button
                        key={p.page}
                        onClick={() => setSelectedPage(p.page)}
                        className={`px-3 py-1 rounded-lg text-xs font-semibold shrink-0 transition-colors ${
                          selectedPage === p.page
                            ? 'bg-blue-600 text-white'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                        }`}
                      >
                        P. {p.page}
                      </button>
                    ))}
                  </div>

                  <div className="bg-slate-50 p-4 rounded-2xl border border-slate-200">
                    <div className="flex items-center justify-between text-xs text-slate-500 pb-2 mb-2 border-b border-slate-200">
                      <span>Page {selectedPage} ({activePageText?.word_count || 0} words)</span>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(activePageText?.text || '');
                          toast.success('Page text copied!');
                        }}
                        className="inline-flex items-center gap-1 text-blue-600 font-medium"
                      >
                        <Copy className="w-3.5 h-3.5" />
                        <span>Copy</span>
                      </button>
                    </div>
                    <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-slate-700 max-h-96 overflow-y-auto">
                      {activePageText?.text || 'No extractable text.'}
                    </pre>
                  </div>
                </>
              ) : (
                <div className="text-center p-6 text-slate-400 text-xs">No text preview available.</div>
              )}
            </div>

            <div className="p-4 bg-slate-50 border-t border-slate-100 flex justify-end gap-3">
              <button
                onClick={closePreview}
                className="px-4 py-2 rounded-xl bg-white border border-slate-200 text-xs font-semibold text-slate-700"
              >
                Close
              </button>
              <button
                onClick={() => {
                  closePreview();
                  navigate(`/chat/${previewDoc.id}`);
                }}
                className="px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-semibold shadow-sm"
              >
                Open in Chat
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {docToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => setDocToDelete(null)} />
          <div className="relative bg-white rounded-3xl max-w-md w-full p-6 z-10 shadow-2xl border border-slate-200 space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-rose-50 text-rose-600 flex items-center justify-center">
              <Trash2 className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-bold text-slate-900 text-base">Delete Policy Document?</h3>
              <p className="text-xs text-slate-500 mt-1">
                Are you sure you want to delete <span className="font-semibold text-slate-700">{docToDelete.filename}</span>? All extracted indices and chat history will be removed.
              </p>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setDocToDelete(null)}
                className="px-4 py-2 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-sm"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
