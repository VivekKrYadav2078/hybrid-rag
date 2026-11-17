'use client';

import React, { useState } from 'react';
import { Upload, FileText, CheckCircle2, Loader2, Database } from 'lucide-react';

interface DocItem {
    id: string;
    filename?: string;
    title?: string;
    created_at?: string;
}

interface KnowledgeBasePanelProps {
    documents: DocItem[];
    onUploadSuccess: () => void;
    apiUrl: string;
}

export default function KnowledgeBasePanel({
    documents,
    onUploadSuccess,
    apiUrl,
}: KnowledgeBasePanelProps) {
    const [uploading, setUploading] = useState(false);
    const [uploadStatus, setUploadStatus] = useState<string | null>(null);

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setUploading(true);
        setUploadStatus(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch(`${apiUrl}/ingest`, {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) throw new Error('Ingestion failed');

            setUploadStatus(`Indexed "${file.name}" successfully!`);
            onUploadSuccess();
        } catch (err) {
            console.error(err);
            setUploadStatus('Error uploading file. Check FastAPI console.');
        } finally {
            setUploading(false);
            e.target.value = '';
        }
    };

    return (
        <section className="lg:col-span-4 bg-white rounded-2xl border border-slate-200/80 shadow-sm p-6 flex flex-col h-[calc(100vh-140px)]">
            <div className="flex items-center gap-2 mb-1">
                <Database className="w-4 h-4 text-indigo-600" />
                <h2 className="font-semibold text-base text-slate-900">Knowledge Base</h2>
            </div>
            <p className="text-xs text-slate-500 mb-5">
                Upload corporate documents (.pdf, .txt, .docx) for structural parsing and vectorization.
            </p>

            {/* Dropzone Upload Box */}
            <label className="border-2 border-dashed border-slate-300 hover:border-indigo-500 bg-slate-50/50 hover:bg-indigo-50/30 transition-all rounded-xl p-6 flex flex-col items-center justify-center cursor-pointer text-center group">
                {uploading ? (
                    <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mb-2" />
                ) : (
                    <Upload className="w-8 h-8 text-slate-400 group-hover:text-indigo-600 transition-colors mb-2" />
                )}
                <span className="text-sm font-semibold text-slate-700">
                    {uploading ? 'Docling parsing & embedding...' : 'Click to upload document'}
                </span>
                <span className="text-xs text-slate-400 mt-1">PDF, DOCX, TXT, MD supported</span>
                <input
                    type="file"
                    accept=".txt,.pdf,.docx,.md"
                    onChange={handleFileUpload}
                    disabled={uploading}
                    className="hidden"
                />
            </label>

            {uploadStatus && (
                <div className="mt-3 text-xs px-3 py-2.5 rounded-xl bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-2 animate-fade-in">
                    <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
                    <span className="font-medium">{uploadStatus}</span>
                </div>
            )}

            {/* Document List */}
            <div className="mt-6 flex-1 overflow-y-auto pr-1">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
                    Indexed Documents ({documents.length})
                </h3>
                {documents.length === 0 ? (
                    <div className="text-center py-10 px-4 border border-dashed border-slate-200 rounded-xl bg-slate-50/30">
                        <p className="text-xs text-slate-400">No documents indexed yet. Upload a test file to start querying.</p>
                    </div>
                ) : (
                    <ul className="space-y-2.5">
                        {documents.map((doc) => (
                            <li
                                key={doc.id}
                                className="flex items-center justify-between p-3 rounded-xl border border-slate-100 bg-slate-50 hover:bg-slate-100/80 transition shadow-2xs"
                            >
                                <div className="flex items-center gap-2.5 truncate">
                                    <div className="p-1.5 bg-white rounded-lg border border-slate-200 text-indigo-600 shadow-2xs">
                                        <FileText className="w-4 h-4" />
                                    </div>
                                    <span className="truncate text-xs font-semibold text-slate-700">
                                        {doc.filename || doc.title || 'Untitled Document'}
                                    </span>
                                </div>
                                <span className="text-[10px] font-bold bg-emerald-100 text-emerald-700 px-2.5 py-1 rounded-full uppercase tracking-wider">
                                    Ready
                                </span>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </section>
    );
}