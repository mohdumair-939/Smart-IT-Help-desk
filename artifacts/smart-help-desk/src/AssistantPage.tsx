import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Link, useLocation, useParams } from 'wouter';
import {
  Activity, AlertTriangle, ArrowRight, Bot, Check, CheckCircle2, CircleHelp,
  FileText, LoaderCircle, MessageSquareText, Network, RotateCcw, Send, ShieldAlert,
  Sparkles, Ticket as TicketIcon, UserRound, Wifi,
} from 'lucide-react';
import {
  getGetAssistantSessionQueryKey, getListAssistantSessionsQueryKey,
  useConfirmAssistantResolution, useCreateAssistantSession, useCreateEscalatedTicket,
  useGetAssistantSession, useListAssistantSessions, useRetryAssistantTurn,
  useSendAssistantMessage, type AssistantSession,
} from '@workspace/api-client-react';
import { CitationList } from './KnowledgeBasePage';

const nice = (value?: string | null) => value ? value.replaceAll('_', ' ') : 'Not provided';
const errorText = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Please try again.';
const quickStarts = [
  'My VPN stopped connecting after a password reset.',
  'I think someone may have accessed my account.',
  'A company application keeps crashing with an error.',
];

function fmtTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(date);
}

function journeySteps(status: AssistantSession['status'], hasAnalysis: boolean, hasAnswer: boolean) {
  const final = status === 'resolved' || status === 'escalated';
  return [
    { label: 'Issue reported', done: hasAnalysis || status !== 'triage' },
    { label: 'AI diagnosis', done: hasAnalysis },
    { label: 'Knowledge search', done: hasAnswer || status === 'escalation_preview' || final },
    { label: status === 'escalation_preview' || status === 'escalated' ? 'Human support' : 'Check the solution', done: final, active: status === 'solution_proposed' || status === 'escalation_preview' },
  ];
}

