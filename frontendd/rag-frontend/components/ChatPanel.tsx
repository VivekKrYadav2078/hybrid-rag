'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2, MessageSquare } from 'lucide-react';

interface Message {
    role: 'user' | 'assistant';
    content: string;
}

interface ChatPanelProps {
    messages: Message[];
    onSendMessage: (userMessage: string) => Promise<void>;
    sending: boolean;
}

export default function ChatPanel({ messages, onSendMessage, sending }: ChatPanelProps) {
    const [input, setInput] = useState('');
    const chatEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, sending]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || sending) return;

        const userText = input.trim();
        setInput('');
        await onSendMessage(userText);
    };

    return (
        <section className="lg:col-span-8 bg-white rounded-2xl border border-slate-200/80 shadow-sm flex flex-col h-[calc(100vh-140px)]">
            {/* Header title */}
            <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-indigo-600" />
                <h2 className="font-semibold text-sm text-slate-900">RAG Assistant Chat Window</h2>
            </div>

            {/* Messages Feed */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {messages.length === 0 && (
                    <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto">
                        <div className="w-16 h-16 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 mb-4 shadow-sm">
                            <Bot className="w-8 h-8" />
                        </div>
                        <h3 className="font-bold text-slate-800 text-base">Ask your Knowledge Base</h3>
                        <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                            Query your uploaded files. The system uses Hybrid Search + Cross-Encoder Reranking to pull exact passages for Groq LLM.
                        </p>
                    </div>
                )}

                {messages.map((msg, idx) => (
                    <div
                        key={idx}
                        className={`flex gap-3.5 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                        {msg.role === 'assistant' && (
                            <div className="w-8 h-8 rounded-xl bg-indigo-100 text-indigo-600 flex items-center justify-center shrink-0 mt-1 shadow-2xs">
                                <Bot className="w-4 h-4" />
                            </div>
                        )}

                        <div
                            className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-2xs ${msg.role === 'user'
                                    ? 'bg-indigo-600 text-white rounded-br-xs'
                                    : 'bg-slate-100/80 text-slate-800 border border-slate-200/60 rounded-bl-xs'
                                }`}
                        >
                            <p className="whitespace-pre-wrap">{msg.content}</p>
                        </div>

                        {msg.role === 'user' && (
                            <div className="w-8 h-8 rounded-xl bg-slate-900 text-white flex items-center justify-center shrink-0 mt-1 shadow-2xs">
                                <User className="w-4 h-4" />
                            </div>
                        )}
                    </div>
                ))}
                <div ref={chatEndRef} />
            </div>

            {/* Input Form */}
            <form onSubmit={handleSubmit} className="p-4 border-t border-slate-100 flex gap-3 bg-white rounded-b-2xl">
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Ask a question about your uploaded documents..."
                    className="flex-1 rounded-xl border border-slate-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 transition shadow-2xs"
                />
                <button
                    type="submit"
                    disabled={sending || !input.trim()}
                    className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white px-6 py-3 rounded-xl text-sm font-semibold flex items-center gap-2 transition shadow-md cursor-pointer"
                >
                    {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    Send
                </button>
            </form>
        </section>
    );
}