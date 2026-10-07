import { useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Link } from 'wouter';
import { AlertTriangle, ArrowRight, BookOpen, Bot, Check, FileText, LoaderCircle, Search, Sparkles, Trash2, UploadCloud } from 'lucide-react';
import {
  getListKnowledgeGapsQueryKey,
  getListKnowledgeDocumentsQueryKey,
  useCloseKnowledgeGap,
  useDeleteKnowledgeDocument,
  useGetCurrentUser,
  useGetTicketResolutionHelp,
  useIngestKnowledgeDocument,
  useListKnowledgeDocuments,
  useListKnowledgeGaps,
  useRequestKnowledgeUpload,
  useSearchKnowledge,
  type Citation,
  type GroundedAnswer,
} from '@workspace/api-client-react';

const TOKEN_KEY = 'smart-help-desk.access-token';
const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;
const acceptedExtensions = new Set(['.pdf', '.docx', '.txt', '.md']);
const errorText = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Please try again.';

function fileExtension(filename: string) {
  return filename.slice(filename.lastIndexOf('.')).toLowerCase();
}

export function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return <div className="citation-list" aria-label="Knowledge base citations">
    <div className="citation-heading">Sources from the approved knowledge base</div>
    {citations.map((citation, index) => <article className="citation-card" key={`${citation.document_id}-${citation.chunk_index}`} data-testid={`citation-${citation.document_id}-${citation.chunk_index}`}>
      <div className="citation-title"><span className="citation-index">S{index + 1}</span><strong>{citation.title}</strong></div>
      <div className="citation-meta"><FileText size={12} /> {citation.filename} · passage {citation.chunk_index + 1}</div>
      <p>{citation.excerpt}</p>
    </article>)}
  </div>;
}

