import React, { useEffect, useRef, useState } from 'react';
import {
  Bot,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  FileSearch,
  FileText,
  Send,
  Upload,
  User,
  ChevronRight,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

type Source = {
  chunk_id?: string | number;
  chunk_index?: number;
  page?: number;
  page_number?: number;
  filename?: string;
  excerpt?: string;
  content?: string;
};

type Message = {
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  sources?: Source[];
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

type EvalScores = {
  relevance: string;
  faithfulness: string;
  groundedness: string;
  reasoning: string;
};

function getStatusLabel(status?: string) {
  if (status === 'processing') return 'Processing';
  if (status === 'failed') return 'Failed';
  return 'Ready';
}

function getStatusTone(status?: string) {
  if (status === 'processing') return 'warning';
  if (status === 'failed') return 'danger';
  return 'success';
}

function SourceCards({ sources }: { sources: Source[] }) {
  return (
    <div className="sources-container">
      {sources.map((src, index) => {
        const label = src.chunk_id ?? src.chunk_index ?? index + 1;
        const preview = src.excerpt || src.content?.slice(0, 180) || 'No excerpt available.';
        return (
          <article key={`${label}-${index}`} className="source-card">
            <div className="source-card-header">
              <span className="source-card-badge">Chunk {label}</span>
              <span className="source-card-meta">Page {src.page || src.page_number || '?'}</span>
            </div>
            <div className="source-card-file">{src.filename || 'Uploaded document'}</div>
            <p className="source-card-preview">{preview}</p>
          </article>
        );
      })}
    </div>
  );
}

function MessageBubble({
  msg,
  isLoading,
  prevUserMsg,
}: {
  msg: Message;
  isLoading: boolean;
  prevUserMsg?: string;
}) {
  const [isThinkingOpen, setIsThinkingOpen] = useState(false);
  const [evalScores, setEvalScores] = useState<EvalScores | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);

  let raw = msg.content || '';
  let displayReasoning = '';
  let displayAnswer = raw;

  if (msg.role === 'assistant') {
    const reasoningMatch = raw.match(/<reasoning>([\s\S]*?)(?:<\/reasoning>|$)/);
    if (reasoningMatch) displayReasoning = reasoningMatch[1].trim();

    const answerMatch = raw.match(/<answer>([\s\S]*?)(?:<\/answer>|$)/);
    if (answerMatch) {
      displayAnswer = answerMatch[1].trim();
    } else if (raw.includes('</reasoning>')) {
      displayAnswer = raw.split('</reasoning>')[1].trim();
    } else if (raw.includes('<reasoning>')) {
      displayAnswer = '';
    }

    displayAnswer = displayAnswer
      .replace(/<sources>[\s\S]*?(?:<\/sources>|$)/, '')
      .replace(/<\/?answer>/g, '')
      .trim();

    if (!isLoading && !displayAnswer && displayReasoning) {
      displayAnswer = displayReasoning;
      displayReasoning = '';
    }
  }

  const isThinking = isLoading && !displayAnswer;

  const handleEvaluate = async () => {
    if (isEvaluating || !displayAnswer) return;

    setIsEvaluating(true);
    try {
      const contextText = msg.sources?.map((source) => source.content || source.excerpt || '').join('\n\n') || '';
      const res = await fetch('/api/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: prevUserMsg || 'Evaluate this response',
          answer: displayAnswer,
          context: contextText,
        }),
      });
      const data = await res.json();
      setEvalScores(data);
    } catch (error) {
      console.error(error);
    } finally {
      setIsEvaluating(false);
    }
  };

  return (
    <div className={`message ${msg.role}`}>
      <div className="sr-only" data-testid={`message-role-${msg.role}`}></div>
      <div className={`avatar ${msg.role}`}>
        {msg.role === 'assistant' ? <Bot size={18} /> : <User size={18} />}
      </div>
      <div className="message-shell">
        {msg.role === 'assistant' && (msg.retrieval_mode || displayReasoning || isThinking) && (
          <section className={`reasoning-container ${(isThinkingOpen || isThinking) ? 'open' : ''}`}>
            <button
              type="button"
              className="reasoning-header"
              onClick={() => setIsThinkingOpen((open) => !open)}
            >
              <span className="reasoning-title">
                {isThinking ? <span className="spinner" /> : <BrainCircuit size={15} />}
                {isThinking ? 'Analyzing context' : 'Reasoning and retrieval'}
              </span>
              <ChevronRight size={16} className="chevron" />
            </button>
            <div className="reasoning-content">
              {msg.retrieval_mode && (
                <div className="retrieval-grid">
                  <div className="retrieval-metric">
                    <span className="retrieval-label">Mode</span>
                    <strong>{msg.retrieval_mode.toUpperCase()}</strong>
                  </div>
                  <div className="retrieval-metric">
                    <span className="retrieval-label">Chunks</span>
                    <strong>{msg.chunk_count ?? 0}</strong>
                  </div>
                  <div className="retrieval-metric">
                    <span className="retrieval-label">Latency</span>
                    <strong>{msg.latency_ms ?? 0}ms</strong>
                  </div>
                  <div className="retrieval-query">
                    <span className="retrieval-label">Search query</span>
                    <p>{msg.search_query || 'No rewritten query available.'}</p>
                  </div>
                </div>
              )}
              {displayReasoning ? (
                <div className="reasoning-markdown">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayReasoning}</ReactMarkdown>
                </div>
              ) : (
                isThinking && <p className="thinking-copy">Reading uploaded context and preparing an answer.</p>
              )}
            </div>
          </section>
        )}

        <div className="message-content">
          <div className="markdown-body">
            {displayAnswer ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayAnswer}</ReactMarkdown>
            ) : (
              isLoading && <p className="thinking-copy">Waiting for the model to stream the answer.</p>
            )}
          </div>

          {msg.sources && msg.sources.length > 0 && <SourceCards sources={msg.sources} />}

          {msg.role === 'assistant' && !isLoading && displayAnswer && (
            <div className="message-actions">
              <button type="button" onClick={handleEvaluate} disabled={isEvaluating} className="ghost-button">
                <BrainCircuit size={14} />
                {isEvaluating ? 'Evaluating...' : 'Evaluate answer'}
              </button>

              {evalScores && (
                <div className="eval-scores">
                  <span className={`score-pill ${evalScores.relevance === 'Y' ? 'pass' : 'fail'}`}>
                    Relevance: {evalScores.relevance}
                  </span>
                  <span className={`score-pill ${evalScores.faithfulness === 'Y' ? 'pass' : 'fail'}`}>
                    Faithfulness: {evalScores.faithfulness}
                  </span>
                  <span className={`score-pill ${evalScores.groundedness === 'Y' ? 'pass' : 'fail'}`}>
                    Groundedness: {evalScores.groundedness}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
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
  const [uploadError, setUploadError] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeDocument = documents.find((doc) => doc.id === activeDocId) || null;
  const readyDocuments = documents.filter((doc) => doc.status !== 'processing' && doc.status !== 'failed');
  const processingDocuments = documents.filter((doc) => doc.status === 'processing');

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const processingDocs = documents.filter((doc) => doc.status === 'processing');
    if (processingDocs.length === 0) return;

    const interval = setInterval(async () => {
      for (const doc of processingDocs) {
        try {
          const res = await fetch(`/api/documents/${doc.id}/status`);
          if (!res.ok) continue;

          const data = await res.json();
          if (data.status === 'completed' || data.status === 'failed') {
            setDocuments((prev) =>
              prev.map((item) =>
                item.id === doc.id
                  ? { ...item, status: data.status, chunk_count: data.chunk_count }
                  : item
              )
            );
          }
        } catch (error) {
          console.error('Polling error', error);
        }
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [documents]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadError('');
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) throw new Error('Upload failed');

      const data = await res.json();
      const newDoc = {
        id: data.document_id,
        filename: data.filename,
        chunk_count: data.chunk_count,
        status: data.status,
      };
      setDocuments((prev) => [...prev, newDoc]);
      setActiveDocId(newDoc.id);
    } catch (error) {
      console.error(error);
      setUploadError('Upload failed. Use a text-based PDF or UTF-8 text file and try again.');
    }

    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg: Message = { role: 'user', content: input.trim() };
    setMessages((prev) => [...prev, userMsg, { role: 'assistant', content: '', reasoning: '' }]);
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
          if (!line.startsWith('data: ')) continue;

          const dataStr = line.substring(6);
          if (dataStr === '[DONE]') break;

          try {
            const data = JSON.parse(dataStr);
            setMessages((prev) => {
              const next = [...prev];
              const lastMsg = { ...next[next.length - 1] };

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

              next[next.length - 1] = lastMsg;
              return next;
            });
          } catch (error) {
            console.error('Failed to parse SSE', dataStr, error);
          }
        }
      }
    } catch (error) {
      console.error(error);
      setMessages((prev) => {
        const next = [...prev];
        const lastMsg = { ...next[next.length - 1] };
        lastMsg.content = 'Error: failed to fetch a streamed response from the backend.';
        next[next.length - 1] = lastMsg;
        return next;
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      <aside className="sidebar">
        <div className="sidebar-header">
          <p className="eyebrow">Workspace</p>
          <h1>Decision Assistant</h1>
          <p className="sidebar-copy">
            Upload a document, watch ingestion complete, and ask grounded questions with citations.
          </p>
        </div>

        <div className="upload-zone" onClick={() => fileInputRef.current?.click()}>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            className="hidden-input"
            accept=".pdf,.txt"
            data-testid="upload-input"
          />
          <Upload className="upload-icon" size={22} />
          <div className="upload-title">Upload PDF or text</div>
          <div className="upload-text">The backend extracts text, chunks it, embeds it, and marks the document ready.</div>
        </div>

        {uploadError && <div className="notice danger">{uploadError}</div>}

        <div className="sidebar-stats">
          <div className="stat-card">
            <span className="stat-label">Ready</span>
            <strong>{readyDocuments.length}</strong>
          </div>
          <div className="stat-card">
            <span className="stat-label">Processing</span>
            <strong>{processingDocuments.length}</strong>
          </div>
        </div>

        <div className="document-list">
          <button
            type="button"
            className={`document-item ${activeDocId === null ? 'active' : ''}`}
            onClick={() => setActiveDocId(null)}
          >
            <div className="document-main">
              <FileSearch size={16} />
              <div>
                <div className="document-name">All documents</div>
                <div className="document-meta">Search across every completed upload</div>
              </div>
            </div>
            {activeDocId === null && <CheckCircle2 size={16} color="var(--accent-strong)" />}
          </button>

          {documents.map((doc) => (
            <button
              key={doc.id}
              type="button"
              className={`document-item ${activeDocId === doc.id ? 'active' : ''}`}
              onClick={() => setActiveDocId(doc.id)}
            >
              <div className="document-main">
                <FileText size={16} />
                <div className="document-copy">
                  <div className="document-name">{doc.filename}</div>
                  <div className="document-meta">
                    {doc.chunk_count} chunks
                    <span className={`status-pill ${getStatusTone(doc.status)}`}>{getStatusLabel(doc.status)}</span>
                  </div>
                </div>
              </div>
              {activeDocId === doc.id && doc.status === 'completed' && (
                <CheckCircle2 size={16} color="var(--accent-strong)" />
              )}
            </button>
          ))}
        </div>
      </aside>

      <main className="chat-container">
        <header className="chat-header">
          <div>
            <p className="eyebrow">Scope</p>
            <h2>{activeDocument ? activeDocument.filename : 'All uploaded documents'}</h2>
          </div>
          <div className="chat-header-metrics">
            <div className="header-chip">
              <Clock3 size={14} />
              {processingDocuments.length > 0 ? `${processingDocuments.length} processing` : 'Ingestion idle'}
            </div>
            <div className="header-chip">
              <FileText size={14} />
              {documents.length} documents
            </div>
          </div>
        </header>

        {documents.length === 0 ? (
          <section className="hero-panel">
            <div className="hero-orb">
              <Bot size={56} />
            </div>
            <p className="eyebrow">Start here</p>
            <h2>Bring a document into the workspace</h2>
            <p className="hero-copy">
              This UI is tuned for reviewing retrieval behavior, streamed answers, and source-backed output instead of a generic chat shell.
            </p>
            <button type="button" className="primary-button" onClick={() => fileInputRef.current?.click()}>
              <Upload size={18} />
              Upload first document
            </button>
          </section>
        ) : (
          <>
            <div className="chat-messages">
              {messages.length === 0 ? (
                <section className="empty-state">
                  <Bot size={44} />
                  <h3>{activeDocument?.status === 'processing' ? 'Document is processing' : 'Ready for questions'}</h3>
                  <p>
                    {activeDocument?.status === 'processing'
                      ? 'Wait for ingestion to finish, then ask about claims, risks, summaries, or evidence in the document.'
                      : 'Ask a question and review the reasoning panel, retrieval metadata, and citations as the answer streams in.'}
                  </p>
                </section>
              ) : (
                messages.map((msg, index) => (
                  <div
                    key={index}
                    data-testid="chat-message"
                    data-message-role={msg.role}
                  >
                    <MessageBubble
                      msg={msg}
                      isLoading={isLoading && index === messages.length - 1}
                      prevUserMsg={index > 0 && messages[index - 1].role === 'user' ? messages[index - 1].content : undefined}
                    />
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            <form className="input-area" onSubmit={handleSubmit}>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  activeDocument?.status === 'processing'
                    ? 'Document is still processing...'
                    : 'Ask a question about your documents...'
                }
                className="chat-input"
                disabled={isLoading || activeDocument?.status === 'processing'}
                data-testid="chat-input"
              />
              <button
                type="submit"
                className="send-button"
                disabled={!input.trim() || isLoading || activeDocument?.status === 'processing'}
                data-testid="send-button"
              >
                <Send size={18} />
              </button>
            </form>
          </>
        )}
      </main>
    </div>
  );
}

export default App;
