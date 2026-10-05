import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { Link, Route, Switch, useLocation, useParams, Router as WouterRouter } from 'wouter';
import {
  Activity, ArrowDown, ArrowLeft, ArrowRight, ArrowUpRight, Bell, BriefcaseBusiness, Check,
  CheckCircle2, ChevronDown, CircleHelp, Clock3, FilePlus2, Filter, Gauge, Headphones,
  Layers3, ListFilter, LoaderCircle, LogOut, MessageSquareText, Monitor, Plus, Search,
  Send, ShieldCheck, Ticket as TicketIcon, UserRound, Users, Wifi, X,
} from 'lucide-react';
import {
  getGetCurrentUserQueryKey, getGetDashboardSummaryQueryKey, getGetTicketQueryKey,
  getListRecentActivityQueryKey, getListTicketCommentsQueryKey, getListTicketsQueryKey,
  getListUsersQueryKey, setAuthTokenGetter, useCreateTicket, useCreateTicketComment,
  useGetCurrentUser, useGetDashboardSummary, useGetTicket, useHealthCheck,
  useListRecentActivity, useListTicketComments, useListTickets, useListUsers, useLogin,
  useRegister, useUpdateTicket,
} from '@workspace/api-client-react';
import {
  TicketCategory, TicketPriority, TicketStatus,
  type ActivityItem, type AuthResponse, type DashboardSummary, type Ticket,
  type TicketCategory as TicketCategoryType, type TicketPriority as TicketPriorityType,
  type TicketStatus as TicketStatusType, type User,
} from '@workspace/api-client-react';

const TOKEN_KEY = 'smart-help-desk.access-token';
const client = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 20_000 } } });
setAuthTokenGetter(() => localStorage.getItem(TOKEN_KEY));

