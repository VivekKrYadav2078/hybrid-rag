'use client';

import React, { useState, useEffect } from 'react';
// import { supabase } from '@/lib/supabase';
import Navbar from '@/components/Navbar';
import KnowledgeBasePanel from '@/components/KnowledgeBasePanel';
import ChatPanel from '@/components/ChatPanel';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface DocItem {
  id: string;
  filename?: string;
  title?: string;
  created_at?: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export default function RagDemoDashboard() {
  const [sessionId, setSessionId] = useState<string>('');
  const [documents, setDocuments] = useState<DocItem[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let storedSession = localStorage.getItem('rag_demo_session_id');
    if (!storedSession) {
      storedSession = crypto.randomUUID();
      localStorage.setItem('rag_demo_session_id', storedSession);
    }
    setSessionId(storedSession);
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      const res = await fetch(`${API_URL}/documents`);
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.documents || []);
      }
    } catch (err) {
      console.error('Error fetching documents from FastAPI:', err);
    }
  };

  const resetSession = () => {
    const newSession = crypto.randomUUID();
    localStorage.setItem('rag_demo_session_id', newSession);
    setSessionId(newSession);
    setMessages([]);
  };

  // const handleSendMessage = async (userText: string) => {
  //   const userMsg: Message = { role: 'user', content: userText };
  //   const updatedMessages = [...messages, userMsg];
  //   setMessages(updatedMessages);
  //   setSending(true);

  //   try {
  //     const res = await fetch(`${API_URL}/chat`, {
  //       method: 'POST',
  //       headers: { 'Content-Type': 'application/json' },
  //       body: JSON.stringify({
  //         message: userText,
  //         session_id: sessionId,
  //         chat_history: messages, // Send prior conversation history for context
  //       }),
  //     });

  //     if (!res.ok) throw new Error('Chat request failed');

  //     // Handle streaming response from FastAPI + Groq
  //     const reader = res.body?.getReader();
  //     const decoder = new TextDecoder();
  //     let assistantContent = '';

  //     setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

  //     if (reader) {
  //       while (true) {
  //         const { done, value } = await reader.read();
  //         if (done) break;
  //         assistantContent += decoder.decode(value, { stream: true });
  //         setMessages((prev) => {
  //           const updated = [...prev];
  //           updated[updated.length - 1] = { role: 'assistant', content: assistantContent };
  //           return updated;
  //         });
  //       }
  //     }
  //   } catch (err) {
  //     console.error(err);
  //     setMessages((prev) => [
  //       ...prev,
  //       { role: 'assistant', content: '⚠️ Failed to reach backend. Ensure FastAPI is running on port 8000.' },
  //     ]);
  //   } finally {
  //     setSending(false);
  //   }
  // };
  const handleSendMessage = async (userText: string) => {
    const userMsg: Message = { role: 'user', content: userText };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setSending(true);

    let assistantContent = '';

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userText,
          session_id: sessionId,
          chat_history: messages,
        }),
      });

      if (!res.ok) throw new Error('Chat request failed');

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();

      setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

      if (reader) {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            assistantContent += decoder.decode(value, { stream: true });
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = { role: 'assistant', content: assistantContent };
              return updated;
            });
          }
        } catch (streamErr) {
          // Stream read closed or interrupted, but if we have content, ignore it
          if (!assistantContent) throw streamErr;
        }
      }
    } catch (err) {
      console.error(err);
      // Only show error message if we didn't successfully stream any text
      if (!assistantContent) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: '⚠️ Failed to reach backend. Ensure FastAPI is running on port 8000.' },
        ]);
      }
    } finally {
      setSending(false);
    }
  };
  return (
    <div className="min-h-screen bg-slate-100/70 text-slate-900 flex flex-col font-sans">
      <Navbar sessionId={sessionId} onResetSession={resetSession} />

      <main className="flex-1 max-w-7xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        <KnowledgeBasePanel documents={documents} onUploadSuccess={fetchDocuments} apiUrl={API_URL} />
        <ChatPanel messages={messages} onSendMessage={handleSendMessage} sending={sending} />
      </main>
    </div>
  );
}