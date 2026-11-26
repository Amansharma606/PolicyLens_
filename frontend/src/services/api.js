import axios from 'axios';

// Base URL points to FastAPI backend
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  headers: {
    'Accept': 'application/json',
  }
});

// Health API
export const checkHealth = async () => {
  const response = await api.get('/api/health');
  return response.data;
};

// Document APIs
export const getDocuments = async () => {
  const response = await api.get('/api/documents');
  return response.data;
};

export const getDocument = async (documentId) => {
  const response = await api.get(`/api/documents/${documentId}`);
  return response.data;
};

export const getDocumentStatus = async (documentId) => {
  const response = await api.get(`/api/documents/${documentId}/status`);
  return response.data;
};

export const getDocumentText = async (documentId) => {
  const response = await api.get(`/api/documents/${documentId}/text`);
  return response.data;
};

export const getDocumentExplanation = async (documentId) => {
  const response = await api.get(`/api/documents/${documentId}/explanation`);
  return response.data;
};

export const uploadDocument = async (file, onUploadProgress) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post('/api/documents/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    timeout: 180000, // 3 minutes for comprehensive insurance policy extraction & embedding
    onUploadProgress: (progressEvent) => {
      if (onUploadProgress && progressEvent.total) {
        const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onUploadProgress(percentCompleted);
      }
    }
  });
  return response.data;
};

export const deleteDocument = async (documentId) => {
  const response = await api.delete(`/api/documents/${documentId}`);
  return response.data;
};

// QA and Chat APIs
export const askQuestion = async (documentId, question, conversationId = null, useBaseline = false) => {
  const payload = { question, use_baseline: useBaseline };
  if (conversationId) {
    payload.conversation_id = conversationId;
  }
  const response = await api.post(`/api/documents/${documentId}/ask`, payload);
  return response.data;
};

export const askQuestionStream = async (
  documentId,
  question,
  conversationId = null,
  { onMeta, onToken, onDone, onError } = {}
) => {
  const payload = { question, use_baseline: false };
  if (conversationId) {
    payload.conversation_id = conversationId;
  }

  const response = await fetch(`${API_BASE_URL}/api/documents/${documentId}/ask/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let detail = 'Error connecting to streaming QA service.';
    try {
      const errJson = await response.json();
      detail = errJson.detail || detail;
    } catch {
      // ignore parse failure
    }
    throw new Error(detail);
  }

  if (!response.body) {
    throw new Error('Streaming is not supported in this browser environment.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const processBlock = (block) => {
    const lines = block.split(/\r?\n/);
    let eventName = 'message';
    const dataLines = [];
    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim());
      }
    }
    if (dataLines.length === 0) return;
    const rawData = dataLines.join('\n');
    try {
      const parsed = JSON.parse(rawData);
      if (eventName === 'meta' || parsed.event === 'meta') {
        onMeta?.(parsed);
      } else if (eventName === 'token' || parsed.event === 'token') {
        if (parsed.token) onToken?.(parsed.token);
      } else if (eventName === 'done' || parsed.event === 'done') {
        onDone?.(parsed);
      } else if (eventName === 'error' || parsed.event === 'error') {
        onError?.(new Error(parsed.detail || 'Streaming error'));
      }
    } catch {
      // ignore incomplete JSON chunk
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() || '';
    for (const part of parts) {
      if (part.trim()) processBlock(part);
    }
  }
  if (buffer.trim()) {
    processBlock(buffer);
  }
};

export const getDocumentHistory = async (documentId, conversationId = null) => {
  const url = conversationId 
    ? `/api/documents/${documentId}/history?conversation_id=${encodeURIComponent(conversationId)}`
    : `/api/documents/${documentId}/history`;
  const response = await api.get(url);
  return response.data;
};

export const getConversations = async () => {
  const response = await api.get('/api/conversations');
  return response.data;
};

export const deleteConversation = async (conversationId) => {
  const response = await api.delete(`/api/conversations/${conversationId}`);
  return response.data;
};

export default api;
