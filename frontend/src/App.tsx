import React, { useState, useRef, useEffect } from 'react';
import { Upload, Send, User, Bot, FileText, CheckCircle2, ChevronDown, ChevronRight, BrainCircuit } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

type Message = {
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  sources?: any[];
  retrieval_mode?: string;
  search_query?: string;
  chunk_count?: number;
  latency_ms?: number;
};

type Document = {
  id: number;
  filename: string;
  chunk_count: number;
  status?: string;
};

function MessageBubble({ msg, isLoading, prevUserMsg }: { msg: Message, isLoading: boolean, prevUserMsg?: string }) {
  const [isThinkingOpen, setIsThinkingOpen] = useState(false);
  
  let raw = msg.content || '';
  let displayReasoning = '';
  let displayAnswer = raw;

  if (msg.role === 'assistant') {
    const rMatch = raw.match(/<reasoning>([\s\S]*?)(?:<\/reasoning>|$)/);
    if (rMatch) displayReasoning = rMatch[1].trim();

    const aMatch = raw.match(/<answer>([\s\S]*?)(?:<\/answer>|$)/);
    if (aMatch) {
      displayAnswer = aMatch[1].trim();
    } else if (raw.includes('</reasoning>')) {
      displayAnswer = raw.split('</reasoning>')[1].trim();
    } else if (raw.includes('<reasoning>')) {
      displayAnswer = '';
    }

    displayAnswer = displayAnswer.replace(/<sources>[\s\S]*?(?:<\/sources>|$)/, '').replace(/<\/?answer>/g, '').trim();

    // Ultimate Fallback: if the LLM dumped everything into reasoning, or if the answer is empty when done
    if (!isLoading && !displayAnswer && displayReasoning) {
      displayAnswer = displayReasoning;
      displayReasoning = '';
    }
  }

  const isThinking = isLoading && !displayAnswer;

  const [evalScores, setEvalScores] = useState<any>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  
  const handleEvaluate = async () => {
    if (isEvaluating || !displayAnswer) return;
    setIsEvaluating(true);
    try {
      const res = await fetch('/api/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: prevUserMsg || "Evaluate this response", answer: displayAnswer })
      });
      const data = await res.json();
      setEvalScores(data);
    } catch (e) {
      console.error(e);
    }
    setIsEvaluating(false);
  };

  return (
    <div className={`message ${msg.role}`}>
      <div className="avatar">
        {msg.role === 'assistant' ? <Bot size={20} /> : <User size={20} />}
      </div>
      <div className="message-content" style={{ position: 'relative' }}>
        {(displayReasoning || isThinking || msg.retrieval_mode) && msg.role === 'assistant' && (
          <div className={`reasoning-container ${(isThinkingOpen || isThinking) ? 'open' : ''}`}>
            <div className="reasoning-header" onClick={() => setIsThinkingOpen(!isThinkingOpen)}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {isThinking ? (
                  <div className="spinner" style={{ width: 14, height: 14, border: '2px solid var(--text-muted)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                ) : (
                  <Bot size={16} />
                )}
                <span>{isThinking ? 'Analyzing context...' : 'Thinking Process'}</span>
                <ChevronRight size={16} className="chevron" />
              </div>
            </div>
            <div className="reasoning-content">
              {msg.retrieval_mode && (
                <div style={{ marginBottom: '1rem', padding: '0.75rem', background: 'rgba(0,0,0,0.2)', borderRadius: '6px', fontSize: '0.8rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                    <span style={{ color: 'var(--primary)' }}>Retrieval Mode:</span>
                    <span style={{ fontWeight: 600 }}>{msg.retrieval_mode.toUpperCase()}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                    <span style={{ color: 'var(--primary)' }}>Search Query:</span>
                    <span style={{ fontStyle: 'italic' }}>"{msg.search_query}"</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--primary)' }}>Context Chunks:</span>
                    <span>{msg.chunk_count} ({msg.latency_ms}ms)</span>
                  </div>
                </div>
              )}
              {displayReasoning ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayReasoning}</ReactMarkdown>
              ) : (
                isThinking && <span style={{ opacity: 0.5, fontStyle: 'italic' }}>Parsing documents...</span>
              )}
            </div>
          </div>
        )}

        <div className="markdown-body">
          {displayAnswer && <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayAnswer}</ReactMarkdown>}
        </div>

        {msg.sources && msg.sources.length > 0 && (
          <div className="sources-container">
            {msg.sources.map((src, i) => (
              <div key={i} className="source-chip">
                Page {src.page || src.page_number} [Chunk {src.chunk_id || src.chunk_index}]
              </div>
            ))}
          </div>
        )}
        
        {msg.role === 'assistant' && !isLoading && displayAnswer && (
          <div style={{ marginTop: '1rem', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
            <button 
              onClick={handleEvaluate} 
              disabled={isEvaluating} 
              style={{ background: 'transparent', border: '1px solid var(--border)', color: 'var(--text-muted)', padding: '0.35rem 0.75rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem', transition: 'all 0.2s' }}
              onMouseOver={e => { e.currentTarget.style.color = 'var(--primary)'; e.currentTarget.style.borderColor = 'var(--primary)'; }}
              onMouseOut={e => { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.borderColor = 'var(--border)'; }}
            >
              <BrainCircuit size={14} />
              {isEvaluating ? 'Evaluating...' : 'Evaluate Answer'}
            </button>
            
            {evalScores && (
              <div style={{ display: 'flex', gap: '0.5rem', fontSize: '0.8rem' }}>
                <span style={{ padding: '0.2rem 0.5rem', borderRadius: '4px', background: evalScores.relevance === 'Y' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)', color: evalScores.relevance === 'Y' ? '#4ade80' : '#f87171' }}>
                  Relevance: {evalScores.relevance}
                </span>
                <span style={{ padding: '0.2rem 0.5rem', borderRadius: '4px', background: evalScores.faithfulness === 'Y' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)', color: evalScores.faithfulness === 'Y' ? '#4ade80' : '#f87171' }}>
                  Faithfulness: {evalScores.faithfulness}
                </span>
                <span style={{ padding: '0.2rem 0.5rem', borderRadius: '4px', background: evalScores.groundedness === 'Y' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)', color: evalScores.groundedness === 'Y' ? '#4ade80' : '#f87171' }}>
                  Groundedness: {evalScores.groundedness}
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [activeDocId, setActiveDocId] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    const processingDocs = documents.filter(d => d.status === 'processing');
    if (processingDocs.length === 0) return;

    const interval = setInterval(async () => {
      for (const doc of processingDocs) {
        try {
          const res = await fetch(`/api/documents/${doc.id}/status`);
          if (res.ok) {
            const data = await res.json();
            if (data.status === 'completed' || data.status === 'failed') {
              setDocuments(prev => prev.map(d => 
                d.id === doc.id ? { ...d, status: data.status, chunk_count: data.chunk_count } : d
              ));
            }
          }
        } catch (e) {
          console.error("Polling error", e);
        }
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [documents]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) throw new Error('Upload failed');
      const data = await res.json();
      const newDoc = { id: data.document_id, filename: data.filename, chunk_count: data.chunk_count, status: data.status };
      setDocuments(prev => [...prev, newDoc]);
      setActiveDocId(newDoc.id);
    } catch (err) {
      console.error(err);
      alert('Failed to upload document');
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg: Message = { role: 'user', content: input.trim() };
    setMessages(prev => [...prev, userMsg, { role: 'assistant', content: '', reasoning: '' }]);
    setInput('');
    setIsLoading(true);

    try {
      const res = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: userMsg.content,
          doc_id: activeDocId,
          chat_history: messages,
        }),
      });

      if (!res.body) throw new Error('No readable stream');
      
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.substring(6);
            if (dataStr === '[DONE]') break;
            
            try {
              const data = JSON.parse(dataStr);
              setMessages(prev => {
                const newMsgs = [...prev];
                const lastMsg = { ...newMsgs[newMsgs.length - 1] };
                
                if (data.type === 'token') {
                  lastMsg.content += data.text;
                } else if (data.type === 'retrieval_done') {
                  lastMsg.retrieval_mode = data.retrieval_mode;
                  lastMsg.search_query = data.search_query;
                  lastMsg.chunk_count = data.chunk_count;
                  lastMsg.latency_ms = data.latency_ms;
                } else if (data.type === 'final') {
                  lastMsg.reasoning = data.reasoning;
                  lastMsg.sources = data.sources;
                }
                newMsgs[newMsgs.length - 1] = lastMsg;
                return newMsgs;
              });
            } catch (e) {
              console.error('Failed to parse SSE', dataStr);
            }
          }
        }
      }
    } catch (err) {
      console.error(err);
      setMessages(prev => {
        const newMsgs = [...prev];
        const lastMsg = { ...newMsgs[newMsgs.length - 1] };
        lastMsg.content = 'Error: Failed to fetch response.';
        newMsgs[newMsgs.length - 1] = lastMsg;
        return newMsgs;
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      <aside className="sidebar">
        <h2>Documents</h2>
        <div className="upload-zone" onClick={() => fileInputRef.current?.click()}>
          <input type="file" ref={fileInputRef} onChange={handleFileUpload} style={{ display: 'none' }} accept=".pdf,.txt" />
          <Upload className="upload-icon" size={24} />
          <div className="upload-text">Click to upload PDF</div>
        </div>

        <div className="document-list">
          <div className={`document-item ${activeDocId === null ? 'active' : ''}`} onClick={() => setActiveDocId(null)}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <FileText size={16} /><span>All Documents</span>
            </div>
            {activeDocId === null && <CheckCircle2 size={16} color="var(--primary)" />}
          </div>
          {documents.map(doc => (
            <div key={doc.id} className={`document-item ${activeDocId === doc.id ? 'active' : ''}`} onClick={() => setActiveDocId(doc.id)}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', overflow: 'hidden' }}>
                <FileText size={16} style={{ flexShrink: 0 }} />
                <span style={{ whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden', flex: 1 }}>
                  {doc.filename}
                </span>
                {doc.status === 'processing' && <span style={{fontSize: '0.75rem', color: '#fbbf24', marginLeft: 4, flexShrink: 0}}>(Processing...)</span>}
                {doc.status === 'failed' && <span style={{fontSize: '0.75rem', color: '#ef4444', marginLeft: 4, flexShrink: 0}}>(Failed)</span>}
              </div>
              {activeDocId === doc.id && doc.status !== 'processing' && doc.status !== 'failed' && <CheckCircle2 size={16} color="var(--primary)" />}
            </div>
          ))}
        </div>
      </aside>

      <main className="chat-container">
        {documents.length === 0 ? (
          <div style={{ margin: 'auto', textAlign: 'center', color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
            <div style={{ background: 'rgba(59, 130, 246, 0.1)', padding: '2rem', borderRadius: '50%', marginBottom: '2rem' }}>
              <Bot size={64} style={{ color: 'var(--primary)' }} />
            </div>
            <h2 style={{ fontSize: '2rem', marginBottom: '1rem', color: 'var(--text-main)' }}>AI Decision Assistant</h2>
            <p style={{ fontSize: '1.1rem', maxWidth: '400px', marginBottom: '2rem', lineHeight: '1.6' }}>
              Upload a document to begin analyzing, extracting insights, and chatting with your data.
            </p>
            <button 
              onClick={() => fileInputRef.current?.click()}
              style={{ padding: '0.85rem 2rem', fontSize: '1.1rem', background: 'var(--primary)', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.75rem', fontWeight: 500, transition: 'all 0.2s', boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)' }}
              onMouseOver={e => e.currentTarget.style.transform = 'translateY(-2px)'}
              onMouseOut={e => e.currentTarget.style.transform = 'translateY(0)'}
            >
              <Upload size={20} />
              Upload Document
            </button>
          </div>
        ) : (
          <>
            <div className="chat-messages">
              {messages.length === 0 ? (
                <div style={{ margin: 'auto', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <Bot size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                  <h2>Document Ready</h2>
                  <p>Start asking questions about your documents.</p>
                </div>
              ) : (
                messages.map((msg, i) => (
                  <MessageBubble 
                    key={i} 
                    msg={msg} 
                    isLoading={isLoading && i === messages.length - 1} 
                    prevUserMsg={i > 0 && messages[i-1].role === 'user' ? messages[i-1].content : undefined}
                  />
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            <form className="input-area" onSubmit={handleSubmit}>
              <input
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder={documents.find(d => d.id === activeDocId)?.status === 'processing' ? "Document is still processing..." : "Ask a question about your documents..."}
                className="chat-input"
                disabled={isLoading || documents.find(d => d.id === activeDocId)?.status === 'processing'}
              />
              <button type="submit" className="send-button" disabled={!input.trim() || isLoading || documents.find(d => d.id === activeDocId)?.status === 'processing'}>
                <Send size={20} />
              </button>
            </form>
          </>
        )}
      </main>
    </div>
  );
}

export default App;
