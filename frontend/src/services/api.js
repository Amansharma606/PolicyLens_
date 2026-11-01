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
