'use client';

import { Sparkles, RefreshCw } from 'lucide-react';

interface NavbarProps {
    sessionId: string;
    onResetSession: () => void;
}

export default function Navbar({ sessionId, onResetSession }: NavbarProps) {
    return (
        <header className="bg-white border-b border-slate-200 px-6 py-4 flex flex-col sm:flex-row items-center justify-between gap-4 shadow-sm">
            <div className="flex items-center gap-3">
                <div className="bg-gradient-to-tr from-indigo-600 to-violet-600 text-white p-2.5 rounded-xl shadow-md">
                    <Sparkles className="w-5 h-5" />
                </div>
                <div>
                    <h1 className="font-bold text-lg text-slate-900 tracking-tight">Enterprise RAG Knowledge Assistant</h1>
                    <p className="text-xs text-slate-500 font-medium">
                        Docling Parsing • BGE Hybrid Search • Cross-Encoder Reranking • Groq LLM
                    </p>
                </div>
            </div>

            <div className="flex items-center gap-3">
                <span className="text-xs bg-slate-100 text-slate-600 px-3 py-1.5 rounded-lg font-mono border border-slate-200">
                    Session: {sessionId.slice(0, 8)}...
                </span>
                <button
                    onClick={onResetSession}
                    className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-indigo-600 bg-white hover:bg-indigo-50 border border-slate-200 px-3 py-1.5 rounded-lg transition"
                    title="Start a new chat session"
                >
                    <RefreshCw className="w-3.5 h-3.5" />
                    New Chat
                </button>
            </div>
        </header>
    );
}