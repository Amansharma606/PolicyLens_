import React, { useState, useEffect, useRef } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { 
  Bot, 
  User, 
  Copy, 
  Trash2, 
  PlusCircle, 
  ChevronDown, 
  ChevronUp, 
  BookOpen, 
  FileText, 
  Sparkles, 
  Check,
  ArrowUp,
  ShieldCheck,
  HelpCircle,
  FileSearch,
  Scale,
  CalendarClock,
  RefreshCw
} from 'lucide-react';
import { getDocuments, askQuestion, getDocumentHistory, getDocumentStatus } from '../services/api';
import { useToast } from '../context/ToastContext';

const STARTER_PROMPTS = [
  {
    icon: ShieldCheck,
    title: "Coverage & Scope",
    subtitle: "What hospital expenses, room rent, and surgeries are covered?",
    prompt: "What expenses and treatments are covered under this policy?"
  },
  {
    icon: CalendarClock,
    title: "Waiting Periods",
    subtitle: "What is the waiting period for specific illnesses and PED?",
    prompt: "What are the waiting periods for pre-existing diseases and specific illnesses?"
  },
  {
    icon: Scale,
    title: "Permanent Exclusions",
    subtitle: "List all treatments, cosmetic care, and exclusions in this policy.",
    prompt: "What are the permanent exclusions in this policy?"
  },
  {
    icon: FileSearch,
    title: "Claim Process & Filing",
    subtitle: "What documents and notice periods are required for claims?",
    prompt: "What documents are required to file a reimbursement or cashless claim?"
  }
];

const QUICK_SUGGESTIONS = [
  "What is this policy about?",
  "What is the waiting period?",
  "What are the exclusions?",
  "What documents are required to file a claim?",
  "Does this policy cover maternity?"
];

