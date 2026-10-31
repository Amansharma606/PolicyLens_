import React, { useState, useEffect } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { 
  Shield, 
  LayoutDashboard, 
  UploadCloud, 
  Files, 
  MessageSquareQuote, 
  History, 
  Menu, 
  X, 
  Cpu, 
  Activity, 
  CheckCircle2, 
  AlertTriangle,
  LogOut,
  User
} from 'lucide-react';
import { checkHealth } from '../services/api';
import { useAuth } from '../context/AuthContext';

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/upload', label: 'Upload Policy', icon: UploadCloud },
  { path: '/documents', label: 'Policy Library', icon: Files },
  { path: '/chat', label: 'Chat & Ask', icon: MessageSquareQuote },
  { path: '/history', label: 'Conversations', icon: History },
];

export const AppLayout = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [backendStatus, setBackendStatus] = useState({
    connected: false,
    checking: true,
    data: null,
  });
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  const verifyBackend = async () => {
    try {
      const data = await checkHealth();
      setBackendStatus({ connected: true, checking: false, data });
    } catch (err) {
      setBackendStatus({ connected: false, checking: false, data: null });
    }
  };

  useEffect(() => {
    verifyBackend();
    const interval = setInterval(verifyBackend, 15000);
    return () => clearInterval(interval);
  }, []);

  // Close mobile menu on page change
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  const isChatRoute = location.pathname.startsWith('/chat');

  return (
    <div className="flex h-screen h-[100dvh] w-full overflow-hidden bg-slate-50 text-slate-800 font-sans">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex flex-col w-64 h-full bg-slate-900 border-r border-slate-800 text-slate-300 shrink-0 select-none z-20">
        {/* Brand Header */}
        <div className="p-5 border-b border-slate-800/80 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400 shadow-inner shrink-0">
              <Shield className="w-6 h-6 text-amber-400" />
            </div>
            <div className="min-w-0">
              <h1 className="text-xl font-bold text-white tracking-tight leading-none truncate">
                Policy<span className="text-amber-400">Lens</span>
              </h1>
              <p className="text-[11px] text-amber-400/90 font-medium tracking-wide mt-1 uppercase truncate">Local Policy AI</p>
            </div>
          </div>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 px-3 py-4 space-y-1.5 overflow-y-auto overflow-x-hidden min-h-0 chat-scroll">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path || 
              (item.path !== '/' && location.pathname.startsWith(item.path));
            
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3.5 px-3.5 py-2.5 rounded-xl font-medium text-sm transition-all duration-150 ${
                  isActive
                    ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-900/30 font-semibold'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
                }`}
              >
                <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-slate-950 font-bold' : 'text-slate-400 group-hover:text-white'}`} />
                <span className="truncate">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        {/* Local Engine Status Box */}
        <div className="p-3.5 m-3 rounded-2xl bg-slate-800/50 border border-slate-700/60 text-xs text-slate-400 shrink-0">
          <div className="flex items-center justify-between font-semibold text-slate-200 mb-1.5">
            <span className="flex items-center gap-1.5 truncate">
              <Cpu className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              ML Engine
            </span>
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 font-mono shrink-0">
              PyTorch
            </span>
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed mb-2 line-clamp-2">
            Zero external AI APIs. Document-grounded retrieval with custom transformer.
          </p>
          <div className="pt-2 border-t border-slate-700/60 flex items-center justify-between text-[11px]">
            <span className="text-slate-400">Model State:</span>
            <span className="text-slate-200 font-medium truncate ml-1">
              {backendStatus.data?.classifier_trained ? 'Trained' : 'Extractive'}
            </span>
          </div>
        </div>

        {/* Authenticated User Profile & Sign Out (Sidebar Footer) */}
        <div className="p-3 m-3 mt-0 rounded-2xl bg-slate-800/90 border border-slate-700/80 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5 overflow-hidden min-w-0 mr-2">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 text-slate-950 font-bold text-xs flex items-center justify-center shrink-0 shadow-md">
              {user?.avatar || 'PL'}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-white truncate">{user?.name || 'PolicyLens User'}</p>
              <p className="text-[10px] text-amber-400/90 truncate font-mono">{user?.role || 'Analyst'}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-700/60 transition-colors shrink-0"
            title="Sign out of PolicyLens"
            aria-label="Sign Out"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {/* Top Navigation Bar */}
        <header className="h-16 shrink-0 bg-white/95 backdrop-blur-md border-b border-slate-200/80 px-4 sm:px-6 lg:px-8 flex items-center justify-between z-10">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="lg:hidden p-2 rounded-lg text-slate-600 hover:bg-slate-100 shrink-0"
              aria-label="Toggle navigation"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="hidden sm:block min-w-0">
              <span className="text-[11px] font-semibold text-amber-600 uppercase tracking-wider block">PolicyLens Intelligence</span>
              <p className="text-xs sm:text-sm font-medium text-slate-600 truncate">Understand Every Policy. Make Smarter Decisions.</p>
            </div>
            <div className="sm:hidden font-bold text-slate-900 text-base truncate">
              Policy<span className="text-amber-500">Lens</span>
            </div>
          </div>

          {/* Right Header: Connection Status + User Profile */}
          <div className="flex items-center gap-2 sm:gap-3 shrink-0">
            {/* Connection Status Badge */}
            <div
              className={`flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-3 py-1 sm:py-1.5 rounded-full text-xs font-medium border transition-colors shrink-0 ${
                backendStatus.connected
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-rose-50 text-rose-700 border-rose-200'
              }`}
              title={backendStatus.connected ? 'FastAPI Local Backend Active' : 'Backend Unreachable'}
            >
              <span className="relative flex h-2 w-2 shrink-0">
                {backendStatus.connected && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                )}
                <span
                  className={`relative inline-flex rounded-full h-2 w-2 ${
                    backendStatus.connected ? 'bg-emerald-500' : 'bg-rose-500'
                  }`}
                ></span>
              </span>
              <span className="hidden md:inline">
                {backendStatus.connected ? 'Backend Connected' : 'Backend Disconnected'}
              </span>
              <span className="md:hidden text-[11px]">
                {backendStatus.connected ? 'Online' : 'Offline'}
              </span>
            </div>

            {/* User Profile Pill & Sign Out */}
            <div className="flex items-center gap-2 pl-2 border-l border-slate-200 shrink-0">
              <div className="hidden sm:flex items-center gap-2 text-xs text-slate-700 font-medium">
                <span className="w-7 h-7 rounded-lg bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-600 font-bold text-xs shrink-0">
                  {user?.avatar || 'PL'}
                </span>
                <span className="hidden md:inline font-semibold text-slate-800 truncate max-w-[120px]">{user?.name || 'Analyst'}</span>
              </div>
              <button
                onClick={handleLogout}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:text-rose-600 hover:bg-rose-50 border border-slate-200 transition-colors shrink-0"
                title="Sign out of PolicyLens"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Sign Out</span>
              </button>
            </div>
          </div>
        </header>

        {/* Mobile Navigation Drawer */}
        {mobileMenuOpen && (
          <div className="lg:hidden fixed inset-0 z-50 flex">
            <div 
              className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm"
              onClick={() => setMobileMenuOpen(false)}
            />
            <div className="relative flex-1 flex flex-col max-w-xs w-full bg-slate-900 text-slate-300 p-6 z-10 shadow-2xl">
              <div className="flex items-center justify-between pb-6 border-b border-slate-800">
                <div className="flex items-center gap-3">
                  <Shield className="w-6 h-6 text-amber-400" />
                  <span className="text-lg font-bold text-white">
                    Policy<span className="text-amber-400">Lens</span>
                  </span>
                </div>
                <button
                  onClick={() => setMobileMenuOpen(false)}
                  className="p-1 rounded-lg text-slate-400 hover:text-white"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <nav className="flex-1 py-6 space-y-1">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = location.pathname === item.path || 
                    (item.path !== '/' && location.pathname.startsWith(item.path));
                  return (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      className={`flex items-center gap-3.5 px-3 py-2.5 rounded-xl font-medium text-sm ${
                        isActive
                          ? 'bg-amber-500 text-slate-950 font-semibold'
                          : 'text-slate-400 hover:text-white hover:bg-slate-800'
                      }`}
                    >
                      <Icon className="w-4 h-4" />
                      <span>{item.label}</span>
                    </NavLink>
                  );
                })}
              </nav>

              {/* Mobile User Profile Footer */}
              <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-amber-500/20 text-amber-400 font-bold text-xs flex items-center justify-center">
                    {user?.avatar || 'PL'}
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-white">{user?.name || 'User'}</p>
                    <p className="text-[10px] text-amber-400/90">{user?.role || 'Analyst'}</p>
                  </div>
                </div>
                <button
                  onClick={handleLogout}
                  className="p-2 text-rose-400 hover:bg-slate-800 rounded-lg text-xs flex items-center gap-1"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Page Content Container */}
        <main className={`flex-1 min-h-0 w-full h-full ${
          isChatRoute
            ? 'flex flex-col overflow-hidden p-0 bg-white'
            : 'overflow-y-auto p-4 sm:p-8 max-w-7xl mx-auto chat-scroll'
        }`}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};
