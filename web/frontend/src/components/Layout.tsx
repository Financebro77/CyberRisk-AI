import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  Bell,
  ChevronDown,
  CircleHelp,
  LayoutDashboard,
  LogOut,
  Moon,
  Search,
  Settings,
  Sun,
  UserRound,
  FileText,
  ShieldHalf,
  Bot,
  Gauge,
  Menu,
  X,
} from 'lucide-react';
import { Logo } from './Logo';
import { RouteTransition } from './RouteTransition';
import { useTheme } from '../lib/useTheme';

const BASE = '/app';

/* --------------------------- nav groups --------------------------- */

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  end?: boolean;
}

const NAV_GROUPS: Array<{ group: string; items: NavItem[] }> = [
  {
    group: 'Workspace',
    items: [{ to: `${BASE}/`, label: 'Dashboard', icon: LayoutDashboard, end: true }],
  },
  {
    group: 'Advisory',
    items: [
      { to: `${BASE}/assess`, label: 'Assessment', icon: Gauge },
      { to: `${BASE}/consult`, label: 'AI Consultant', icon: Bot },
    ],
  },
  {
    group: 'Risk & Insurance',
    items: [
      { to: `${BASE}/optimise`, label: 'Insurance', icon: ShieldHalf },
      { to: `${BASE}/report`, label: 'Reports', icon: FileText },
    ],
  },
];

const FOOTER_ITEMS: NavItem[] = [{ to: `${BASE}/settings`, label: 'Settings', icon: Settings }];

/* --------------------------- sidebar --------------------------- */

