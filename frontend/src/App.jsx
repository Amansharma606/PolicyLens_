import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ToastProvider } from './context/ToastContext';
import { AuthProvider } from './context/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AppLayout } from './layouts/AppLayout';
import { LoginPage } from './pages/LoginPage';
import { Dashboard } from './pages/Dashboard';
import { UploadPage } from './pages/UploadPage';
import { ChatPage } from './pages/ChatPage';
import { DocumentLibrary } from './pages/DocumentLibrary';
import { ConversationHistory } from './pages/ConversationHistory';

export function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            {/* Protected Application Dashboard Routes */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <AppLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Dashboard />} />
              <Route path="dashboard" element={<Navigate to="/" replace />} />
              <Route path="upload" element={<UploadPage />} />
              <Route path="documents" element={<DocumentLibrary />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="chat/:documentId" element={<ChatPage />} />
              <Route path="history" element={<ConversationHistory />} />
            </Route>

            {/* Interactive Lamp Login Page */}
            <Route path="/login" element={<LoginPage />} />

            {/* Catch-all redirect */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  );
}

export default App;
