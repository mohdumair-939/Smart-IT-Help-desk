import { useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Download, FileText, LoaderCircle, Paperclip, Trash2, UploadCloud } from 'lucide-react';
import {
  getListRecentActivityQueryKey,
  getListTicketAttachmentsQueryKey,
  getListTicketCommentsQueryKey,
  getListTicketsQueryKey,
  getGetDashboardSummaryQueryKey,
  getGetCurrentUserQueryKey,
  useCompleteTicketAttachmentUpload,
  useDeleteTicketAttachment,
  useGetCurrentUser,
  useListTicketAttachments,
  useRequestTicketAttachmentUpload,
  getTicketAttachmentDownload,
} from '@workspace/api-client-react';

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const allowedExtensions = new Set(['.pdf', '.docx', '.txt', '.md', '.png', '.jpg', '.jpeg', '.csv', '.log']);
const errorText = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Please try again.';

export default function TicketAttachments({ ticketId }: { ticketId: string }) {
  const queryClient = useQueryClient();
  const currentUser = useGetCurrentUser({ query: { queryKey: getGetCurrentUserQueryKey() } });
  const attachments = useListTicketAttachments(ticketId, {
    query: { queryKey: getListTicketAttachmentsQueryKey(ticketId), enabled: !!ticketId },
  });
  const requestUpload = useRequestTicketAttachmentUpload();
  const completeUpload = useCompleteTicketAttachmentUpload();
  const removeAttachment = useDeleteTicketAttachment();
  const [file, setFile] = useState<File | null>(null);
  const [pendingUpload, setPendingUpload] = useState<{ id: string; url: string; uploaded: boolean } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: getListTicketAttachmentsQueryKey(ticketId) });
    await queryClient.invalidateQueries({ queryKey: getListRecentActivityQueryKey() });
    await queryClient.invalidateQueries({ queryKey: getListTicketCommentsQueryKey(ticketId) });
    await queryClient.invalidateQueries({ queryKey: getListTicketsQueryKey() });
    await queryClient.invalidateQueries({ queryKey: getGetDashboardSummaryQueryKey() });
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) return;
    setError('');
    setNotice('');
    const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!allowedExtensions.has(extension)) {
      setError('Choose a PDF, DOCX, TXT, Markdown, CSV, LOG, PNG, or JPG file.');
      return;
    }
    if (file.size < 1 || file.size > MAX_FILE_BYTES) {
      setError('Attachments must be smaller than 10 MB.');
      return;
    }

    setUploading(true);
    try {
      let currentUpload = pendingUpload;
      if (!currentUpload) {
        const requested = await requestUpload.mutateAsync({
          ticketId,
          data: {
            filename: file.name,
            content_type: file.type || 'application/octet-stream',
            size_bytes: file.size,
          },
        });
        currentUpload = { id: requested.attachment_id, url: requested.upload_url, uploaded: false };
        setPendingUpload(currentUpload);
      }
      if (!currentUpload.uploaded) {
        const stored = await fetch(currentUpload.url, {
          method: 'PUT',
          headers: { 'Content-Type': file.type || 'application/octet-stream' },
          body: file,
        });
        if (!stored.ok) throw new Error('The file could not be stored. Try uploading it again.');
        currentUpload = { ...currentUpload, uploaded: true };
        setPendingUpload(currentUpload);
      }
      await completeUpload.mutateAsync({ ticketId, attachmentId: currentUpload.id });
      setPendingUpload(null);
      setFile(null);
      const input = document.getElementById(`ticket-attachment-${ticketId}`) as HTMLInputElement | null;
      if (input) input.value = '';
      setNotice('Attachment added to this ticket.');
      await invalidate();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setUploading(false);
    }
  };

  const download = async (attachmentId: string) => {
    setError('');
    const openedTab = window.open('about:blank', '_blank');
    if (openedTab) openedTab.opener = null;
    try {
      const result = await getTicketAttachmentDownload(ticketId, attachmentId);
      if (openedTab) openedTab.location.href = result.download_url;
      else window.location.assign(result.download_url);
    } catch (reason) {
      openedTab?.close();
      setError(errorText(reason));
    }
  };

  const deleteAttachment = (attachmentId: string, filename: string) => {
    if (!window.confirm(`Remove “${filename}” from this ticket? The stored file will be deleted.`)) return;
    setError('');
    removeAttachment.mutate({ ticketId, attachmentId }, {
      onSuccess: () => invalidate(),
      onError: (reason) => setError(errorText(reason)),
    });
  };

  const isStaff = currentUser.data?.role === 'admin' || currentUser.data?.role === 'support_engineer';

  return <section className="panel attachment-panel">
    <div className="panel-head"><div><h2 className="panel-title">Attachments</h2><p className="panel-kicker">Private files shared with the requester and support team · 10 MB max</p></div><Paperclip size={15} color="hsl(var(--muted-foreground))" /></div>
    {attachments.isLoading ? <div className="loading-state" style={{ padding: '16px 20px' }}>Loading attachments…</div> : attachments.isError ? <div className="auth-error" role="alert" style={{ margin: '0 20px 16px' }}>{errorText(attachments.error)}</div> : attachments.data?.length ? <div className="attachment-list">
      {attachments.data.map((attachment) => <article className="attachment-row" key={attachment.id}>
        <div className="attachment-file-icon"><FileText size={15} /></div>
        <div className="attachment-file-info"><strong>{attachment.filename}</strong><span>{(attachment.size_bytes / (1024 * 1024)).toFixed(2)} MB · added by {attachment.uploaded_by.name}</span>{attachment.status !== 'ready' ? <small>Upload incomplete — remove it and try again.</small> : null}</div>
        {attachment.status === 'ready' ? <button className="icon-button" title="Open attachment" aria-label={`Open ${attachment.filename}`} onClick={() => download(attachment.id)}><Download size={14} /></button> : <span className="attachment-pending">Pending</span>}
        {isStaff || attachment.uploaded_by.id === currentUser.data?.id ? <button className="icon-button danger" title="Remove attachment" aria-label={`Remove ${attachment.filename}`} disabled={removeAttachment.isPending} onClick={() => deleteAttachment(attachment.id, attachment.filename)}><Trash2 size={14} /></button> : null}
      </article>)}
    </div> : <div className="attachment-empty">No files have been attached to this request.</div>}
    <form className="attachment-upload" onSubmit={submit}>
      <label htmlFor={`ticket-attachment-${ticketId}`}>Add a file</label>
      <input id={`ticket-attachment-${ticketId}`} type="file" accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.csv,.log" disabled={!!pendingUpload || uploading} onChange={(event) => setFile(event.target.files?.[0] || null)} data-testid="input-ticket-attachment" />
      {pendingUpload?.uploaded ? <small>File uploaded; retry to verify and finish attaching it.</small> : <small>PDF, DOCX, TXT, Markdown, CSV, LOG, PNG, or JPG · up to 10 MB</small>}
      {error ? <div className="auth-error" role="alert">{error}</div> : null}
      {notice ? <div className="kb-upload-notice" role="status">{notice}</div> : null}
      <button className="button secondary small" type="submit" disabled={!file || uploading} data-testid="button-upload-ticket-attachment">{uploading ? <><LoaderCircle size={13} /> {pendingUpload?.uploaded ? 'Verifying file…' : 'Uploading…'}</> : <><UploadCloud size={13} /> {pendingUpload?.uploaded ? 'Finish attaching' : 'Upload attachment'}</>}</button>
    </form>
  </section>;
}