const categories = Object.values(TicketCategory);
const priorities = Object.values(TicketPriority);
const statuses = Object.values(TicketStatus);
const nice = (value?: string | null) => value ? value.replaceAll('_', ' ') : 'Unassigned';
const initials = (name?: string) => (name || '?').trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase();
const formatDate = (date?: string | null, withTime = false) => {
  if (!date) return '—';
  const parsed = new Date(date);
  if (Number.isNaN(parsed.getTime())) return date;
  return new Intl.DateTimeFormat(undefined, withTime ? { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' } : { month: 'short', day: 'numeric', year: 'numeric' }).format(parsed);
};
const elapsed = (date: string) => {
  const hours = Math.max(0, Math.floor((Date.now() - new Date(date).getTime()) / 3_600_000));
  if (hours < 1) return 'Just now';
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
};
const showError = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Please try again.';

function App() {
  return <QueryClientProvider client={client}>
    <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
      <Router />
    </WouterRouter>
  </QueryClientProvider>;
}

function Router() {
  const [path, navigate] = useLocation();
  useEffect(() => { if (path === '/') navigate(localStorage.getItem(TOKEN_KEY) ? '/dashboard' : '/login'); }, [path, navigate]);
  return <Switch>
    <Route path="/login" component={LoginPage} />
    <Route path="/dashboard"><Protected><DashboardPage /></Protected></Route>
    <Route path="/tickets"><Protected><TicketsPage /></Protected></Route>
    <Route path="/tickets/:ticketId"><Protected><TicketDetailPage /></Protected></Route>
    <Route path="/new-ticket"><Protected><NewTicketPage /></Protected></Route>
    <Route><NotFound /></Route>
  </Switch>;
}

function Protected({ children }: { children: ReactNode }) {
  const [, setLocation] = useLocation();
  const token = localStorage.getItem(TOKEN_KEY);
  const userQuery = useGetCurrentUser({ query: { enabled: !!token, queryKey: getGetCurrentUserQueryKey() } });
  const qc = useQueryClient();
  useEffect(() => {
    if (!token) setLocation('/login');
    if (userQuery.isError) {
      localStorage.removeItem(TOKEN_KEY);
      qc.clear();
      setLocation('/login');
    }
  }, [token, userQuery.isError, qc, setLocation]);
  if (!token) return <ScreenLoading />;
  if (userQuery.isLoading || !userQuery.data) return <ScreenLoading />;
  return <AppShell user={userQuery.data}>{children}</AppShell>;
}

function AppShell({ user, children }: { user: User; children: ReactNode }) {
  const [, setLocation] = useLocation();
  const qc = useQueryClient();
  const logout = () => {
    localStorage.removeItem(TOKEN_KEY);
    qc.clear();
    setLocation('/login');
  };
  const navigation = [
    { href: '/dashboard', label: 'Overview', icon: Gauge },
    { href: '/tickets', label: 'Ticket queue', icon: Layers3 },
    { href: '/new-ticket', label: 'Submit a request', icon: FilePlus2 },
  ];
  const activePath = window.location.pathname;
  return <div className="shell">
    <aside className="sidebar">
      <Brand />
      <div className="nav-label">Workspace</div>
      <nav aria-label="Main navigation">{navigation.map(({ href, label, icon: Icon }) => <Link key={href} href={href} className={`nav-link ${activePath === href || (href === '/tickets' && activePath.startsWith('/tickets/')) ? 'active' : ''}`} data-testid={`link-nav-${label.toLowerCase().replaceAll(' ', '-')}`}><Icon size={16} strokeWidth={1.8} /><span>{label}</span></Link>)}</nav>
      <div className="sidebar-bottom">
        <div className="side-help"><CircleHelp size={17} color="#d7b681" /><p>Need a hand? Your IT team is here to help you get back to work.</p><Link href="/new-ticket">Contact support <ArrowUpRight size={12} /></Link></div>
        <div className="user-chip"><div className="avatar">{initials(user.name)}</div><div><strong data-testid="text-current-user">{user.name}</strong><span>{nice(user.role)}</span></div><button className="logout" title="Sign out" aria-label="Sign out" onClick={logout} data-testid="button-sign-out"><LogOut size={15} /></button></div>
      </div>
    </aside>
    <div className="main-area">
      <div className="mobile-top"><Brand /><button onClick={logout} className="logout" aria-label="Sign out"><LogOut size={17} /></button></div>
      <header className="topbar"><div className="crumb">Help desk <span aria-hidden="true">/</span> <b>{titleForPath(activePath)}</b></div><div className="top-actions"><span className="mono" style={{ fontSize: 9, color: 'hsl(var(--muted-foreground))' }}>IT SERVICE DESK</span><div className="avatar" style={{ width: 30, height: 30, flexBasis: 30 }}>{initials(user.name)}</div></div></header>
      <main className="main-content">{children}</main>
    </div>
  </div>;
}

function Brand() {
  return <Link href="/dashboard" className="brand"><span className="brand-mark"><Headphones size={19} strokeWidth={2.2} /></span><span><span className="brand-name">Smart Help Desk</span><span className="brand-sub">Technology support</span></span></Link>;
}
function titleForPath(path: string) {
  if (path === '/dashboard') return 'Overview';
  if (path === '/tickets') return 'Ticket queue';
  if (path === '/new-ticket') return 'Submit a request';
  if (path.startsWith('/tickets/')) return 'Ticket details';
  return 'Workspace';
}
function ScreenLoading() {
  return <div style={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', background: 'hsl(var(--background))' }}><div style={{ width: 290 }}><div className="skeleton skeleton-line" style={{ width: 112, height: 16 }} /><div className="skeleton skeleton-line" style={{ width: 240, height: 28 }} /><div className="skeleton skeleton-line" style={{ width: 170 }} /></div></div>;
}
function PageError({ error, retry }: { error: unknown; retry: () => void }) {
  return <div className="error-state"><div className="state-mark"><Wifi size={20} /></div><strong>We couldn’t load this view</strong><div>{showError(error)}</div><button className="button secondary small" onClick={retry} style={{ marginTop: 15 }} data-testid="button-retry">Try again</button></div>;
}
function LoadingRows({ count = 4 }: { count?: number }) {
  return <div style={{ padding: '5px 20px 16px' }} aria-label="Loading"><div className="skeleton skeleton-line" style={{ width: 90 }} />{Array.from({ length: count }, (_, index) => <div key={index} className="skeleton skeleton-line" style={{ height: 35, margin: '16px 0' }} />)}</div>;
}
function MetricCard({ label, value, note, icon: Icon, alert = false }: { label: string; value: number; note: string; icon: typeof TicketIcon; alert?: boolean }) {
  return <div className="metric" data-testid={`metric-${label.toLowerCase().replaceAll(' ', '-')}`}><div className="metric-top"><span>{label}</span><span className="metric-icon" style={alert ? { background: '#f8e3de', color: '#a64639' } : undefined}><Icon size={14} /></span></div><div className="metric-value">{value}</div><div className="metric-note">{note}</div></div>;
}
function StatusPill({ status }: { status: string }) { return <span className={`pill status-${status}`}>{nice(status)}</span>; }
function PriorityPill({ priority }: { priority: string }) { return <span className={`pill priority-${priority}`}>{priority}</span>; }

function DashboardPage() {
  const summary = useGetDashboardSummary({ query: { queryKey: getGetDashboardSummaryQueryKey() } });
  const activity = useListRecentActivity({ limit: 7 }, { query: { queryKey: getListRecentActivityQueryKey({ limit: 7 }) } });
  const tickets = useListTickets({ page: 1, page_size: 5 }, { query: { queryKey: getListTicketsQueryKey({ page: 1, page_size: 5 }) } });
  const health = useHealthCheck({ query: { queryKey: ['/api/healthz'] } });
  const [location] = useLocation();
  if (summary.isLoading || activity.isLoading || tickets.isLoading) return <><div className="page-heading"><div><div className="eyebrow">Workspace overview</div><h1>Good to see you.</h1></div></div><div className="metrics">{[0, 1, 2, 3].map((n) => <div key={n} className="skeleton-card" />)}</div><div className="panel"><LoadingRows /></div></>;
  if (summary.isError) return <PageError error={summary.error} retry={() => summary.refetch()} />;
  const data = summary.data as DashboardSummary;
  const topTickets = tickets.data?.items || [];
  const activities = activity.data || [];
  const categoryMax = Math.max(1, ...(data.by_category || []).map((item) => item.count));
  const departmentMax = Math.max(1, ...(data.by_department || []).map((item) => item.count));
  return <section key={location}>
    <div className="page-heading"><div><div className="eyebrow">Workspace overview · {new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric' }).format(new Date())}</div><h1>Good to see you.</h1><p className="page-subtitle">Here’s what’s moving across your help desk today.</p></div><Link href="/new-ticket" className="button" data-testid="link-create-ticket"><Plus size={15} /> New request</Link></div>
    <div className="metrics">
      <MetricCard label="Open tickets" value={data.open_tickets} note="Need attention from the team" icon={TicketIcon} />
      <MetricCard label="Resolved" value={data.resolved_tickets} note="Marked resolved" icon={CheckCircle2} />
      <MetricCard label="Closed" value={data.closed_tickets} note="Completed requests" icon={Check} />
      <MetricCard label="Urgent" value={data.urgent_tickets} note="Prioritized for response" icon={ArrowUpRight} alert />
    </div>
    <div className="grid-main">
      <section className="panel">
        <div className="panel-head"><div><h2 className="panel-title">Recent tickets</h2><p className="panel-kicker">Latest requests across your queue</p></div><Link href="/tickets" className="text-link">View queue <ArrowRight size={13} /></Link></div>
        {tickets.isError ? <PageError error={tickets.error} retry={() => tickets.refetch()} /> : topTickets.length ? <div className="ticket-list">{topTickets.map((ticket) => <TicketRow key={ticket.id} ticket={ticket} />)}</div> : <EmptyState icon={<TicketIcon size={19} />} title="Your queue is clear" body="There are no tickets to show right now." action={<Link href="/new-ticket" className="text-link">Submit a request <ArrowRight size={13} /></Link>} /> }
      </section>
      <section className="panel">
        <div className="panel-head"><div><h2 className="panel-title">Recent activity</h2><p className="panel-kicker">A live trail of ticket updates</p></div><Activity size={15} color="hsl(var(--muted-foreground))" /></div>
        {activity.isError ? <PageError error={activity.error} retry={() => activity.refetch()} /> : activities.length ? <ActivityFeed items={activities} /> : <EmptyState icon={<Activity size={19} />} title="No activity yet" body="Ticket updates will appear here." />}
      </section>
    </div>
    <div className="section-row">
      <section className="panel"><div className="panel-head"><div><h2 className="panel-title">Requests by category</h2><p className="panel-kicker">Where support is most needed</p></div><ListFilter size={15} color="hsl(var(--muted-foreground))" /></div>{data.by_category?.length ? <BarList items={data.by_category} max={categoryMax} /> : <EmptyState title="No category data" body="Category breakdown will appear as tickets are reported." />}</section>
      <section className="panel"><div className="panel-head"><div><h2 className="panel-title">Engineer workload</h2><p className="panel-kicker">Currently assigned open tickets</p></div><Users size={15} color="hsl(var(--muted-foreground))" /></div>{data.engineer_workload?.length ? <div style={{ padding: '8px 20px 12px' }}>{data.engineer_workload.map((entry) => <div className="workload-item" key={entry.engineer.id}><div className="avatar" style={{ width: 29, height: 29, flexBasis: 29 }}>{initials(entry.engineer.name)}</div><span className="workload-name">{entry.engineer.name}</span><span className="workload-count">{entry.open_tickets} open</span></div>)}</div> : <EmptyState title="No workload data" body="Engineer assignments will appear here." />}</section>
    </div>
    {data.by_department?.length ? <section className="panel" style={{ marginTop: 18 }}><div className="panel-head"><div><h2 className="panel-title">Requests by department</h2><p className="panel-kicker">Tickets grouped by requesting department</p></div><BriefcaseBusiness size={15} color="hsl(var(--muted-foreground))" /></div><BarList items={data.by_department} max={departmentMax} /></section> : null}
    <div className="mono" style={{ display: 'flex', justifyContent: 'flex-end', gap: 6, alignItems: 'center', marginTop: 15, fontSize: 9, color: 'hsl(var(--muted-foreground))' }}><span style={{ width: 6, height: 6, borderRadius: '50%', background: health.isError ? '#b45b4c' : '#5c927d' }} /> Service {health.isError ? 'unreachable' : health.data?.status || 'checking'}</div>
  </section>;
}
function TicketRow({ ticket }: { ticket: Ticket }) {
  return <div className="ticket-row"><div className="ticket-main"><Link href={`/tickets/${ticket.id}`} className="ticket-title" data-testid={`link-ticket-${ticket.id}`}>{ticket.title}</Link><div className="ticket-meta"><span className="ticket-number">{ticket.number}</span><span>·</span><span>{ticket.requester.name}</span><span>·</span><span>{elapsed(ticket.updated_at)}</span></div></div><StatusPill status={ticket.status} /></div>;
}
function ActivityFeed({ items }: { items: ActivityItem[] }) {
  return <div className="activity-list">{items.map((item) => <div className="activity-item" key={item.id} data-testid={`activity-item-${item.id}`}><span className="activity-dot"><Activity size={12} /></span><div className="activity-copy"><strong>{item.actor.name}</strong> {item.action} <Link href={`/tickets/${item.ticket_id}`}>{item.ticket_number}</Link>{item.detail ? <> · {item.detail}</> : null}<div className="activity-time">{formatDate(item.created_at, true)}</div></div></div>)}</div>;
}
function BarList({ items, max }: { items: { label: string; count: number }[]; max: number }) {
  return <div className="bar-list">{items.map((item) => <div className="bar-item" key={item.label}><span className="bar-label">{nice(item.label)}</span><div className="bar-track"><div className="bar-fill" style={{ width: `${Math.max(1, (item.count / max) * 100)}%` }} /></div><span className="bar-count">{item.count}</span></div>)}</div>;
}
function EmptyState({ icon, title, body, action }: { icon?: ReactNode; title: string; body: string; action?: ReactNode }) {
  return <div className="empty-state"><div className="state-mark">{icon || <Monitor size={19} />}</div><strong>{title}</strong><div>{body}</div>{action ? <div style={{ marginTop: 13 }}>{action}</div> : null}</div>;
}

function TicketsPage() {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [priority, setPriority] = useState('');
  const [category, setCategory] = useState('');
  const [page, setPage] = useState(1);
  const params = useMemo(() => ({
    page, page_size: 10,
    ...(query ? { q: query } : {}),
    ...(status ? { status: status as TicketStatusType } : {}),
    ...(priority ? { priority: priority as TicketPriorityType } : {}),
    ...(category ? { category: category as TicketCategoryType } : {}),
  }), [page, query, status, priority, category]);
  const result = useListTickets(params, { query: { queryKey: getListTicketsQueryKey(params) } });
  const data = result.data;
  const pages = Math.max(1, Math.ceil((data?.total || 0) / (data?.page_size || 10)));
  const runSearch = (event: FormEvent) => { event.preventDefault(); setPage(1); setQuery(search.trim()); };
  const clearFilters = () => { setSearch(''); setQuery(''); setStatus(''); setPriority(''); setCategory(''); setPage(1); };
  return <section>
    <div className="page-heading"><div><div className="eyebrow">Service requests</div><h1>Ticket queue</h1><p className="page-subtitle">Search, sort, and follow the requests in your workspace.</p></div><Link href="/new-ticket" className="button"><Plus size={15} /> New request</Link></div>
    <form className="filters" onSubmit={runSearch}><div className="search-wrap"><Search size={15} /><input className="field" type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search tickets..." aria-label="Search tickets" data-testid="input-ticket-search" /></div>
      <select className="select" aria-label="Filter by status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} data-testid="select-status"><option value="">All statuses</option>{statuses.map((item) => <option key={item} value={item}>{nice(item)}</option>)}</select>
      <select className="select" aria-label="Filter by priority" value={priority} onChange={(event) => { setPriority(event.target.value); setPage(1); }} data-testid="select-priority"><option value="">All priorities</option>{priorities.map((item) => <option key={item} value={item}>{nice(item)}</option>)}</select>
      <select className="select" aria-label="Filter by category" value={category} onChange={(event) => { setCategory(event.target.value); setPage(1); }} data-testid="select-category"><option value="">All categories</option>{categories.map((item) => <option key={item} value={item}>{nice(item)}</option>)}</select>
      <button className="button small" type="submit"><Search size={13} /> Search</button><button className="button quiet small" type="button" onClick={clearFilters}><X size={13} /> Clear</button>
    </form>
    <div className="panel">
      {result.isLoading ? <LoadingRows count={7} /> : result.isError ? <PageError error={result.error} retry={() => result.refetch()} /> : data?.items.length ? <>
        <div className="table-wrap"><table className="ticket-table"><thead><tr><th>Ticket</th><th>Requester</th><th>Category</th><th>Priority</th><th>Status</th><th>Updated</th></tr></thead><tbody>{data.items.map((ticket) => <tr key={ticket.id} data-testid={`row-ticket-${ticket.id}`}><td><Link href={`/tickets/${ticket.id}`} className="table-ticket">{ticket.title}</Link><span className="table-num">{ticket.number}</span></td><td>{ticket.requester.name}<div className="muted-text" style={{ fontSize: 9, marginTop: 3 }}>{ticket.department}</div></td><td className="muted-text" style={{ textTransform: 'capitalize' }}>{nice(ticket.category)}</td><td><PriorityPill priority={ticket.priority} /></td><td><StatusPill status={ticket.status} /></td><td className="muted-text">{formatDate(ticket.updated_at)}</td></tr>)}</tbody></table></div>
        <div className="pagination"><span>Showing {data.total ? (data.page - 1) * data.page_size + 1 : 0}–{Math.min(data.page * data.page_size, data.total)} of {data.total} requests</span><div className="pagination-controls"><button className="page-button" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))} aria-label="Previous page"><ArrowLeft size={13} /></button><span className="page-button" style={{ display: 'grid', placeItems: 'center' }}>{data.page} / {pages}</span><button className="page-button" disabled={page >= pages} onClick={() => setPage((current) => current + 1)} aria-label="Next page"><ArrowRight size={13} /></button></div></div>
      </> : <EmptyState icon={<Filter size={19} />} title="No matching tickets" body="Try another search or clear the filters to see more requests." action={<button onClick={clearFilters} className="button secondary small">Clear filters</button>} />}
    </div>
  </section>;
}

function NewTicketPage() {
  const [, setLocation] = useLocation();
  const qc = useQueryClient();
  const mutation = useCreateTicket();
  const [error, setError] = useState('');
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    const form = new FormData(event.currentTarget);
    mutation.mutate({ data: {
      title: String(form.get('title') || '').trim(),
      description: String(form.get('description') || '').trim(),
      category: String(form.get('category')) as TicketCategoryType,
      priority: String(form.get('priority')) as TicketPriorityType,
      department: String(form.get('department') || '').trim(),
    } }, { onSuccess: (ticket) => {
      qc.invalidateQueries({ queryKey: getListTicketsQueryKey() });
      qc.invalidateQueries({ queryKey: getGetDashboardSummaryQueryKey() });
      qc.invalidateQueries({ queryKey: getListRecentActivityQueryKey() });
      setLocation(`/tickets/${ticket.id}`);
    }, onError: (reason) => setError(showError(reason)) });
  };
  return <section><div className="page-heading"><div><div className="eyebrow">Help us get you back to work</div><h1>Submit a request</h1><p className="page-subtitle">A clear description helps us route your issue to the right person.</p></div><Link href="/tickets" className="button secondary"><ArrowLeft size={14} /> Back to queue</Link></div>
    <div className="notice"><strong>Before you begin:</strong> Include what you were trying to do, what happened instead, and any error message you saw.</div>
    <form className="form-card" onSubmit={submit} data-testid="form-new-ticket">
      <div className="form-grid">
        <div className="form-field full"><label htmlFor="ticket-title">Request title</label><input id="ticket-title" name="title" required minLength={5} maxLength={180} placeholder="For example, “Can’t connect to the office printer”" data-testid="input-ticket-title" /></div>
        <div className="form-field"><label htmlFor="ticket-category">Category</label><select id="ticket-category" name="category" required defaultValue="software" data-testid="select-ticket-category">{categories.map((item) => <option key={item} value={item}>{nice(item)}</option>)}</select></div>
        <div className="form-field"><label htmlFor="ticket-priority">Priority</label><select id="ticket-priority" name="priority" defaultValue="normal" data-testid="select-ticket-priority"><option value="low">Low — can wait</option><option value="normal">Normal — standard request</option><option value="high">High — blocking work</option><option value="urgent">Urgent — critical disruption</option></select></div>
        <div className="form-field full"><label htmlFor="ticket-department">Department</label><input id="ticket-department" name="department" required minLength={2} maxLength={120} placeholder="Your team or department" data-testid="input-ticket-department" /></div>
        <div className="form-field full"><label htmlFor="ticket-description">What’s happening?</label><textarea id="ticket-description" name="description" required minLength={10} maxLength={12000} placeholder="Tell us what you were doing, what you expected, and what happened instead." data-testid="input-ticket-description" /><small>Do not include passwords or sensitive personal information.</small></div>
      </div>
      {error ? <p role="alert" className="auth-error" style={{ marginTop: 18 }}>{error}</p> : null}
      <div className="form-actions"><span className="muted-text" style={{ fontSize: 10 }}>Required fields must be completed.</span><button className="button" type="submit" disabled={mutation.isPending} data-testid="button-submit-ticket">{mutation.isPending ? <><LoaderCircle size={14} /> Sending request…</> : <><Send size={14} /> Send request</>}</button></div>
    </form>
  </section>;
}

