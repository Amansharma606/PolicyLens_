import React, { useState, useEffect, useRef } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import {
  Bot,
  Copy,
  Trash2,
  PlusCircle,
  ChevronDown,
  FileText,
  Sparkles,
  Check,
  ArrowUp,
  ShieldCheck,
  FileSearch,
  Scale,
  CalendarClock,
  RefreshCw
} from 'lucide-react';
import { getDocuments, askQuestionStream, getDocumentHistory, getDocumentStatus } from '../services/api';
import { useToast } from '../context/ToastContext';

const STARTER_PROMPTS = [
  {
    icon: ShieldCheck,
    title: "Coverage & Scope",
    subtitle: "What benefits, expenses, or events are covered?",
    prompt: "What expenses and benefits are covered under this policy?"
  },
  {
    icon: CalendarClock,
    title: "Waiting Periods",
    subtitle: "What waiting periods apply before benefits become payable?",
    prompt: "What are the waiting periods mentioned in this policy?"
  },
  {
    icon: Scale,
    title: "Exclusions & Limits",
    subtitle: "What is excluded, capped, or subject to deductibles/co-pay?",
    prompt: "What are the main exclusions and financial limits in this policy?"
  },
  {
    icon: FileSearch,
    title: "Claims & Documents",
    subtitle: "How do I file a claim and what documents are required?",
    prompt: "How do I file a claim and what documents are required?"
  }
];