export default function AssistantPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params.sessionId || '';
  const [, navigate] = useLocation();
  const queryClient = useQueryClient();
  const sessionQuery = useGetAssistantSession(sessionId, {
    query: { queryKey: getGetAssistantSessionQueryKey(sessionId), enabled: !!sessionId },
  });
  const sessionsQuery = useListAssistantSessions();
  const createSession = useCreateAssistantSession();
  const sendMessage = useSendAssistantMessage();
  const retryTurn = useRetryAssistantTurn();
  const confirmResolution = useConfirmAssistantResolution();
  const createTicket = useCreateEscalatedTicket();
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const chatEnd = useRef<HTMLDivElement>(null);
  const session = sessionQuery.data;

  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [session?.messages.length]);

  const acceptSession = (next: AssistantSession) => {
    queryClient.setQueryData(getGetAssistantSessionQueryKey(next.id), next);
    void queryClient.invalidateQueries({ queryKey: getListAssistantSessionsQueryKey() });
    void queryClient.invalidateQueries({ queryKey: ['/api/v1/tickets'] });
    void queryClient.invalidateQueries({ queryKey: ['/api/v1/dashboard/summary'] });
    void queryClient.invalidateQueries({ queryKey: ['/api/v1/activity'] });
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = message.trim();
    if (text.length < 2) return;
    setError('');
    if (sessionId) {
      try {
        const updated = await sendMessage.mutateAsync({ sessionId, data: { message: text } });
        setMessage('');
        acceptSession(updated);
      } catch (reason) {
        setError(errorText(reason));
        await sessionQuery.refetch();
      }
      return;
    }

    setStarting(true);
    try {
      const created = await createSession.mutateAsync();
      setMessage('');
      navigate(`/assistant/${created.id}`);
      try {
        const updated = await sendMessage.mutateAsync({ sessionId: created.id, data: { message: text } });
        acceptSession(updated);
      } catch (reason) {
        setError(errorText(reason));
        await queryClient.invalidateQueries({ queryKey: getGetAssistantSessionQueryKey(created.id) });
      }
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setStarting(false);
    }
  };

  const retry = async () => {
    if (!sessionId) return;
    setError('');
    try {
      acceptSession(await retryTurn.mutateAsync({ sessionId }));
    } catch (reason) {
      setError(errorText(reason));
    }
  };

  const resolve = async (solved: boolean) => {
    if (!sessionId) return;
    setError('');
    try {
      acceptSession(await confirmResolution.mutateAsync({ sessionId, data: { solved } }));
    } catch (reason) {
      setError(errorText(reason));
    }
  };

  const escalate = async () => {
    if (!sessionId) return;
    setError('');
    try {
      acceptSession(await createTicket.mutateAsync({ sessionId }));
    } catch (reason) {
      setError(errorText(reason));
    }
  };

  const isBusy = starting || createSession.isPending || sendMessage.isPending || retryTurn.isPending || confirmResolution.isPending || createTicket.isPending;
  const currentJourney = session ? journeySteps(session.status, !!session.analysis, !!session.answer) : null;
  const lastMessage = session?.messages.at(-1);
  const failedResponse = !!sessionId && !!lastMessage && lastMessage.role === 'user' && !session?.answer;

  return <section className="assistant-page">
    <div className="page-heading assistant-page-heading">
      <div><div className="eyebrow">AI-first IT support</div><h1>Support assistant</h1><p className="page-subtitle">Troubleshoot with approved IT guidance first. Create a support ticket only if a person needs to step in.</p></div>
      {sessionId ? <Link href="/assistant" className="button secondary"><RotateCcw size={14} /> New conversation</Link> : null}
    </div>
    <div className="notice assistant-privacy"><strong>Privacy:</strong> When you send a message, its text is sent to the configured OpenAI service and relevant source passages may be included. Don’t share passwords, recovery codes, access tokens, or sensitive personal information.</div>

    {!sessionId ? <div className="assistant-home-grid">
      <section className="panel assistant-start-panel">
        <div className="assistant-start-top"><div className="assistant-orb"><Bot size={23} /></div><div><span className="assistant-kicker">IT SUPPORT, STARTING WITH YOU</span><h2>What’s getting in the way?</h2><p>Describe the issue in your own words. I’ll ask relevant questions, check approved support articles, and show the sources behind any suggestion.</p></div></div>
        <form className="assistant-compose assistant-compose-start" onSubmit={submit}>
          <label htmlFor="assistant-first-message">Describe your IT issue</label>
          <textarea id="assistant-first-message" value={message} onChange={(event) => setMessage(event.target.value)} maxLength={4000} placeholder="For example: I can’t connect to the VPN after changing my password." data-testid="input-assistant-message" />
          {error ? <div className="auth-error" role="alert">{error}</div> : null}
          <div className="assistant-compose-footer"><span>Don’t include passwords or other secrets.</span><button className="button" type="submit" disabled={isBusy || message.trim().length < 2} data-testid="button-start-assistant">{isBusy ? <><LoaderCircle size={14} /> Starting…</> : <><Sparkles size={14} /> Start troubleshooting <ArrowRight size={14} /></>}</button></div>
        </form>
        <div className="assistant-quick-starts"><span>Try a scenario</span><div>{quickStarts.map((prompt) => <button key={prompt} onClick={() => setMessage(prompt)}>{prompt}</button>)}</div></div>
        <div className="assistant-manual-link">Prefer a standard request? <Link href="/new-ticket">Create a ticket directly</Link></div>
      </section>
      <aside className="panel assistant-process-panel">
        <div className="panel-head"><div><h2 className="panel-title">How this works</h2><p className="panel-kicker">No unsupported answers or invented sources</p></div><Activity size={15} color="hsl(var(--primary))" /></div>
        <div className="assistant-process-list">
          <div><span className="process-number">01</span><div><strong>Understand the issue</strong><p>The assistant asks only useful follow-up questions.</p></div></div>
          <div><span className="process-number">02</span><div><strong>Search approved guidance</strong><p>Relevant documents are retrieved locally and cited.</p></div></div>
          <div><span className="process-number">03</span><div><strong>Resolve or route</strong><p>Confirm a successful fix or review the smart ticket before it is created.</p></div></div>
        </div>
        <div className="assistant-demo-note"><ShieldAlert size={14} /><span>Security concerns and potentially risky issues are routed to people instead of receiving unsafe self-service steps.</span></div>
      </aside>
    </div> : sessionQuery.isLoading ? <div className="panel"><div className="assistant-loading"><LoaderCircle size={18} /> Resuming your conversation…</div></div> : sessionQuery.isError || !session ? <div className="panel assistant-session-error"><strong>We couldn’t open this conversation.</strong><p>{sessionQuery.isError ? errorText(sessionQuery.error) : 'It may have been removed or you may not have access.'}</p><button className="button secondary small" onClick={() => sessionQuery.refetch()}>Try again</button></div> : <div className="assistant-session-grid">
      <section className="panel assistant-chat-panel">
        <div className="assistant-chat-header"><div className="assistant-chat-avatar"><Bot size={17} /></div><div><strong>IT support assistant</strong><span>Conversation saved automatically</span></div><span className={`assistant-status assistant-status-${session.status}`}>{nice(session.status)}</span></div>
        <div className="assistant-journey" aria-label="Troubleshooting journey">
          {currentJourney?.map((step, index) => <div className={`journey-step ${step.done ? 'done' : ''} ${step.active ? 'active' : ''}`} key={step.label}><span className="journey-dot">{step.done ? <Check size={10} /> : index + 1}</span><span>{step.label}</span>{index < (currentJourney?.length || 0) - 1 ? <i /> : null}</div>)}
        </div>
        <div className="assistant-messages" aria-live="polite">
          {!session.messages.length ? <div className="assistant-empty-chat"><MessageSquareText size={20} /><p>Share what is happening and the assistant will ask about the details that matter.</p></div> : session.messages.map((item, index) => <article className={`assistant-message ${item.role === 'user' ? 'from-user' : 'from-assistant'}`} key={`${item.created_at}-${index}`}>
            <div className="message-avatar">{item.role === 'user' ? <UserRound size={14} /> : <Bot size={14} />}</div>
            <div className="message-content"><div className="message-meta"><strong>{item.role === 'user' ? 'You' : 'Support assistant'}</strong>{item.kind === 'follow_up' ? <span>One more detail</span> : null}<time>{fmtTime(item.created_at)}</time></div><p>{item.content}</p></div>
          </article>)}
          <div ref={chatEnd} />
        </div>
        {failedResponse ? <div className="assistant-retry"><span>The message is saved, but the assistant response failed.</span><button className="button secondary small" onClick={retry} disabled={isBusy}><RotateCcw size={13} /> Retry response</button></div> : null}
        {error && sessionId ? <div className="assistant-inline-error" role="alert">{error}</div> : null}
        {session.status !== 'resolved' && session.status !== 'escalated' ? <form className="assistant-compose assistant-compose-followup" onSubmit={submit}>
          <textarea aria-label="Your reply" value={message} onChange={(event) => setMessage(event.target.value)} maxLength={4000} placeholder={session.status === 'escalation_preview' ? 'Add any detail you want the support team to see…' : 'Answer the question or describe what is still happening…'} data-testid="input-assistant-reply" />
          <button className="button" type="submit" disabled={isBusy || message.trim().length < 2} data-testid="button-send-assistant-reply">{sendMessage.isPending ? <LoaderCircle size={14} /> : <Send size={14} />} Send</button>
        </form> : null}
      </section>

      <aside className="assistant-detail-column">
        {session.analysis ? <section className="panel assistant-analysis-panel">
          <div className="panel-head"><div><h2 className="panel-title">Issue understanding</h2><p className="panel-kicker">AI-estimated details from this conversation</p></div><Network size={15} color="hsl(var(--primary))" /></div>
          <div className="assistant-summary"><span>PROBLEM SUMMARY</span><strong>{session.analysis.problem_summary}</strong></div>
          <div className="assistant-analysis-grid">
            <div><span>Route to</span><strong>{session.analysis.department}</strong></div>
            <div><span>Category</span><strong>{nice(session.analysis.category)}</strong></div>
            <div><span>Priority</span><strong className={`assistant-priority priority-${session.analysis.priority}`}>{nice(session.analysis.priority)}</strong></div>
            <div><span>Issue type</span><strong>{session.analysis.issue_type || 'Still investigating'}</strong></div>
          </div>
          {session.analysis.priority_reason ? <div className="analysis-reason"><strong>Priority reason</strong><p>{session.analysis.priority_reason}</p></div> : null}
          {session.analysis.symptoms.length ? <div className="analysis-reason"><strong>Symptoms</strong><p>{session.analysis.symptoms.join(' · ')}</p></div> : null}
          {session.analysis.troubleshooting_attempted.length ? <div className="analysis-reason"><strong>Already tried</strong><ul>{session.analysis.troubleshooting_attempted.map((step) => <li key={step}>{step}</li>)}</ul></div> : null}
          {session.analysis.escalation_reason ? <div className="analysis-escalation"><AlertTriangle size={14} /><div><strong>Why a person may need to step in</strong><p>{session.analysis.escalation_reason}</p></div></div> : null}
        </section> : null}

        {session.answer ? <section className="panel assistant-evidence-panel">
          <div className="panel-head"><div><h2 className="panel-title">Knowledge search</h2><p className="panel-kicker">{session.answer.citations.length ? `${session.answer.citations.length} approved source${session.answer.citations.length === 1 ? '' : 's'} retrieved` : 'No relevant approved source found'}</p></div><FileText size={15} color="hsl(var(--primary))" /></div>
          {session.answer.citations.length ? <div className="assistant-citations"><CitationList citations={session.answer.citations} /></div> : <div className="assistant-no-source"><CircleHelp size={15} /><span>No article met the minimum relevance threshold. The assistant will not invent a solution.</span></div>}
          {session.answer.needs_human_support && session.status === 'solution_proposed' ? <div className="analysis-escalation"><AlertTriangle size={14} /><div><strong>Human support recommended</strong><p>The answer may be incomplete. Review it carefully or request an IT engineer.</p></div></div> : null}
        </section> : null}

        {session.related_tickets.length ? <section className="panel assistant-related-panel">
          <div className="panel-head"><div><h2 className="panel-title">Related incidents</h2><p className="panel-kicker">Matched from prior ticket text using local embeddings</p></div><TicketIcon size={15} color="hsl(var(--primary))" /></div>
          <div className="related-ticket-list">{session.related_tickets.map((item) => <article key={item.id}><Link href={`/tickets/${item.id}`}><strong>{item.number}</strong><span>{item.title}</span><ArrowRight size={13} /></Link><small>{Math.round(item.relevance * 100)}% semantic match · {nice(item.status)}</small>{item.resolution ? <p>{item.resolution}</p> : null}</article>)}</div>
        </section> : null}

        {session.status === 'solution_proposed' ? <section className="panel assistant-decision-panel">
          <div className="decision-icon"><CheckCircle2 size={16} /></div><div><strong>Did that solve your issue?</strong><p>If it did, we’ll save a resolved history record. If not, the assistant will prepare a ticket with the details already collected.</p></div>
          <div className="decision-actions"><button className="button" onClick={() => resolve(true)} disabled={isBusy} data-testid="button-confirm-solved">{confirmResolution.isPending ? <LoaderCircle size={13} /> : <Check size={13} />} Yes, it’s fixed</button><button className="button secondary" onClick={() => resolve(false)} disabled={isBusy} data-testid="button-confirm-unsolved">No, I still need help</button></div>
        </section> : null}

        {session.status === 'escalation_preview' && session.analysis ? <section className="panel assistant-escalation-panel">
          <div className="escalation-heading"><ShieldAlert size={16} /><div><span>HUMAN SUPPORT</span><strong>Review before creating a ticket</strong></div></div>
          <div className="escalation-summary"><div><span>Department</span><strong>{session.analysis.department}</strong></div><div><span>Priority</span><strong>{nice(session.analysis.priority)}</strong></div><div><span>Category</span><strong>{nice(session.analysis.category)}</strong></div></div>
          <p>The ticket will include your conversation, symptoms, steps already tried, AI analysis, related matches, and any actual knowledge sources retrieved.</p>
          <button className="button" onClick={escalate} disabled={isBusy} data-testid="button-create-smart-ticket">{createTicket.isPending ? <><LoaderCircle size={14} /> Creating ticket…</> : <><TicketIcon size={14} /> Create support ticket</>}</button>
        </section> : null}

        {session.status === 'resolved' || session.status === 'escalated' ? <section className={`panel assistant-complete-panel ${session.status}`}>
          {session.status === 'resolved' ? <CheckCircle2 size={17} /> : <TicketIcon size={17} />}
          <div><strong>{session.status === 'resolved' ? 'Marked as resolved' : 'Ticket created'}</strong><p>{session.ticket_number ? `History saved as ${session.ticket_number}.` : 'Your conversation has been saved.'}{session.assigned_engineer ? ` Assigned to ${session.assigned_engineer.name}.` : ''}</p>{session.ticket_id ? <Link href={`/tickets/${session.ticket_id}`} className="button secondary small">View ticket <ArrowRight size={12} /></Link> : null}</div>
        </section> : null}
      </aside>
    </div>}

    {!sessionId && sessionsQuery.data?.length ? <section className="panel assistant-history">
      <div className="panel-head"><div><h2 className="panel-title">Recent troubleshooting</h2><p className="panel-kicker">Resume a saved conversation or review its outcome</p></div><Activity size={15} color="hsl(var(--muted-foreground))" /></div>
      <div className="assistant-history-list">{sessionsQuery.data.slice(0, 5).map((item) => <Link className="assistant-history-item" href={`/assistant/${item.id}`} key={item.id}>
        <span className={`assistant-history-mark status-${item.status}`}>{item.status === 'resolved' ? <CheckCircle2 size={14} /> : item.status === 'escalated' ? <TicketIcon size={14} /> : <MessageSquareText size={14} />}</span>
        <span className="assistant-history-title"><strong>{item.analysis?.problem_summary || item.messages.find((entry) => entry.role === 'user')?.content || 'New troubleshooting session'}</strong><small>{item.ticket_number || nice(item.status)} · {fmtTime(item.updated_at)}</small></span><ArrowRight size={14} />
      </Link>)}</div>
    </section> : null}
  </section>;
}