export const ChatPage = () => {
  const { documentId: routeDocId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryConvId = searchParams.get('conversation');

  const [documents, setDocuments] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState(routeDocId || '');
  const [conversationId, setConversationId] = useState(queryConvId || null);
  const [messages, setMessages] = useState([]);
  const [inputQuestion, setInputQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [expandedSources, setExpandedSources] = useState({});
  const [copiedId, setCopiedId] = useState(null);

  const messagesContainerRef = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const shouldAutoScrollRef = useRef(true);

  const navigate = useNavigate();
  const toast = useToast();

  // Handle user scroll to detect if they scrolled up to read older messages
  const handleScroll = () => {
    const container = messagesContainerRef.current;
    if (!container) return;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom < 120;
  };

  // Scroll to bottom of message stream
  const scrollToBottom = (force = false) => {
    if (force || shouldAutoScrollRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  };

  useEffect(() => {
    scrollToBottom(false);
  }, [messages, loading]);

  // Keep routeDocId and queryConvId in sync if URL changes
  useEffect(() => {
    if (routeDocId && routeDocId !== selectedDocId) {
      setSelectedDocId(routeDocId);
    }
  }, [routeDocId]);

  useEffect(() => {
    if (queryConvId !== conversationId) {
      setConversationId(queryConvId || null);
    }
  }, [queryConvId]);

  // Load documents list
  useEffect(() => {
    const fetchDocs = async () => {
      try {
        setLoadingDocs(true);
        const docs = await getDocuments();
        setDocuments(docs || []);

        if (routeDocId) {
          setSelectedDocId(routeDocId);
        } else if (docs && docs.length > 0 && !selectedDocId) {
          setSelectedDocId(docs[0].id);
        }
      } catch (err) {
        console.error("Failed to fetch documents:", err);
        toast.error("Could not load documents list.");
      } finally {
        setLoadingDocs(false);
      }
    };
    fetchDocs();
  }, [routeDocId]);

  // Load chat history when selectedDocId or conversationId changes
  useEffect(() => {
    if (!selectedDocId) {
      setMessages([]);
      return;
    }

    const loadHistory = async () => {
      try {
        const historyResp = await getDocumentHistory(selectedDocId, conversationId);
        if (historyResp && historyResp.messages) {
          setMessages(historyResp.messages);
          setTimeout(() => scrollToBottom(true), 100);
        }
      } catch (err) {
        console.error("Error loading chat history:", err);
      }
    };

    loadHistory();
  }, [selectedDocId, conversationId]);

  const activeDoc = documents.find((d) => d.id === selectedDocId);
  const isDocReady = !selectedDocId || (activeDoc && (activeDoc.status === 'completed' || activeDoc.status === 'ready'));
  const isProcessing = activeDoc && (activeDoc.status === 'processing' || activeDoc.status === 'pending');
  const isFailed = activeDoc && activeDoc.status === 'failed';

  // Poll status if active document is still processing
  useEffect(() => {
    if (!selectedDocId || !isProcessing) return;

    const interval = setInterval(async () => {
      try {
        const statusResp = await getDocumentStatus(selectedDocId);
        setDocuments((prev) =>
          prev.map((d) =>
            d.id === selectedDocId
              ? {
                  ...d,
                  status: statusResp.status,
                  processing_stage: statusResp.processing_stage,
                  processing_progress: statusResp.processing_progress,
                  total_pages: statusResp.total_pages || d.total_pages,
                  total_clauses: statusResp.total_clauses || d.total_clauses,
                }
              : d
          )
        );
        if (statusResp.status === 'completed' || statusResp.status === 'ready') {
          toast.success("Document indexing complete! You can now ask questions.");
        } else if (statusResp.status === 'failed') {
          toast.error("Document indexing failed: " + (statusResp.error_message || 'Unknown error'));
        }
      } catch (err) {
        console.error("Status polling error:", err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [selectedDocId, isProcessing]);

  const handleDocumentChange = (newDocId) => {
    setSelectedDocId(newDocId);
    setConversationId(null);
    setMessages([]);
    navigate(`/chat/${newDocId}`);
  };

  const startNewConversation = () => {
    setConversationId(null);
    setMessages([]);
    setSearchParams({});
    toast.info("Started new conversation.");
    if (inputRef.current) {
      inputRef.current.focus();
    }
  };

  const handleSendQuestion = async (overrideText) => {
    const questionText = (overrideText || inputQuestion).trim();
    if (!questionText || !selectedDocId || loading) return;

    setInputQuestion('');
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }

    shouldAutoScrollRef.current = true;

    // Append user message to UI
    const tempUserMsg = {
      id: Date.now(),
      role: 'user',
      content: questionText,
      timestamp: new Date().toISOString()
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setLoading(true);

    setTimeout(() => scrollToBottom(true), 50);

    try {
      const response = await askQuestion(selectedDocId, questionText, conversationId);
      
      if (!conversationId && response.conversation_id) {
        setConversationId(response.conversation_id);
        setSearchParams({ conversation: response.conversation_id });
      }

      const botMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.answer,
        topic: response.topic,
        sources: response.sources || [],
        status: response.status,
        timestamp: new Date().toISOString()
      };

      setMessages((prev) => [...prev, botMsg]);
    } catch (err) {
      console.error("Failed to answer question:", err);
      const errDetail = err.response?.data?.detail || "Error connecting to QA service.";
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: 'assistant',
          content: `Unable to answer: ${errDetail}`,
          status: 'error',
          sources: [],
          timestamp: new Date().toISOString()
        }
      ]);
      toast.error(errDetail);
    } finally {
      setLoading(false);
      setTimeout(() => scrollToBottom(true), 50);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendQuestion();
    }
  };

  const copyToClipboard = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast.success("Answer copied to clipboard!");
    setTimeout(() => setCopiedId(null), 2000);
  };

  const toggleSourceExpand = (sourceKey) => {
    setExpandedSources((prev) => ({
      ...prev,
      [sourceKey]: !prev[sourceKey]
    }));
  };

  // Modern Markdown & Citations Parser
  const parseInlineFormatting = (text) => {
    const parts = [];
    const boldRegex = /\*\*(.*?)\*\*/g;
    let lastIndex = 0;
    let match;
    let keyIdx = 0;

    while ((match = boldRegex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(renderCitations(text.substring(lastIndex, match.index), keyIdx++));
      }
      parts.push(
        <strong key={keyIdx++} className="font-semibold text-slate-950">
          {match[1]}
        </strong>
      );
      lastIndex = match.index + match[0].length;
    }

    if (lastIndex < text.length) {
      parts.push(renderCitations(text.substring(lastIndex), keyIdx++));
    }

    return parts.length > 0 ? parts : text;
  };

  const renderCitations = (subText, baseKey) => {
    const citationRegex = /\*\((Source:.*?)\)\*/g;
    const subParts = [];
    let lastIdx = 0;
    let cMatch;
    let innerKey = 0;

    while ((cMatch = citationRegex.exec(subText)) !== null) {
      if (cMatch.index > lastIdx) {
        subParts.push(subText.substring(lastIdx, cMatch.index));
      }
      subParts.push(
        <span
          key={`${baseKey}-c-${innerKey++}`}
          className="inline-flex items-center px-2 py-0.5 mx-1 rounded text-xs font-mono font-medium bg-blue-50 text-blue-700 border border-blue-200/60 shadow-2xs"
        >
          {cMatch[1]}
        </span>
      );
      lastIdx = cMatch.index + cMatch[0].length;
    }

    if (lastIdx < subText.length) {
      subParts.push(subText.substring(lastIdx));
    }

    return subParts.length > 0 ? subParts : subText;
  };

  const renderFormattedContent = (content) => {
    if (!content) return null;
    const lines = content.split('\n');

    return (
      <div className="space-y-2.5 text-slate-800 text-sm sm:text-[15px] leading-relaxed">
        {lines.map((line, idx) => {
          const trimmed = line.trim();
          if (!trimmed) {
            return <div key={idx} className="h-2" />;
          }

          // Section header like ### Direct Answer or **Coverage Determination:**
          if (trimmed.startsWith('### ')) {
            const headerText = trimmed.slice(4).trim();
            return (
              <h4 key={idx} className="font-bold text-slate-900 text-base sm:text-lg pt-3 first:pt-0 pb-1 text-slate-950 border-b border-slate-100 flex items-center gap-2">
                <span className="w-1.5 h-4 rounded-full bg-amber-500 shrink-0" />
                <span>{headerText}</span>
              </h4>
            );
          }

          if (trimmed.startsWith('**') && trimmed.endsWith('**') && !trimmed.slice(2, -2).includes('**')) {
            const headerText = trimmed.slice(2, -2);
            return (
              <h4 key={idx} className="font-bold text-slate-900 text-base sm:text-lg pt-3 first:pt-0 pb-1 text-slate-950 border-b border-slate-100 flex items-center gap-2">
                <span className="w-1.5 h-4 rounded-full bg-amber-500 shrink-0" />
                <span>{headerText}</span>
              </h4>
            );
          }

          // Bullet items
          if (trimmed.startsWith('- ') || trimmed.startsWith('• ')) {
            const bulletText = trimmed.slice(2);
            return (
              <div key={idx} className="flex items-start gap-3 pl-1.5 py-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0 mt-2.5 shadow-xs" />
                <div className="flex-1">
                  {parseInlineFormatting(bulletText)}
                </div>
              </div>
            );
          }

          // Standard paragraph
          return (
            <p key={idx} className="leading-relaxed">
              {parseInlineFormatting(trimmed)}
            </p>
          );
        })}
      </div>
    );
  };

  return (
    <div className="chat-page flex flex-col h-full min-h-0 w-full bg-white overflow-hidden animate-fadeIn">
      {/* 1. Full-Width Active Policy Header */}
      <div className="chat-header shrink-0 bg-white/95 backdrop-blur-md border-b border-slate-200/80 px-4 sm:px-6 lg:px-8 py-2.5 sm:py-3 flex items-center justify-between gap-3 z-10 shadow-2xs">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-600 shadow-2xs shrink-0">
            <FileText className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-amber-600 font-bold uppercase tracking-wider">Active Policy</span>
              {activeDoc && (
                <div className="flex items-center gap-1.5">
                  <span className="px-2 py-0.5 rounded text-[10px] bg-slate-100 text-slate-600 font-mono font-medium border border-slate-200/60 shrink-0">
                    {activeDoc.total_pages} {activeDoc.total_pages === 1 ? 'Page' : 'Pages'}
                  </span>
                  {activeDoc.status === 'processing' && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200 shrink-0">
                      <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                      Indexing ({activeDoc.processing_progress || 0}%)
                    </span>
                  )}
                </div>
              )}
            </div>
            
            {/* Document Switcher Dropdown */}
            <div className="relative flex items-center max-w-full">
              <select
                value={selectedDocId}
                onChange={(e) => handleDocumentChange(e.target.value)}
                disabled={loadingDocs || documents.length === 0}
                title={activeDoc?.filename || 'Select Policy Document'}
                className="bg-transparent text-slate-900 font-bold text-sm sm:text-base cursor-pointer focus:outline-none hover:text-amber-600 transition-colors pr-6 truncate max-w-[220px] sm:max-w-md md:max-w-xl appearance-none"
              >
                {documents.length === 0 ? (
                  <option value="">No documents uploaded yet</option>
                ) : (
                  documents.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.filename}
                    </option>
                  ))
                )}
              </select>
              <ChevronDown className="w-4 h-4 text-slate-400 absolute right-0 pointer-events-none" />
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={startNewConversation}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200/80 text-slate-700 text-xs font-semibold transition-colors border border-slate-200/70 shadow-2xs"
            title="Start fresh conversation"
          >
            <PlusCircle className="w-3.5 h-3.5 text-blue-600" />
            <span className="hidden sm:inline">New Chat</span>
          </button>
          <button
            onClick={() => setMessages([])}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-rose-50 text-slate-600 hover:text-rose-600 text-xs font-semibold transition-colors border border-slate-200/70 shadow-2xs"
            title="Clear messages in view"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Clear</span>
          </button>
        </div>
      </div>

      {/* 2. Full-Screen Scrollable Conversation Area */}
      <div 
        ref={messagesContainerRef}
        onScroll={handleScroll}
        className="chat-messages flex-1 min-h-0 overflow-y-auto overflow-x-hidden chat-scroll"
      >
        <div className="w-full max-w-4xl lg:max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-7">
          {messages.length === 0 ? (
            /* Modern ChatGPT-style Empty / Welcome State */
            <div className="py-8 sm:py-16 flex flex-col items-center justify-center text-center space-y-6">
              <div className="w-16 h-16 rounded-3xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-500 shadow-sm">
                <Bot className="w-8 h-8" />
              </div>

              <div className="max-w-xl space-y-2">
                <h3 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
                  How can PolicyLens help you understand this policy?
                </h3>
                <p className="text-sm text-slate-500 leading-relaxed">
                  Currently analyzing <span className="font-semibold text-slate-700">{activeDoc?.filename || 'the policy'}</span> ({activeDoc?.total_pages || 0} pages). Ask questions in natural language — every answer is verified with citations from the document.
                </p>
              </div>

              {/* Starter Prompt Cards in a 2x2 Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 w-full pt-4">
                {STARTER_PROMPTS.map((item, idx) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={idx}
                      onClick={() => handleSendQuestion(item.prompt)}
                      disabled={loading || !selectedDocId}
                      className="p-4 rounded-2xl bg-slate-50/80 hover:bg-slate-50 border border-slate-200/80 hover:border-amber-400 text-left transition-all group shadow-2xs hover:shadow-sm disabled:opacity-50"
                    >
                      <div className="flex items-center gap-3 mb-1.5">
                        <div className="w-8 h-8 rounded-xl bg-white border border-slate-200/80 flex items-center justify-center text-slate-600 group-hover:text-amber-500 group-hover:border-amber-400 transition-colors shadow-2xs">
                          <Icon className="w-4 h-4" />
                        </div>
                        <span className="font-semibold text-sm text-slate-800 group-hover:text-slate-950 transition-colors">
                          {item.title}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 leading-relaxed pl-1">
                        {item.subtitle}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            /* Active Conversation Messages */
            messages.map((msg, index) => {
              const isUser = msg.role === 'user';
              return (
                <div key={msg.id || index} className="w-full">
                  {isUser ? (
                    /* User Message: Right Aligned Bubble */
                    <div className="flex flex-col items-end max-w-[85%] sm:max-w-[75%] ml-auto">
                      <div className="bg-blue-600 text-white rounded-3xl rounded-br-lg px-5 py-3.5 text-sm sm:text-[15px] leading-relaxed shadow-sm font-normal break-words whitespace-pre-wrap">
                        {msg.content}
                      </div>
                      <span className="text-[10px] text-slate-400 mt-1 px-2 font-mono">
                        {new Date(msg.timestamp || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  ) : (
                    /* Assistant Message: Left Aligned Modern AI Response */
                    <div className="flex items-start gap-3.5 sm:gap-4 w-full">
                      {/* Avatar */}
                      <div className="w-8 h-8 rounded-xl bg-slate-900 text-amber-400 border border-slate-800 flex items-center justify-center shrink-0 shadow-xs mt-0.5">
                        <Bot className="w-4 h-4" />
                      </div>

                      {/* Content Body */}
                      <div className="flex-1 min-w-0 space-y-3.5">
                        {/* Topic Tag & Copy Control */}
                        <div className="flex items-center justify-between pb-1.5 border-b border-slate-100 gap-2 flex-wrap">
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200/60 uppercase tracking-wider shrink-0">
                            <Sparkles className="w-3 h-3 text-amber-600" />
                            {msg.topic ? msg.topic.replace(/_/g, ' ') : 'Policy Analysis'}
                          </span>
                          <button
                            onClick={() => copyToClipboard(msg.content, msg.id || index)}
                            className="inline-flex items-center gap-1.5 text-slate-400 hover:text-slate-700 text-xs transition-colors py-1 px-2 rounded-lg hover:bg-slate-100 shrink-0"
                            title="Copy answer"
                          >
                            {copiedId === (msg.id || index) ? (
                              <Check className="w-3.5 h-3.5 text-emerald-600" />
                            ) : (
                              <Copy className="w-3.5 h-3.5" />
                            )}
                            <span className="text-[11px] font-medium">
                              {copiedId === (msg.id || index) ? 'Copied' : 'Copy response'}
                            </span>
                          </button>
                        </div>

                        {/* Rich Formatted Markdown Text */}
                        {renderFormattedContent(msg.content)}

                        {/* Supporting Policy Evidence Tray */}
                        {!isUser && msg.sources && msg.sources.length > 0 && (
                          <div className="mt-4 pt-3 border-t border-slate-100 space-y-3">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2 text-xs font-bold text-slate-700">
                                <BookOpen className="w-4 h-4 text-amber-600 shrink-0" />
                                <span>Supporting Document Evidence ({msg.sources.length} citations)</span>
                              </div>
                              <span className="text-[11px] font-medium text-slate-400">
                                Grounded Citations
                              </span>
                            </div>

                            <div className="grid grid-cols-1 gap-2.5">
                              {msg.sources.map((src, sIdx) => {
                                const sourceKey = `${msg.id || index}-src-${sIdx}`;
                                const isExpanded = expandedSources[sourceKey];
                                return (
                                  <div
                                    key={sIdx}
                                    className="rounded-xl bg-slate-50/80 hover:bg-slate-50 border border-slate-200/80 p-3.5 text-xs text-slate-700 space-y-2 transition-colors"
                                  >
                                    <div className="flex items-center justify-between font-semibold gap-2 flex-wrap">
                                      <div className="flex items-center gap-2 shrink-0">
                                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md bg-blue-100 text-blue-800 font-mono text-xs font-bold border border-blue-200/70">
                                          Page {src.page}
                                        </span>
                                        {src.section_name && (
                                          <span className="text-xs text-slate-500 font-medium truncate max-w-[260px]" title={src.section_name}>
                                            {src.section_name}
                                          </span>
                                        )}
                                      </div>
                                      {src.relevance_score && (
                                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200/60 shrink-0">
                                          {(src.relevance_score * 100).toFixed(0)}% relevance
                                        </span>
                                      )}
                                    </div>

                                    <p className={`text-slate-700 font-mono text-xs leading-relaxed break-words bg-white p-3 rounded-lg border border-slate-200/70 ${isExpanded ? '' : 'line-clamp-2'}`}>
                                      "{src.text}"
                                    </p>

                                    {src.text.length > 130 && (
                                      <button
                                        onClick={() => toggleSourceExpand(sourceKey)}
                                        className="text-xs font-semibold text-amber-700 hover:text-amber-900 flex items-center gap-1 pt-0.5 transition-colors cursor-pointer"
                                      >
                                        {isExpanded ? (
                                          <>
                                            <span>Show less</span>
                                            <ChevronUp className="w-3.5 h-3.5" />
                                          </>
                                        ) : (
                                          <>
                                            <span>Read full supporting clause</span>
                                            <ChevronDown className="w-3.5 h-3.5" />
                                          </>
                                        )}
                                      </button>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}

          {/* Assistant Generating State */}
          {loading && (
            <div className="flex items-start gap-3.5 sm:gap-4 w-full animate-pulse">
              <div className="w-8 h-8 rounded-xl bg-slate-900 text-amber-400 border border-slate-800 flex items-center justify-center shrink-0 shadow-xs">
                <Bot className="w-4 h-4" />
              </div>
              <div className="space-y-2 pt-1">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 animate-bounce"></span>
                  <span className="w-2 h-2 rounded-full bg-amber-500 animate-bounce [animation-delay:0.2s]"></span>
                  <span className="w-2 h-2 rounded-full bg-amber-500 animate-bounce [animation-delay:0.4s]"></span>
                  <span className="text-xs text-slate-500 font-medium ml-1">Analyzing policy clauses and synthesizing citations...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* 3. Modern ChatGPT-Style Floating Composer Fixed at Bottom */}
      <div className="chat-footer shrink-0 w-full bg-gradient-to-t from-white via-white/95 to-transparent pt-2 pb-4 sm:pb-5 px-4 sm:px-6 lg:px-8 z-10">
        <div className="max-w-4xl lg:max-w-5xl mx-auto w-full space-y-2">
          {/* Quick suggestions pills when conversation is active and document is ready */}
          {messages.length > 0 && isDocReady && (
            <div className="flex items-center gap-1.5 overflow-x-auto py-1 chat-scroll text-xs">
              <span className="text-slate-400 font-medium text-[11px] shrink-0 mr-1">Suggestions:</span>
              {QUICK_SUGGESTIONS.map((sq, i) => (
                <button
                  key={i}
                  onClick={() => handleSendQuestion(sq)}
                  disabled={loading || !selectedDocId || !isDocReady}
                  className="px-3 py-1 rounded-full bg-slate-100 hover:bg-slate-200/80 text-slate-700 text-xs font-medium shrink-0 transition-colors border border-slate-200/60 disabled:opacity-50 whitespace-nowrap shadow-2xs"
                >
                  {sq}
                </button>
              ))}
            </div>
          )}

          {/* Status banner when document is processing or failed */}
          {isProcessing && (
            <div className="flex items-center gap-2.5 px-4 py-2.5 rounded-2xl bg-amber-50 border border-amber-200/80 text-amber-900 text-xs sm:text-sm">
              <RefreshCw className="w-4 h-4 text-amber-600 animate-spin shrink-0" />
              <div className="flex-1 min-w-0">
                <span className="font-semibold text-amber-950">Policy is being indexed: </span>
                <span className="text-amber-800">{activeDoc?.processing_stage || 'Extracting and embedding clauses...'}</span>
                <span className="ml-1.5 text-amber-600 font-mono font-medium">({activeDoc?.processing_progress || 0}%)</span>
                <span className="hidden sm:inline ml-2 text-xs text-amber-700/80">• Chat will unlock automatically when indexing finishes.</span>
              </div>
            </div>
          )}

          {isFailed && (
            <div className="flex items-center gap-2.5 px-4 py-2.5 rounded-2xl bg-rose-50 border border-rose-200/80 text-rose-800 text-xs sm:text-sm">
              <span className="font-semibold">Processing Failed: </span>
              <span>{activeDoc?.processing_stage || 'An error occurred while indexing this document.'}</span>
            </div>
          )}

          {/* ChatGPT-style floating input box */}
          <div className="relative flex items-end gap-2 bg-slate-50/90 hover:bg-slate-50 focus-within:bg-white border border-slate-200/90 focus-within:border-slate-400 focus-within:ring-4 focus-within:ring-slate-100 rounded-3xl p-2 sm:p-2.5 transition-all shadow-sm">
            <textarea
              ref={inputRef}
              rows={1}
              value={inputQuestion}
              onChange={(e) => {
                setInputQuestion(e.target.value);
                e.target.style.height = 'auto';
                e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
              }}
              onKeyDown={handleKeyDown}
              placeholder={
                !selectedDocId
                  ? "Please select or upload a policy document first"
                  : isProcessing
                  ? `Indexing policy (${activeDoc?.processing_progress || 0}%)... Chat will unlock shortly`
                  : isFailed
                  ? "Document processing failed. Please re-upload or select another policy."
                  : "Ask anything about this policy (Press Enter to send, Shift+Enter for newline)..."
              }
              disabled={!selectedDocId || !isDocReady || loading}
              className="w-full px-3.5 py-1.5 bg-transparent text-sm sm:text-[15px] text-slate-800 placeholder:text-slate-400 focus:outline-none resize-none min-h-[38px] max-h-[160px] leading-relaxed chat-scroll disabled:opacity-50"
            />

            <button
              onClick={() => handleSendQuestion()}
              disabled={!inputQuestion.trim() || !selectedDocId || !isDocReady || loading}
              className="w-9 h-9 sm:w-10 sm:h-10 rounded-full bg-slate-900 hover:bg-slate-800 disabled:opacity-30 disabled:hover:bg-slate-900 text-white flex items-center justify-center transition-all shadow-md shrink-0 mb-0.5 active:scale-95 cursor-pointer disabled:cursor-not-allowed"
              title="Send Question (Enter)"
              aria-label="Send Question"
            >
              {loading ? (
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
              ) : (
                <ArrowUp className="w-5 h-5 stroke-[2.5]" />
              )}
            </button>
          </div>

          {/* Subtle single-line footer text */}
          <div className="flex items-center justify-between text-[11px] text-slate-400 px-2">
            <span className="truncate">PolicyLens AI is grounded strictly on uploaded policy text. Verify all financial sub-limits.</span>
            <span className="hidden sm:inline shrink-0 ml-2">Shift + Enter for new line</span>
          </div>
        </div>
      </div>
    </div>
  );
};