function SidebarLink({ to, label, icon: Icon, end, onNavigate }: NavItem & { onNavigate?: () => void }) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onNavigate}
      className={({ isActive }) =>
        `group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200 ${
          isActive
            ? 'bg-brand-600/15 text-brand-400'
            : 'text-ink-400 hover:bg-ink-900/60 hover:text-ink-100'
        }`
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={`absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-brand-500 transition-all duration-200 ${
              isActive ? 'opacity-100' : 'opacity-0'
            }`}
          />
          <Icon className={`h-4 w-4 shrink-0 transition-transform duration-200 ${isActive ? 'scale-110' : 'group-hover:scale-105'}`} />
          {label}
        </>
      )}
    </NavLink>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      <div className="px-5 py-5">
        <Logo variant="dark" />
      </div>

      <nav className="mt-1 flex-1 space-y-5 overflow-y-auto px-3">
        {NAV_GROUPS.map(({ group, items }) => (
          <div key={group}>
            <div className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-500">
              {group}
            </div>
            <div className="space-y-0.5">
              {items.map((item) => (
                <SidebarLink key={item.to} {...item} onNavigate={onNavigate} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="space-y-1 px-3">
        {FOOTER_ITEMS.map((item) => (
          <SidebarLink key={item.to} {...item} onNavigate={onNavigate} />
        ))}
      </div>

      <div className="border-t border-ink-900 px-5 py-4">
        <div className="flex items-center gap-2 text-xs text-ink-500">
          <span className="h-2 w-2 rounded-full bg-risk-low" />
          <span>Engine · DeepSeek ready</span>
        </div>
      </div>
    </>
  );
}

function Sidebar({ collapsed, onClose }: { collapsed: boolean; onClose: () => void }) {
  return (
    <aside
      className={`flex h-full shrink-0 flex-col bg-ink-950 text-ink-300 transition-all duration-300 ${
        collapsed ? 'w-0 opacity-0' : 'w-64 opacity-100'
      }`}
    >
      {!collapsed && <SidebarContent onNavigate={onClose} />}
    </aside>
  );
}

/* --------------------------- top bar --------------------------- */

function SearchBar() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  // Update the visible text and keep the submitted query for the result list.
  const setBoth = (v: string) => {
    setQ(v);
    setQuery(v);
  };

  const results = [
    { label: 'Risk Dashboard', to: `${BASE}/` },
    { label: 'Assessment', to: `${BASE}/assess` },
    { label: 'AI Consultant', to: `${BASE}/consult` },
    { label: 'Insurance', to: `${BASE}/optimise` },
    { label: 'Reports', to: `${BASE}/report` },
    { label: 'Settings', to: `${BASE}/settings` },
  ].filter((r) => r.label.toLowerCase().includes(query.toLowerCase()));

  return (
    <div ref={ref} className="relative hidden w-64 md:block lg:w-80">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
      <input
        value={q}
        onChange={(e) => setBoth(e.target.value)}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && results.length > 0) {
            navigate(results[0].to);
            setQ('');
            setQuery('');
            setOpen(false);
          }
        }}
        placeholder="Search…"
        className="w-full rounded-lg border border-ink-200 bg-ink-50 py-2 pl-9 pr-3 text-sm text-ink-900 outline-none transition-colors placeholder:text-ink-400 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/20"
      />
      {open && q && (
        <div className="absolute left-0 right-0 top-full mt-1 overflow-hidden rounded-lg border border-ink-200 bg-white shadow-lg">
          {results.length === 0 && <div className="px-4 py-3 text-sm text-ink-500">No matches</div>}
          {results.map((r) => (
            <button
              key={r.to}
              type="button"
              onClick={() => {
                navigate(r.to);
                setQ('');
                setQuery('');
                setOpen(false);
              }}
              className="block w-full px-4 py-2 text-left text-sm text-ink-700 transition-colors hover:bg-ink-50"
            >
              {r.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label="Toggle theme"
      className="flex h-9 w-9 items-center justify-center rounded-lg border border-ink-200 bg-white text-ink-500 transition-colors hover:border-brand-500 hover:text-brand-600"
    >
      {theme === 'light' ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
    </button>
  );
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const [unread, setUnread] = useState(3);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, []);

  const items = [
    { id: 1, title: 'Simulation complete', desc: 'Meridian Logistics — 100k paths', tone: 'brand' },
    { id: 2, title: 'Report generated', desc: 'Executive report ready to download', tone: 'brand' },
    { id: 3, title: 'Insurance recommendation', desc: 'New recommended structure available', tone: 'brand' },
  ];

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="Notifications"
        aria-haspopup="true"
        aria-expanded={open}
        className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-ink-200 bg-white text-ink-500 transition-colors hover:border-brand-500 hover:text-brand-600"
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand-600 px-1 text-[10px] font-bold text-white">
            {unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 overflow-hidden rounded-xl border border-ink-200 bg-white shadow-lg">
          <div className="border-b border-ink-100 px-4 py-3">
            <div className="text-sm font-semibold text-ink-900">Notifications</div>
            <div className="text-xs text-ink-500">{unread} unread</div>
          </div>
          <div className="max-h-72 divide-y divide-ink-100 overflow-y-auto">
            {items.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => setUnread((u) => Math.max(0, u - 1))}
                className="block w-full px-4 py-3 text-left transition-colors hover:bg-ink-50"
              >
                <div className="flex items-center gap-2 text-sm font-medium text-ink-800">
                  <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
                  {n.title}
                </div>
                <div className="pl-3.5 text-xs text-ink-500">{n.desc}</div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function UserMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-lg border border-ink-200 bg-white py-1.5 pl-1.5 pr-2.5 transition-colors hover:border-brand-500"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-600 text-xs font-bold text-white">
          JD
        </span>
        <span className="hidden text-left sm:block">
          <span className="block text-xs font-semibold leading-tight text-ink-900">Jane Doe</span>
          <span className="block text-[10px] leading-tight text-ink-500">Risk Analyst</span>
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-ink-400" />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-2 w-56 overflow-hidden rounded-xl border border-ink-200 bg-white shadow-lg">
          <div className="border-b border-ink-100 px-4 py-3">
            <div className="text-sm font-semibold text-ink-900">Jane Doe</div>
            <div className="text-xs text-ink-500">jane.doe@cyberrisk.ai</div>
          </div>
          <div className="p-1.5">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                navigate(`${BASE}/settings`);
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink-700 transition-colors hover:bg-ink-50"
            >
              <UserRound className="h-4 w-4 text-ink-400" /> Profile
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink-700 transition-colors hover:bg-ink-50"
            >
              <CircleHelp className="h-4 w-4 text-ink-400" /> Help
            </button>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                navigate('/');
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink-700 transition-colors hover:bg-ink-50"
            >
              <LogOut className="h-4 w-4 text-ink-400" /> Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Topbar({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-ink-200 bg-white px-4 sm:px-6">
      <div className="flex items-center gap-3">
        {/* Tablet menu toggle */}
        <button
          type="button"
          onClick={onMenuClick}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-ink-200 text-ink-500 lg:hidden"
          aria-label="Toggle menu"
        >
          <Menu className="h-4 w-4" />
        </button>
        <span className="text-sm font-medium text-ink-900">Consulting workspace</span>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        <SearchBar />
        <ThemeToggle />
        <Notifications />
        <UserMenu />
      </div>
    </header>
  );
}

/* --------------------------- layout --------------------------- */

export function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Desktop/tablet sidebar */}
      <div className="hidden lg:block">
        <Sidebar collapsed={false} onClose={() => {}} />
      </div>

      {/* Mobile/tablet overlay sidebar */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div
            className="animate-[fade-in_0.2s_ease] absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 flex shadow-2xl">
            <div className="animate-[panel-in_0.25s_cubic-bezier(0.16,1,0.3,1)]">
              <Sidebar collapsed={false} onClose={() => setMobileOpen(false)} />
            </div>
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="absolute -right-10 top-4 flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 text-white transition-colors hover:bg-white/20"
              aria-label="Close menu"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Topbar onMenuClick={() => setMobileOpen(true)} />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
            <RouteTransition>
              <Outlet />
            </RouteTransition>
          </div>
        </main>
      </div>
    </div>
  );
}
