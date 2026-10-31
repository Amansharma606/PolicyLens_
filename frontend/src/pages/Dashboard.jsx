import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { 
  FileText, 
  UploadCloud, 
  MessageSquare, 
  ArrowRight, 
  BookOpen, 
  ShieldCheck, 
  CheckCircle2, 
  Clock, 
  Sparkles,
  Layers,
  Database
} from 'lucide-react';
import { getDocuments, getConversations } from '../services/api';

export const Dashboard = () => {
  const [documents, setDocuments] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [docsData, convsData] = await Promise.all([
          getDocuments().catch(() => []),
          getConversations().catch(() => [])
        ]);
        setDocuments(docsData);
        setConversations(convsData);
      } catch (err) {
        console.error("Dashboard data load error:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const totalPages = documents.reduce((sum, d) => sum + (d.total_pages || 0), 0);
  const totalWords = documents.reduce((sum, d) => sum + (d.total_words || 0), 0);

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Welcome Banner */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-slate-900 via-blue-950 to-slate-900 text-white p-8 sm:p-10 shadow-xl border border-blue-900/30">
        <div className="relative z-10 max-w-3xl space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/20 border border-blue-400/30 text-blue-300 text-xs font-medium">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Local Neural Document Intelligence</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            Understand Every Policy.<br />Make Smarter Decisions.
          </h2>
          <p className="text-slate-300 text-base sm:text-lg leading-relaxed max-w-2xl">
            Upload complex insurance policies, ask natural questions, and receive precise answers verified directly against document evidence—with exact page citations.
          </p>
          <div className="flex flex-wrap gap-4 pt-2">
            <Link
              to="/upload"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm transition-all shadow-lg shadow-blue-600/30 active:scale-95"
            >
              <UploadCloud className="w-4 h-4" />
              <span>Upload Policy PDF</span>
            </Link>
            <Link
              to="/chat"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 text-white font-semibold text-sm border border-slate-700 transition-all active:scale-95"
            >
              <MessageSquare className="w-4 h-4 text-blue-400" />
              <span>Start New Conversation</span>
            </Link>
          </div>
        </div>

        {/* Decorative background circle */}
        <div className="absolute right-0 top-0 -mr-20 -mt-20 w-96 h-96 rounded-full bg-blue-600/10 blur-3xl pointer-events-none"></div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="p-6 rounded-2xl bg-white border border-slate-200/80 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Policies Uploaded</span>
            <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
              <FileText className="w-5 h-5" />
            </div>
          </div>
          <p className="text-3xl font-extrabold text-slate-900 mt-3">{loading ? '...' : documents.length}</p>
          <p className="text-xs text-slate-500 mt-1">Available for instant QA</p>
        </div>

        <div className="p-6 rounded-2xl bg-white border border-slate-200/80 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Pages Extracted</span>
            <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
              <BookOpen className="w-5 h-5" />
            </div>
          </div>
          <p className="text-3xl font-extrabold text-slate-900 mt-3">{loading ? '...' : totalPages}</p>
          <p className="text-xs text-slate-500 mt-1">Parsed with page preserving indices</p>
        </div>

        <div className="p-6 rounded-2xl bg-white border border-slate-200/80 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Indexed Words</span>
            <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <Database className="w-5 h-5" />
            </div>
          </div>
          <p className="text-3xl font-extrabold text-slate-900 mt-3">{loading ? '...' : totalWords.toLocaleString()}</p>
          <p className="text-xs text-slate-500 mt-1">Indexed in TF-IDF vectors</p>
        </div>

        <div className="p-6 rounded-2xl bg-white border border-slate-200/80 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Conversations</span>
            <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
              <MessageSquare className="w-5 h-5" />
            </div>
          </div>
          <p className="text-3xl font-extrabold text-slate-900 mt-3">{loading ? '...' : conversations.length}</p>
          <p className="text-xs text-slate-500 mt-1">Multi-turn chat threads</p>
        </div>
      </div>

      {/* Main Two Columns: Recent Documents & Recent Conversations */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Recent Policy Documents (Span 2) */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold text-slate-900">Recent Policy Documents</h3>
              <p className="text-xs text-slate-500">Select any document to view passages or start asking questions</p>
            </div>
            <Link
              to="/documents"
              className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
            >
              View all <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
            {loading ? (
              <div className="p-8 text-center text-slate-400 text-sm">Loading policy documents...</div>
            ) : documents.length === 0 ? (
              <div className="p-10 text-center space-y-3">
                <FileText className="w-12 h-12 text-slate-300 mx-auto" />
                <h4 className="text-sm font-semibold text-slate-700">No policy documents found</h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Upload an insurance policy document in PDF format to start asking questions.
                </p>
                <Link
                  to="/upload"
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-medium"
                >
                  <UploadCloud className="w-4 h-4" />
                  <span>Upload PDF</span>
                </Link>
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {documents.slice(0, 5).map((doc) => (
                  <div
                    key={doc.id}
                    className="p-4 sm:p-5 flex items-center justify-between hover:bg-slate-50/70 transition-colors"
                  >
                    <div className="flex items-center gap-3.5 min-w-0">
                      <div className="w-10 h-10 rounded-xl bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 shrink-0">
                        <FileText className="w-5 h-5" />
                      </div>
                      <div className="min-w-0">
                        <h4 className="text-sm font-semibold text-slate-900 truncate" title={doc.filename}>
                          {doc.filename}
                        </h4>
                        <div className="flex items-center gap-3 text-xs text-slate-500 mt-0.5">
                          <span>{doc.total_pages} {doc.total_pages === 1 ? 'page' : 'pages'}</span>
                          <span>•</span>
                          <span>{(doc.file_size / 1024).toFixed(1)} KB</span>
                          <span>•</span>
                          <span className="capitalize text-emerald-600 font-medium">{doc.status}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0 ml-4">
                      <button
                        onClick={() => navigate(`/chat/${doc.id}`)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 text-xs font-medium transition-colors"
                      >
                        <MessageSquare className="w-3.5 h-3.5" />
                        <span>Chat</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Recent Conversations */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold text-slate-900">Recent Chats</h3>
              <p className="text-xs text-slate-500">Pick up where you left off</p>
            </div>
            <Link
              to="/history"
              className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
            >
              All chats <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-4 divide-y divide-slate-100">
            {loading ? (
              <div className="p-6 text-center text-slate-400 text-xs">Loading conversations...</div>
            ) : conversations.length === 0 ? (
              <div className="p-6 text-center text-slate-400 space-y-2">
                <MessageSquare className="w-8 h-8 text-slate-300 mx-auto" />
                <p className="text-xs text-slate-500">No conversations yet.</p>
                <Link
                  to="/chat"
                  className="text-xs text-blue-600 font-semibold hover:underline inline-block"
                >
                  Start your first chat
                </Link>
              </div>
            ) : (
              conversations.slice(0, 5).map((conv) => (
                <div
                  key={conv.conversation_id}
                  onClick={() => navigate(`/chat/${conv.document_id}?conversation=${conv.conversation_id}`)}
                  className="py-3 px-2 first:pt-0 last:pb-0 hover:bg-slate-50 rounded-xl cursor-pointer transition-colors"
                >
                  <p className="text-xs font-semibold text-slate-800 truncate" title={conv.title}>
                    {conv.title || 'Untitled Conversation'}
                  </p>
                  <div className="flex items-center justify-between mt-1 text-[11px] text-slate-400">
                    <span className="truncate max-w-[150px]">{conv.filename || 'Policy'}</span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {new Date(conv.updated_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Architecture Guarantee Card */}
          <div className="p-5 rounded-2xl bg-gradient-to-br from-blue-50 to-indigo-50/50 border border-blue-100 text-xs text-slate-700 space-y-2.5">
            <div className="flex items-center gap-2 font-bold text-blue-900">
              <ShieldCheck className="w-4 h-4 text-blue-600" />
              <span>Strict Grounding Guarantee</span>
            </div>
            <p className="text-slate-600 leading-relaxed text-[11px]">
              Every answer is synthesized strictly from the uploaded PDF document. Out-of-domain questions are refused automatically, and supporting citations indicate the exact page number.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