export default function KnowledgeBasePage() {
  const user = useGetCurrentUser();
  const queryClient = useQueryClient();
  const isAdmin = user.data?.role === 'admin';
  const documents = useListKnowledgeDocuments({
    query: {
      queryKey: getListKnowledgeDocumentsQueryKey(),
      enabled: isAdmin,
      refetchInterval: (query) => query.state.data?.some((doc) => ['queued', 'processing'].includes(doc.status)) ? 2500 : false,
    },
  });
  const gaps = useListKnowledgeGaps({ status: 'all' }, {
    query: { queryKey: getListKnowledgeGapsQueryKey({ status: 'all' }), enabled: isAdmin },
  });
  const closeGap = useCloseKnowledgeGap();
  const ask = useSearchKnowledge();
  const requestUpload = useRequestKnowledgeUpload();
  const ingest = useIngestKnowledgeDocument();
  const remove = useDeleteKnowledgeDocument();
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<GroundedAnswer | null>(null);
  const [searchError, setSearchError] = useState('');
  const [uploadError, setUploadError] = useState('');
  const [uploadNotice, setUploadNotice] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [uploading, setUploading] = useState(false);

  const submitQuestion = (event: FormEvent) => {
    event.preventDefault();
    if (question.trim().length < 3) return;
    setSearchError('');
    setAnswer(null);
    ask.mutate({ data: { query: question.trim() } }, {
      onSuccess: setAnswer,
      onError: (reason) => setSearchError(errorText(reason)),
    });
  };

  const submitDocument = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) return;
    setUploadError('');
    setUploadNotice('');
    if (!acceptedExtensions.has(fileExtension(file.name))) {
      setUploadError('Choose a PDF, DOCX, TXT, or Markdown file.');
      return;
    }
    if (file.size < 1 || file.size > MAX_UPLOAD_BYTES) {
      setUploadError('Documents must be smaller than 15 MB.');
      return;
    }

    setUploading(true);
    try {
      const upload = await requestUpload.mutateAsync({
        data: {
          title: title.trim() || file.name,
          filename: file.name,
          content_type: file.type || 'application/octet-stream',
          size_bytes: file.size,
        },
      });
      const stored = await fetch(upload.upload_url, {
        method: 'PUT',
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
        body: file,
      });
      if (!stored.ok) throw new Error('The file could not be stored. Please try again.');

      await ingest.mutateAsync({ documentId: upload.document_id });
      setFile(null);
      setTitle('');
      const input = document.getElementById('knowledge-file') as HTMLInputElement | null;
      if (input) input.value = '';
      setUploadNotice('Upload complete. The document is being indexed and will be searchable when its status is Ready.');
      await queryClient.invalidateQueries({ queryKey: getListKnowledgeDocumentsQueryKey() });
    } catch (reason) {
      setUploadError(errorText(reason));
      await queryClient.invalidateQueries({ queryKey: getListKnowledgeDocumentsQueryKey() });
    } finally {
      setUploading(false);
    }
  };

  const deleteDocument = (documentId: string, name: string) => {
    if (!window.confirm(`Delete “${name}” and remove its indexed passages? This cannot be undone.`)) return;
    remove.mutate({ documentId }, {
      onSuccess: () => queryClient.invalidateQueries({ queryKey: getListKnowledgeDocumentsQueryKey() }),
      onError: (reason) => setUploadError(errorText(reason)),
    });
  };
  const markGapReviewed = (gapId: string) => {
    closeGap.mutate({ gapId }, {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getListKnowledgeGapsQueryKey({ status: 'all' }) });
        void queryClient.invalidateQueries({ queryKey: getListKnowledgeGapsQueryKey({ status: 'open' }) });
      },
      onError: (reason) => setUploadError(errorText(reason)),
    });
  };

  return <section>
    <div className="page-heading">
      <div><div className="eyebrow">Approved IT guidance</div><h1>Knowledge base</h1><p className="page-subtitle">Search trusted support articles and get answers with source citations.</p></div>
      <div className="kb-trust"><BookOpen size={15} /> Grounded in approved articles</div>
    </div>
    <div className="notice"><strong>AI privacy:</strong> Your question is sent to OpenAI to draft an answer. Don’t include passwords, access tokens, or sensitive personal information. Verify suggested steps before applying them.</div>
    <div className="kb-grid">
      <section className="panel kb-search-panel">
        <div className="panel-head"><div><h2 className="panel-title">Ask IT guidance</h2><p className="panel-kicker">Answers use passages from indexed documents only.</p></div><Sparkles size={16} color="hsl(var(--primary))" /></div>
        <form onSubmit={submitQuestion} className="kb-question-form" data-testid="form-knowledge-search">
          <label htmlFor="knowledge-question">What do you need help with?</label>
          <textarea id="knowledge-question" value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={2000} placeholder="Describe the IT issue or ask a question about a support procedure." data-testid="input-knowledge-question" />
          {searchError ? <div className="auth-error" role="alert">{searchError}</div> : null}
          <div className="kb-form-actions"><span className="muted-text">OpenAI may not have enough evidence to answer every question.</span><button className="button" type="submit" disabled={ask.isPending || question.trim().length < 3} data-testid="button-knowledge-search">{ask.isPending ? <><LoaderCircle size={14} /> Searching…</> : <><Search size={14} /> Ask the knowledge base</>}</button></div>
        </form>
        {ask.isPending ? <div className="kb-answer-placeholder"><LoaderCircle size={16} className="spin" /> Searching indexed passages and preparing an answer…</div> : answer ? <div className="kb-answer" aria-live="polite">
          <div className="kb-answer-title"><Bot size={16} /> Suggested answer</div>
          <p>{answer.answer}</p>
          {answer.needs_human_support ? <div className="kb-escalation">The approved articles did not contain enough evidence. Please contact your IT team.</div> : <div className="kb-review-note">Review this suggestion before acting on it.</div>}
          <CitationList citations={answer.citations} />
        </div> : null}
      </section>

      {isAdmin ? <section className="panel kb-admin-panel">
        <div className="panel-head"><div><h2 className="panel-title">Manage articles</h2><p className="panel-kicker">Only administrators can add or remove source documents.</p></div><UploadCloud size={16} color="hsl(var(--primary))" /></div>
        <form className="kb-upload-form" onSubmit={submitDocument} data-testid="form-knowledge-upload">
          <div className="form-field"><label htmlFor="knowledge-title">Article title</label><input id="knowledge-title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={180} placeholder={file?.name || 'Give this article a clear title'} /></div>
          <div className="form-field"><label htmlFor="knowledge-file">Document</label><input id="knowledge-file" type="file" accept=".pdf,.docx,.txt,.md,application/pdf,text/plain,text/markdown" onChange={(event) => { const next = event.target.files?.[0] || null; setFile(next); if (next && !title) setTitle(next.name.replace(/\.[^.]+$/, '')); }} data-testid="input-knowledge-file" /><small>PDF, DOCX, TXT, or Markdown · up to 15 MB</small></div>
          {uploadError ? <div className="auth-error" role="alert">{uploadError}</div> : null}
          {uploadNotice ? <div className="kb-upload-notice" role="status">{uploadNotice}</div> : null}
          <button className="button" type="submit" disabled={!file || uploading} data-testid="button-upload-knowledge">{uploading ? <><LoaderCircle size={14} /> Uploading and indexing…</> : <><UploadCloud size={14} /> Upload article</>}</button>
        </form>
        <div className="kb-document-list">
          <div className="kb-list-heading">Uploaded documents <span>{documents.data?.length ?? 0}</span></div>
          {documents.isLoading ? <div className="loading-state">Loading documents…</div> : documents.isError ? <div className="auth-error" role="alert">{errorText(documents.error)}</div> : documents.data?.length ? documents.data.map((doc) => <article className="kb-document" key={doc.id}>
            <div className="kb-document-icon"><FileText size={15} /></div>
            <div className="kb-document-main"><strong>{doc.title}</strong><span>{doc.filename} · {(doc.size_bytes / (1024 * 1024)).toFixed(1)} MB</span>
              {doc.status === 'ready' ? <small>{doc.chunk_count} indexed passages</small> : doc.error_message ? <small className="kb-document-error">{doc.error_message}</small> : null}
            </div>
            <span className={`kb-status kb-status-${doc.status}`}>{doc.status}</span>
            <div className="kb-document-actions">
              {doc.status === 'uploading' || doc.status === 'error' ? <button className="icon-button" title="Retry indexing" aria-label={`Retry indexing ${doc.title}`} data-testid={`button-retry-document-${doc.id}`} disabled={ingest.isPending} onClick={() => ingest.mutate({ documentId: doc.id }, { onSuccess: () => queryClient.invalidateQueries({ queryKey: getListKnowledgeDocumentsQueryKey() }), onError: (reason) => setUploadError(errorText(reason)) })}><Sparkles size={14} /></button> : null}
              <button className="icon-button danger" title="Delete document" aria-label={`Delete ${doc.title}`} data-testid={`button-delete-document-${doc.id}`} disabled={remove.isPending} onClick={() => deleteDocument(doc.id, doc.title)}><Trash2 size={14} /></button>
            </div>
          </article>) : <div className="empty-state"><div className="state-mark"><BookOpen size={18} /></div><strong>No documents yet</strong><div>Upload approved support guides to enable cited answers.</div></div>}
        </div>
      </section> : <section className="panel kb-empty-panel"><div className="empty-state"><div className="state-mark"><BookOpen size={19} /></div><strong>Answers come from approved IT documents</strong><div>The support team manages the documents behind the search results. If no article covers your issue, contact IT support.</div></div></section>}
    </div>
    {isAdmin ? <section className="panel knowledge-gaps">
      <div className="panel-head"><div><h2 className="panel-title">Knowledge gaps</h2><p className="panel-kicker">Unanswered needs surfaced through troubleshooting conversations</p></div><AlertTriangle size={16} color="hsl(var(--primary))" /></div>
      {gaps.isLoading ? <div className="loading-state">Loading knowledge gaps…</div> : gaps.isError ? <div className="empty-state"><div className="state-mark"><AlertTriangle size={18} /></div><strong>Knowledge gaps couldn’t load</strong><div>{errorText(gaps.error)}</div><button className="button secondary small" style={{ marginTop: 12 }} onClick={() => gaps.refetch()} data-testid="button-retry-knowledge-gaps">Try again</button></div> : gaps.data?.length ? <div className="gap-list">
        {gaps.data.map((gap) => <article className="gap-row" key={gap.id} data-testid={`row-knowledge-gap-${gap.id}`}>
          <div><div className="gap-query">{gap.query_text}</div><div className="gap-meta"><span>{gap.department}</span><span>·</span><span>{gap.category.replaceAll('_', ' ')}</span><span>·</span><span>{gap.priority} priority</span><span>·</span><time>{new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(gap.created_at))}</time></div><p className="gap-reason">{gap.reason}</p></div>
          <div className="gap-actions">{gap.ticket_id ? <Link className="gap-link" href={`/tickets/${gap.ticket_id}`} data-testid={`link-gap-ticket-${gap.id}`}>{gap.ticket_number || 'Linked ticket'} <ArrowRight size={12} /></Link> : null}<span className={`gap-status gap-status-${gap.status}`}>{gap.status}</span>{gap.status === 'open' ? <button className="button secondary small" onClick={() => markGapReviewed(gap.id)} disabled={closeGap.isPending} data-testid={`button-close-gap-${gap.id}`}>{closeGap.isPending ? <LoaderCircle size={12} /> : <Check size={12} />} Mark reviewed</button> : null}</div>
        </article>)}
      </div> : <div className="empty-state"><div className="state-mark"><Check size={18} /></div><strong>No knowledge gaps recorded</strong><div>When approved guidance is missing, surfaced gaps will appear here.</div></div>}
    </section> : null}
  </section>;
}