const QUICK_SUGGESTIONS = [
  "What is covered in this policy?",
  "What are the exclusions?",
  "What is the waiting period?",
  "Kya is policy mein dental cover hai?",
  "Claim ke liye kaunse documents chahiye?"
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
  const [copiedId, setCopiedId] = useState(null);

  const messagesContainerRef = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const shouldAutoScrollRef = useRef(true);

  const navigate = useNavigate();
  const toast = useToast();

  const handleScroll = () => {
    const container = messagesContainerRef.current;
    if (!container) return;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom < 120;
  };

  const scrollToBottom = (force = false) => {
    if (force || shouldAutoScrollRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  };

  useEffect(() => {
    scrollToBottom(false);
  }, [messages, loading]);

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
  const isDocReady =
    !selectedDocId ||
    (activeDoc && ['chat_ready', 'completed', 'ready'].includes(activeDoc.status));
  const isEnriching = activeDoc && activeDoc.status === 'chat_ready';
  const isProcessing = activeDoc && ['processing', 'pending'].includes(activeDoc.status);
  const isFailed = activeDoc && activeDoc.status === 'failed';

  // Poll status if active document is processing or enriching in Stage 2
  useEffect(() => {
    if (!selectedDocId || (!isProcessing && !isEnriching)) return;

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
                  total_words: statusResp.total_words || d.total_words,
                }
              : d
          )
        );
        if (statusResp.status === 'failed') {
          toast.error("Document indexing failed: " + (statusResp.error_message || 'Unknown error'));
        }
      } catch (err) {
        console.error("Status polling error:", err);
      }
    }, 1800);

    return () => clearInterval(interval);
  }, [selectedDocId, isProcessing, isEnriching]);

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

    const userMsgId = Date.now();
    const botMsgId = userMsgId + 1;

    setMessages((prev) => [
      ...prev,
      {
        id: userMsgId,
        role: 'user',
        content: questionText,
        timestamp: new Date().toISOString()
      },
      {
        id: botMsgId,
        role: 'assistant',
        content: '',
        isStreaming: true,
        timestamp: new Date().toISOString()
      }
    ]);
    setLoading(true);
    setTimeout(() => scrollToBottom(true), 40);

    let activeConvId = conversationId;

    try {
      await askQuestionStream(selectedDocId, questionText, activeConvId, {
        onMeta: (meta) => {
          if (!activeConvId && meta.conversation_id) {
            activeConvId = meta.conversation_id;
            setConversationId(meta.conversation_id);
            setSearchParams({ conversation: meta.conversation_id });
          }
          setMessages((prev) =>
            prev.map((m) => (m.id === botMsgId ? { ...m, topic: meta.topic || m.topic } : m))
          );
        },
        onToken: (token) => {
          setMessages((prev) =>
            prev.map((m) => (m.id === botMsgId ? { ...m, content: (m.content || '') + token } : m))
          );
        },
        onDone: (finalData) => {
          if (!activeConvId && finalData.conversation_id) {
            activeConvId = finalData.conversation_id;
            setConversationId(finalData.conversation_id);
            setSearchParams({ conversation: finalData.conversation_id });
          }
          setMessages((prev) =>
            prev.map((m) =>
              m.id === botMsgId
                ? {
                    ...m,
                    content: finalData.answer ?? m.content,
                    topic: finalData.topic || m.topic,
                    status: finalData.status,
                    isStreaming: false
                  }
                : m
            )
          );
        },
        onError: (err) => {
          throw err;
        }
      });

      // Guarantee streaming flag cleared even if stream ended cleanly
      setMessages((prev) =>
        prev.map((m) => (m.id === botMsgId ? { ...m, isStreaming: false } : m))
      );
    } catch (err) {
      console.error("Streaming chat error:", err);
      const errDetail = err.message || "Error connecting to QA service.";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === botMsgId
            ? {
                ...m,
                content: m.content || `Unable to answer: ${errDetail}`,
                status: 'error',
                isStreaming: false
              }
            : m
        )
      );
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

  // Render inline *(Page X)* / (Page X) badges + **bold** nicely
  const renderPageBadges = (subText, baseKey) => {
    const pageRegex = /\*?\((Pages?\s+\d+(?:[\s,&\-]+\d+)*)\)\*?/gi;
    const subParts = [];
    let lastIdx = 0;
    let pMatch;
    let innerKey = 0;

    while ((pMatch = pageRegex.exec(subText)) !== null) {
      if (pMatch.index > lastIdx) {
        subParts.push(subText.substring(lastIdx, pMatch.index));
      }
      subParts.push(
        <span
          key={`${baseKey}-p-${innerKey++}`}
          className="inline-flex items-center px-1.5 py-0.5 mx-0.5 rounded-md text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-200/70 align-baseline"
        >
          {pMatch[1]}
        </span>
      );
      lastIdx = pMatch.index + pMatch[0].length;
    }

    if (lastIdx < subText.length) {
      subParts.push(subText.substring(lastIdx));
    }

    return subParts.length > 0 ? subParts : subText;
  };

  const parseInlineFormatting = (text) => {
    const parts = [];
    const boldRegex = /\*\*(.*?)\*\*/g;
    let lastIndex = 0;
    let match;
    let keyIdx = 0;

    while ((match = boldRegex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(renderPageBadges(text.substring(lastIndex, match.index), keyIdx++));
      }
      parts.push(
        <strong key={keyIdx++} className="font-semibold text-slate-950">
          {renderPageBadges(match[1], `b-${keyIdx}`)}
        </strong>
      );
      lastIndex = match.index + match[0].length;
    }

    if (lastIndex < text.length) {
      parts.push(renderPageBadges(text.substring(lastIndex), keyIdx++));
    }

    return parts.length > 0 ? parts : text;
  };

  const renderFormattedContent = (content, isStreaming = false) => {
    if (!content) return null;
    const lines = content.split('\n');

    return (
      <div className="space-y-2.5 text-slate-800 text-sm sm:text-[15px] leading-relaxed">
        {lines.map((line, idx) => {
          const trimmed = line.trim();
          const isLastLine = idx === lines.length - 1;
          if (!trimmed) {
            return <div key={idx} className="h-1.5" />;
          }

          if (trimmed.startsWith('### ') || trimmed.startsWith('## ')) {
            const headerText = trimmed.replace(/^#{2,3}\s+/, '').trim();
            return (
              <h4 key={idx} className="font-bold text-slate-950 text-base pt-2 first:pt-0 pb-0.5">
                {headerText}
              </h4>
            );
          }

          // Bullet items (-, •, *) or numbered lists (1.)
          if (trimmed.startsWith('- ') || trimmed.startsWith('• ') || trimmed.startsWith('* ')) {
            const bulletText = trimmed.slice(2);
            return (
              <div key={idx} className="flex items-start gap-2.5 pl-1 py-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0 mt-2.5" />
                <div className="flex-1">
                  {parseInlineFormatting(bulletText)}
                  {isStreaming && isLastLine && (
                    <span className="inline-block w-1.5 h-4 ml-1 bg-slate-700 animate-pulse align-middle rounded-xs" />
                  )}
                </div>
              </div>
            );
          }

          const numMatch = trimmed.match(/^(\d+\.)\s+(.*)$/);
          if (numMatch) {
            return (
              <div key={idx} className="flex items-start gap-2 pl-1 py-0.5">
                <span className="font-semibold text-slate-700 shrink-0">{numMatch[1]}</span>
                <div className="flex-1">
                  {parseInlineFormatting(numMatch[2])}
                  {isStreaming && isLastLine && (
                    <span className="inline-block w-1.5 h-4 ml-1 bg-slate-700 animate-pulse align-middle rounded-xs" />
                  )}
                </div>
              </div>
            );
          }

          return (
            <p key={idx} className="leading-relaxed">
              {parseInlineFormatting(trimmed)}
              {isStreaming && isLastLine && (
                <span className="inline-block w-1.5 h-4 ml-1 bg-slate-700 animate-pulse align-middle rounded-xs" />
              )}
            </p>
          );
        })}
      </div>
    );
  };

  return (
    <div className="chat-page flex flex-col h-full min-h-0 w-full bg-white overflow-hidden animate-fadeIn">
      {/* 1. Active Policy Header */}
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
                  {isEnriching && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200 shrink-0">
                      <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                      Chat Active • Enriching ({activeDoc.processing_progress || 40}%)
                    </span>
                  )}
                  {isProcessing && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200 shrink-0">
                      <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                      Extracting ({activeDoc.processing_progress || 0}%)
                    </span>
                  )}
                </div>
              )}
            </div>

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

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={startNewConversation}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200/80 text-slate-700 text-xs font-semibold transition-colors border border-slate-200/70 shadow-2xs cursor-pointer"
            title="Start fresh conversation"
          >
            <PlusCircle className="w-3.5 h-3.5 text-blue-600" />
            <span className="hidden sm:inline">New Chat</span>
          </button>
          <button
            onClick={() => setMessages([])}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-rose-50 text-slate-600 hover:text-rose-600 text-xs font-semibold transition-colors border border-slate-200/70 shadow-2xs cursor-pointer"
            title="Clear messages in view"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Clear</span>
          </button>
        </div>
      </div>

      {/* 2. Conversation Area */}
      <div
        ref={messagesContainerRef}
        onScroll={handleScroll}
        className="chat-messages flex-1 min-h-0 overflow-y-auto overflow-x-hidden chat-scroll"
      >
        <div className="w-full max-w-4xl lg:max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-7">
          {messages.length === 0 ? (
            <div className="py-8 sm:py-16 flex flex-col items-center justify-center text-center space-y-6">
              <div className="w-16 h-16 rounded-3xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-500 shadow-sm">
                <Bot className="w-8 h-8" />
              </div>

              <div className="max-w-xl space-y-2">
                <h3 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
                  Ask anything about this policy
                </h3>
                <p className="text-sm text-slate-500 leading-relaxed">
                  Currently reading <span className="font-semibold text-slate-700">{activeDoc?.filename || 'the policy'}</span> ({activeDoc?.total_pages || 0} pages). Ask in English, Hindi, or Hinglish — answers stream live with inline page numbers.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 w-full pt-4">
                {STARTER_PROMPTS.map((item, idx) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={idx}
                      onClick={() => handleSendQuestion(item.prompt)}
                      disabled={loading || !selectedDocId || !isDocReady}
                      className="p-4 rounded-2xl bg-slate-50/80 hover:bg-slate-50 border border-slate-200/80 hover:border-amber-400 text-left transition-all group shadow-2xs hover:shadow-sm disabled:opacity-50 cursor-pointer"
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
            messages.map((msg, index) => {
              const isUser = msg.role === 'user';
              return (
                <div key={msg.id || index} className="w-full">
                  {isUser ? (
                    <div className="flex flex-col items-end max-w-[85%] sm:max-w-[75%] ml-auto">
                      <div className="bg-blue-600 text-white rounded-3xl rounded-br-lg px-5 py-3.5 text-sm sm:text-[15px] leading-relaxed shadow-sm font-normal break-words whitespace-pre-wrap">
                        {msg.content}
                      </div>
                      <span className="text-[10px] text-slate-400 mt-1 px-2 font-mono">
                        {new Date(msg.timestamp || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-start gap-3.5 sm:gap-4 w-full">
                      <div className="w-8 h-8 rounded-xl bg-slate-900 text-amber-400 border border-slate-800 flex items-center justify-center shrink-0 shadow-xs mt-0.5">
                        <Bot className="w-4 h-4" />
                      </div>

                      <div className="flex-1 min-w-0 space-y-2.5">
                        <div className="flex items-center justify-between pb-1 border-b border-slate-100 gap-2 flex-wrap">
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200/60 uppercase tracking-wider shrink-0">
                            <Sparkles className="w-3 h-3 text-amber-600" />
                            {msg.topic ? msg.topic.replace(/_/g, ' ') : 'PolicyLens AI'}
                          </span>
                          {!msg.isStreaming && msg.content && (
                            <button
                              onClick={() => copyToClipboard(msg.content, msg.id || index)}
                              className="inline-flex items-center gap-1.5 text-slate-400 hover:text-slate-700 text-xs transition-colors py-1 px-2 rounded-lg hover:bg-slate-100 shrink-0 cursor-pointer"
                              title="Copy answer"
                            >
                              {copiedId === (msg.id || index) ? (
                                <Check className="w-3.5 h-3.5 text-emerald-600" />
                              ) : (
                                <Copy className="w-3.5 h-3.5" />
                              )}
                              <span className="text-[11px] font-medium">
                                {copiedId === (msg.id || index) ? 'Copied' : 'Copy'}
                              </span>
                            </button>
                          )}
                        </div>

                        {msg.isStreaming && !msg.content ? (
                          <div className="flex items-center gap-2 py-1.5">
                            <span className="w-2 h-2 rounded-full bg-amber-500 animate-bounce" />
                            <span className="w-2 h-2 rounded-full bg-amber-500 animate-bounce [animation-delay:0.2s]" />
                            <span className="w-2 h-2 rounded-full bg-amber-500 animate-bounce [animation-delay:0.4s]" />
                            <span className="text-xs text-slate-500 font-medium ml-1">Reading policy clauses...</span>
                          </div>
                        ) : (
                          renderFormattedContent(msg.content, Boolean(msg.isStreaming))
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* 3. Composer */}
      <div className="chat-footer shrink-0 w-full bg-gradient-to-t from-white via-white/95 to-transparent pt-2 pb-4 sm:pb-5 px-4 sm:px-6 lg:px-8 z-10">
        <div className="max-w-4xl lg:max-w-5xl mx-auto w-full space-y-2">
          {messages.length > 0 && isDocReady && (
            <div className="flex items-center gap-1.5 overflow-x-auto py-1 chat-scroll text-xs">
              <span className="text-slate-400 font-medium text-[11px] shrink-0 mr-1">Suggestions:</span>
              {QUICK_SUGGESTIONS.map((sq, i) => (
                <button
                  key={i}
                  onClick={() => handleSendQuestion(sq)}
                  disabled={loading || !selectedDocId || !isDocReady}
                  className="px-3 py-1 rounded-full bg-slate-100 hover:bg-slate-200/80 text-slate-700 text-xs font-medium shrink-0 transition-colors border border-slate-200/60 disabled:opacity-50 whitespace-nowrap shadow-2xs cursor-pointer"
                >
                  {sq}
                </button>
              ))}
            </div>
          )}

          {isProcessing && (
            <div className="flex items-center gap-2.5 px-4 py-2.5 rounded-2xl bg-amber-50 border border-amber-200/80 text-amber-900 text-xs sm:text-sm">
              <RefreshCw className="w-4 h-4 text-amber-600 animate-spin shrink-0" />
              <div className="flex-1 min-w-0">
                <span className="font-semibold text-amber-950">Extracting document: </span>
                <span className="text-amber-800">{activeDoc?.processing_stage || 'Parsing PDF text...'}</span>
              </div>
            </div>
          )}

          {isFailed && (
            <div className="flex items-center gap-2.5 px-4 py-2.5 rounded-2xl bg-rose-50 border border-rose-200/80 text-rose-800 text-xs sm:text-sm">
              <span className="font-semibold">Processing Failed: </span>
              <span>{activeDoc?.processing_stage || 'An error occurred while indexing this document.'}</span>
            </div>
          )}

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
                  ? "Parsing PDF... Chat will unlock in a couple seconds"
                  : isFailed
                  ? "Document processing failed. Please re-upload or select another policy."
                  : "Ask in English, Hindi, or Hinglish (Enter to send)..."
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
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <ArrowUp className="w-5 h-5 stroke-[2.5]" />
              )}
            </button>
          </div>

          <div className="flex items-center justify-between text-[11px] text-slate-400 px-2">
            <span className="truncate">PolicyLens answers strictly from the uploaded PDF with inline page citations.</span>
            <span className="hidden sm:inline shrink-0 ml-2">Shift + Enter for new line</span>
          </div>
        </div>
      </div>
    </div>
  );
};
