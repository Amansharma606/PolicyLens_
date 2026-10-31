import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  History, 
  MessageSquare, 
  Clock, 
  ArrowRight, 
  Trash2, 
  FileText, 
  FolderArchive,
  Search
} from 'lucide-react';
import { getConversations, deleteConversation } from '../services/api';
import { useToast } from '../context/ToastContext';

export const ConversationHistory = () => {
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [convToDelete, setConvToDelete] = useState(null);

  const navigate = useNavigate();
  const toast = useToast();

  const loadConversations = async () => {
    try {
      setLoading(true);
      const data = await getConversations();
      setConversations(data);
    } catch (err) {
      console.error('Error fetching conversations:', err);
      toast.error('Could not load conversation history.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConversations();
  }, []);

  const handleDelete = async () => {
    if (!convToDelete) return;
    try {
      await deleteConversation(convToDelete.conversation_id);
      toast.success('Conversation thread deleted.');
      setConversations((prev) => prev.filter((c) => c.conversation_id !== convToDelete.conversation_id));
      setConvToDelete(null);
    } catch (err) {
      toast.error('Failed to delete conversation.');
    }
  };

  // Group conversations by document filename
  const filtered = conversations.filter((c) => {
    const q = searchQuery.toLowerCase();
    const titleMatch = (c.title || '').toLowerCase().includes(q);
    const docMatch = (c.filename || '').toLowerCase().includes(q);
    return titleMatch || docMatch;
  });

  const grouped = filtered.reduce((acc, conv) => {
    const docName = conv.filename || 'General Documents';
    if (!acc[docName]) {
      acc[docName] = [];
    }
    acc[docName].push(conv);
    return acc;
  }, {});

  return (
    <div className="space-y-8 animate-fadeIn max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">Conversation History</h2>
          <p className="text-slate-500 text-sm mt-1">
            Previous question-answer threads grouped by insurance policy document.
          </p>
        </div>

        {/* Search */}
        <div className="relative min-w-[240px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search conversation topics..."
            className="w-full pl-9 pr-4 py-2 rounded-xl bg-white border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 shadow-sm"
          />
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="p-12 text-center text-slate-400 text-sm bg-white rounded-3xl border border-slate-200">
          Loading conversation history...
        </div>
      ) : Object.keys(grouped).length === 0 ? (
        <div className="p-16 text-center space-y-3 bg-white rounded-3xl border border-slate-200/80 shadow-sm">
          <History className="w-12 h-12 text-slate-300 mx-auto" />
          <h3 className="text-base font-bold text-slate-800">No conversation history</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            {searchQuery
              ? `No chats matched "${searchQuery}".`
              : 'Start a conversation with an uploaded policy document to save history.'}
          </p>
          <button
            onClick={() => navigate('/chat')}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 text-white text-xs font-semibold"
          >
            <MessageSquare className="w-4 h-4" />
            <span>Open Chat</span>
          </button>
        </div>
      ) : (
        <div className="space-y-8">
          {Object.entries(grouped).map(([docName, docConvs]) => (
            <div key={docName} className="space-y-4">
              {/* Document Group Header */}
              <div className="flex items-center gap-2.5 px-2">
                <FileText className="w-5 h-5 text-blue-600" />
                <h3 className="text-sm font-bold text-slate-800">{docName}</h3>
                <span className="text-xs text-slate-400">({docConvs.length} threads)</span>
              </div>

              {/* Conversation Cards */}
              <div className="bg-white rounded-3xl border border-slate-200/90 divide-y divide-slate-100 shadow-sm overflow-hidden">
                {docConvs.map((conv) => (
                  <div
                    key={conv.conversation_id}
                    className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-slate-50/70 transition-colors"
                  >
                    <div className="space-y-1 min-w-0">
                      <h4 className="text-sm font-semibold text-slate-900 truncate" title={conv.title}>
                        {conv.title || 'Untitled Conversation'}
                      </h4>
                      <div className="flex items-center gap-3 text-xs text-slate-400">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3.5 h-3.5" />
                          {new Date(conv.updated_at).toLocaleString()}
                        </span>
                        <span>•</span>
                        <span>{conv.message_count || 0} messages</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                      <button
                        onClick={() => navigate(`/chat/${conv.document_id}?conversation=${conv.conversation_id}`)}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs font-semibold transition-colors"
                      >
                        <span>Continue</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => setConvToDelete(conv)}
                        className="p-2 rounded-xl hover:bg-rose-50 text-slate-400 hover:text-rose-600 transition-colors"
                        title="Delete Thread"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {convToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => setConvToDelete(null)} />
          <div className="relative bg-white rounded-3xl max-w-md w-full p-6 z-10 shadow-2xl border border-slate-200 space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-rose-50 text-rose-600 flex items-center justify-center">
              <Trash2 className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-bold text-slate-900 text-base">Delete Conversation Thread?</h3>
              <p className="text-xs text-slate-500 mt-1">
                Are you sure you want to delete <span className="font-semibold text-slate-700">"{convToDelete.title}"</span>? This action cannot be undone.
              </p>
            </div>
            <div className="flex items-center justify-end gap-3 pt-3">
              <button
                onClick={() => setConvToDelete(null)}
                className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-sm"
              >
                Delete Thread
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