export function TicketResolutionAssist({ ticketId, onUseSuggestion }: { ticketId: string; onUseSuggestion?: (answer: string) => void }) {
  const [answer, setAnswer] = useState<GroundedAnswer | null>(null);
  const [error, setError] = useState('');
  const generate = useGetTicketResolutionHelp();
  const run = () => {
    setError('');
    generate.mutate({ ticketId }, {
      onSuccess: setAnswer,
      onError: (reason) => setError(errorText(reason)),
    });
  };
  return <section className="panel ai-assist-panel">
    <div className="panel-head"><div><h2 className="panel-title">AI resolution help</h2><p className="panel-kicker">Drafted from approved support articles for this ticket.</p></div><Sparkles size={16} color="hsl(var(--primary))" /></div>
    <div className="ai-assist-body">
      <p className="ai-privacy-note">Ticket details are sent to OpenAI when you request a draft. Don’t include passwords or sensitive information; review every suggestion.</p>
      <button className="button secondary small" onClick={run} disabled={generate.isPending} data-testid="button-ai-resolution">{generate.isPending ? <><LoaderCircle size={13} /> Preparing suggestion…</> : <><Sparkles size={13} /> Suggest next steps</>}</button>
      {error ? <div className="auth-error" role="alert" style={{ marginTop: 12 }}>{error}</div> : null}
      {answer ? <div className="kb-answer ai-answer" aria-live="polite">
        <p>{answer.answer}</p>
        {answer.needs_human_support ? <div className="kb-escalation">No relevant approved article was found. Escalate this ticket to the support team.</div> : null}
        {onUseSuggestion && !answer.needs_human_support ? <button className="button small" style={{ marginTop: 11 }} onClick={() => onUseSuggestion(answer.answer)}>Use as resolution draft</button> : null}
        <CitationList citations={answer.citations} />
      </div> : null}
    </div>
  </section>;
}