function TicketDetailPage() {
  const params = useParams<{ ticketId: string }>();
  const ticketId = params.ticketId || '';
  const ticketQuery = useGetTicket(ticketId, { query: { queryKey: getGetTicketQueryKey(ticketId), enabled: !!ticketId } });
  const commentsQuery = useListTicketComments(ticketId, { query: { queryKey: getListTicketCommentsQueryKey(ticketId), enabled: !!ticketId } });
  const userQuery = useGetCurrentUser({ query: { queryKey: getGetCurrentUserQueryKey() } });
  const usersQuery = useListUsers({ role: 'support_engineer' }, { query: { queryKey: getListUsersQueryKey({ role: 'support_engineer' }), enabled: userQuery.data?.role !== 'employee' } });
  const update = useUpdateTicket();
  const addComment = useCreateTicketComment();
  const qc = useQueryClient();
  const [body, setBody] = useState('');
  const [resolution, setResolution] = useState('');
  const [error, setError] = useState('');
  const ticket = ticketQuery.data;
  useEffect(() => { if (ticket?.resolution) setResolution(ticket.resolution); }, [ticket?.id, ticket?.resolution]);
  const isEngineer = userQuery.data?.role !== 'employee';
  const patch = (data: Parameters<typeof update.mutate>[0]['data']) => {
    update.mutate({ ticketId, data }, { onSuccess: (next) => {
      qc.setQueryData(getGetTicketQueryKey(ticketId), next);
      qc.invalidateQueries({ queryKey: getListTicketsQueryKey() });
      qc.invalidateQueries({ queryKey: getGetDashboardSummaryQueryKey() });
      qc.invalidateQueries({ queryKey: getListRecentActivityQueryKey() });
      setError('');
    }, onError: (reason) => setError(showError(reason)) });
  };
  const submitComment = (event: FormEvent) => {
    event.preventDefault();
    if (!body.trim()) return;
    addComment.mutate({ ticketId, data: { body: body.trim() } }, { onSuccess: () => {
      setBody('');
      qc.invalidateQueries({ queryKey: getListTicketCommentsQueryKey(ticketId) });
      qc.invalidateQueries({ queryKey: getListRecentActivityQueryKey() });
    }, onError: (reason) => setError(showError(reason)) });
  };
  if (ticketQuery.isLoading) return <div className="panel"><LoadingRows count={5} /></div>;
  if (ticketQuery.isError) return <PageError error={ticketQuery.error} retry={() => ticketQuery.refetch()} />;
  if (!ticket) return <EmptyState title="Ticket not found" body="This request may have been removed or you may not have access." action={<Link href="/tickets" className="button secondary small">Back to queue</Link>} />;
  const assignableUsers = usersQuery.data || [];
  return <section>
    <div className="page-heading"><div><div className="eyebrow">Request detail · <span className="mono">{ticket.number}</span></div><h1 style={{ fontSize: 28 }}>Ticket details</h1><p className="page-subtitle">Follow progress and keep the conversation in one place.</p></div><Link href="/tickets" className="button secondary"><ArrowLeft size={14} /> Ticket queue</Link></div>
    {error ? <div className="auth-error" role="alert">{error}</div> : null}
    <div className="detail-layout">
      <div>
        <section className="panel detail-panel">
          <div className="detail-title-row"><div><div className="detail-number">{ticket.number}</div><h2>{ticket.title}</h2></div><StatusPill status={ticket.status} /></div>
          <div className="detail-properties">
            <div className="property"><span>Requester</span><strong>{ticket.requester.name}</strong></div>
            <div className="property"><span>Category</span><strong style={{ textTransform: 'capitalize' }}>{nice(ticket.category)}</strong></div>
            <div className="property"><span>Priority</span><PriorityPill priority={ticket.priority} /></div>
          </div>
          <p className="detail-desc">{ticket.description}</p>
          {ticket.resolution ? <div style={{ marginTop: 20, padding: 15, background: '#e8f0e4', borderRadius: 9 }}><div style={{ fontSize: 10, fontWeight: 700, color: '#4b7447', marginBottom: 6 }}><CheckCircle2 size={13} style={{ verticalAlign: 'middle', marginRight: 5 }} /> Resolution</div><p style={{ fontSize: 11, lineHeight: 1.6, margin: 0, color: '#52684f' }}>{ticket.resolution}</p></div> : null}
        </section>
        <section className="panel comments" style={{ marginTop: 17 }}>
          <div className="panel-head"><div><h2 className="panel-title">Conversation</h2><p className="panel-kicker">Updates between you and support</p></div><MessageSquareText size={15} color="hsl(var(--muted-foreground))" /></div>
          {commentsQuery.isLoading ? <LoadingRows count={2} /> : commentsQuery.isError ? <PageError error={commentsQuery.error} retry={() => commentsQuery.refetch()} /> : commentsQuery.data?.length ? <div style={{ padding: '2px 20px 0' }}>{commentsQuery.data.map((comment) => <div className="comment" key={comment.id}><div className="avatar" style={{ width: 29, height: 29, flexBasis: 29 }}>{initials(comment.author.name)}</div><div className="comment-content"><div className="comment-top"><strong>{comment.author.name}</strong><time>{formatDate(comment.created_at, true)}</time></div><p className="comment-body">{comment.body}</p></div></div>)}</div> : <EmptyState icon={<MessageSquareText size={18} />} title="No updates yet" body="Send a message to start the conversation." />}
          <form className="comment-form" onSubmit={submitComment} style={{ padding: '0 20px 20px' }}><textarea aria-label="Write an update" value={body} onChange={(event) => setBody(event.target.value)} placeholder="Write an update for the support team…" maxLength={8000} data-testid="input-comment" /><button className="button small" type="submit" disabled={!body.trim() || addComment.isPending} data-testid="button-send-comment">{addComment.isPending ? <LoaderCircle size={13} /> : <Send size={13} />} Send</button></form>
        </section>
      </div>
      <aside className="panel side-panel">
        <h3>Ticket information</h3>
        <div className="side-prop"><label>Status</label>{isEngineer ? <select value={ticket.status} onChange={(event) => patch({ status: event.target.value as TicketStatusType })} data-testid="select-update-status">{statuses.map((item) => <option key={item} value={item}>{nice(item)}</option>)}</select> : <StatusPill status={ticket.status} />}</div>
        <div className="side-prop"><label>Priority</label>{isEngineer ? <select value={ticket.priority} onChange={(event) => patch({ priority: event.target.value as TicketPriorityType })} data-testid="select-update-priority">{priorities.map((item) => <option key={item} value={item}>{nice(item)}</option>)}</select> : <PriorityPill priority={ticket.priority} />}</div>
        <div className="side-prop"><label>Assigned engineer</label>{isEngineer ? <select value={ticket.assigned_engineer?.id || ''} onChange={(event) => patch({ assigned_engineer_id: event.target.value || null })} data-testid="select-assign-engineer"><option value="">Unassigned</option>{assignableUsers.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select> : <div>{ticket.assigned_engineer?.name || 'Not assigned yet'}</div>}</div>
        <div className="side-prop"><label>Department</label><div>{ticket.department}</div></div>
        <div className="side-prop"><label>Created</label><div>{formatDate(ticket.created_at)}</div></div>
        <div className="side-prop"><label>Last updated</label><div>{formatDate(ticket.updated_at)}</div></div>
        {isEngineer ? <div className="side-prop"><label>Resolution notes</label><textarea value={resolution} onChange={(event) => setResolution(event.target.value)} placeholder="Add resolution details…" maxLength={12000} data-testid="input-resolution" /><button className="button small" style={{ marginTop: 8 }} disabled={update.isPending || resolution === (ticket.resolution || '')} onClick={() => patch({ resolution: resolution || null })} data-testid="button-save-resolution">{update.isPending ? 'Saving…' : 'Save resolution'}</button></div> : null}
      </aside>
    </div>
  </section>;
}

function LoginPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [error, setError] = useState('');
  const [, setLocation] = useLocation();
  const qc = useQueryClient();
  const login = useLogin();
  const register = useRegister();
  const pending = login.isPending || register.isPending;
  useEffect(() => { if (localStorage.getItem(TOKEN_KEY)) setLocation('/dashboard'); }, [setLocation]);
  const finishAuth = (response: AuthResponse) => {
    localStorage.setItem(TOKEN_KEY, response.access_token);
    qc.clear();
    qc.setQueryData(getGetCurrentUserQueryKey(), response.user);
    setLocation('/dashboard');
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    const values = new FormData(event.currentTarget);
    if (mode === 'login') {
      login.mutate({ data: { email: String(values.get('email')), password: String(values.get('password')) } }, { onSuccess: finishAuth, onError: (reason) => setError(showError(reason)) });
    } else {
      register.mutate({ data: { name: String(values.get('name')), email: String(values.get('email')), password: String(values.get('password')), department: String(values.get('department')) } }, { onSuccess: finishAuth, onError: (reason) => setError(showError(reason)) });
    }
  };
  return <div className="auth-layout">
    <section className="auth-story"><Brand /><div className="story-copy"><div className="eyebrow">Support that keeps you moving</div><h1>Work shouldn’t stop at “something’s broken.”</h1><p>One place to report the issue, understand what’s happening, and get back to the work that matters.</p></div><div className="story-quote">“A little more visibility makes a big difference to everyone waiting on a fix.”<strong>Smart Help Desk · Technology Support</strong></div></section>
    <main className="auth-main"><div className="auth-box"><div className="eyebrow">SMART HELP DESK</div><h2>{mode === 'login' ? 'Welcome back' : 'Create your account'}</h2><p>{mode === 'login' ? 'Sign in to view your support requests and updates.' : 'Register as an employee to start submitting requests.'}</p>
      <div className="auth-tabs" role="tablist"><button className={`auth-tab ${mode === 'login' ? 'active' : ''}`} onClick={() => { setMode('login'); setError(''); }} role="tab" aria-selected={mode === 'login'} data-testid="tab-sign-in">Sign in</button><button className={`auth-tab ${mode === 'register' ? 'active' : ''}`} onClick={() => { setMode('register'); setError(''); }} role="tab" aria-selected={mode === 'register'} data-testid="tab-register">Create account</button></div>
      <form onSubmit={submit} data-testid="form-auth">{error ? <div className="auth-error" role="alert">{error}</div> : null}<div className="auth-fields">
        {mode === 'register' ? <div className="form-field"><label htmlFor="auth-name">Full name</label><input id="auth-name" name="name" minLength={2} maxLength={120} required placeholder="Your name" autoComplete="name" data-testid="input-auth-name" /></div> : null}
        <div className="form-field"><label htmlFor="auth-email">Work email</label><input id="auth-email" type="email" name="email" required placeholder="you@company.com" autoComplete="email" data-testid="input-auth-email" /></div>
        <div className="form-field"><label htmlFor="auth-password">Password</label><input id="auth-password" type="password" name="password" minLength={mode === 'register' ? 8 : 1} maxLength={128} required placeholder="Enter your password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} data-testid="input-auth-password" /></div>
        {mode === 'register' ? <div className="form-field"><label htmlFor="auth-department">Department</label><input id="auth-department" name="department" minLength={2} maxLength={120} required placeholder="Your team or department" data-testid="input-auth-department" /></div> : null}
      </div><button className="button auth-submit" type="submit" disabled={pending} data-testid="button-auth-submit">{pending ? <><LoaderCircle size={15} /> Please wait…</> : mode === 'login' ? <>Sign in <ArrowRight size={15} /></> : <>Create account <ArrowRight size={15} /></>}</button></form>
      <p style={{ fontSize: 10, lineHeight: 1.6, marginTop: 17 }}>By continuing, you’ll securely access requests available to your account.</p>
    </div></main>
  </div>;
}
function NotFound() {
  return <div className="empty-state" style={{ minHeight: '100dvh', display: 'grid', alignContent: 'center' }}><div className="state-mark"><Search size={18} /></div><strong>That page isn’t here</strong><div>Check the address or return to your help desk.</div><Link href={localStorage.getItem(TOKEN_KEY) ? '/dashboard' : '/login'} className="button" style={{ margin: '18px auto 0' }}>Go to workspace</Link></div>;
}

export default App;
