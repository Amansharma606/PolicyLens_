import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Shield, Sparkles } from 'lucide-react';
import { Lamp } from '../components/Lamp';
import { LoginForm } from '../components/LoginForm';
import { useAuth } from '../context/AuthContext';

export const LoginPage = () => {
  // Initially OFF for the dramatic, cinematic dark room atmosphere
  const [isLightOn, setIsLightOn] = useState(false);
  const { isAuthenticated, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // If already authenticated, redirect straight to dashboard
  useEffect(() => {
    if (!loading && isAuthenticated) {
      const from = location.state?.from?.pathname || '/';
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, loading, navigate, location]);

  const toggleLight = () => {
    setIsLightOn((prev) => !prev);
  };

  return (
    <div 
      className={`min-h-screen w-full relative overflow-x-hidden flex flex-col justify-between transition-colors duration-1000 ${
        isLightOn ? 'bg-[#060913]' : 'bg-[#020408]'
      }`}
    >
      {/* =========================================================================
          ATMOSPHERIC AMBIENT BACKDROP LAYERS
          ========================================================================= */}
      {/* Subtle background radial gradient for room depth */}
      <div 
        className={`absolute inset-0 pointer-events-none transition-opacity duration-1000 ${
          isLightOn ? 'opacity-100' : 'opacity-25'
        }`}
        style={{
          backgroundImage: `
            radial-gradient(circle at 18% 35%, rgba(245, 158, 11, ${isLightOn ? '0.14' : '0.02'}) 0%, transparent 50%),
            radial-gradient(circle at 85% 75%, rgba(30, 58, 138, ${isLightOn ? '0.12' : '0.03'}) 0%, transparent 55%),
            linear-gradient(to bottom, #03050a 0%, #060913 100%)
          `
        }}
      />

      {/* Subtle architectural wall texture lines */}
      <div 
        className={`absolute inset-0 pointer-events-none transition-opacity duration-700 bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:4rem_4rem] ${
          isLightOn ? 'opacity-60' : 'opacity-15'
        }`}
      />

      {/* =========================================================================
          TOP NAV / MINIMAL HEADER
          ========================================================================= */}
      <header className="relative z-30 w-full px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
            <Shield className="w-4 h-4 text-amber-400" />
          </div>
          <span className="font-bold text-white tracking-tight text-sm sm:text-base">
            Policy<span className="text-amber-400">Lens</span>
          </span>
        </div>

        <div className="flex items-center gap-2 text-xs font-medium text-slate-400">
          <span className={`inline-block w-2 h-2 rounded-full transition-colors duration-500 ${
            isLightOn ? 'bg-amber-400 shadow-[0_0_8px_#fbbf24]' : 'bg-slate-700'
          }`} />
          <span className="hidden sm:inline">
            {isLightOn ? 'Studio Light ON' : 'Dark Mode Cinematic'}
          </span>
        </div>
      </header>

      {/* =========================================================================
          MAIN INTERACTIVE CONTAINER (SPLIT SCREEN DESKTOP / STACK MOBILE)
          ========================================================================= */}
      <main className="relative z-20 flex-1 flex flex-col justify-center max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-8">
        
        {/* DESKTOP & TABLET LAYOUT: Split Screen */}
        <div className="hidden md:grid md:grid-cols-12 gap-8 items-center min-h-[580px]">
          {/* Left Column: Interactive Lamp */}
          <div className="md:col-span-5 lg:col-span-6 flex items-center justify-center relative">
            <Lamp 
              isOn={isLightOn} 
              onToggle={toggleLight} 
              compact={false}
            />
          </div>

          {/* Right Column: Illuminated Login Panel */}
          <div className="md:col-span-7 lg:col-span-6 flex items-center justify-center relative">
            <AnimatePresence mode="wait">
              {isLightOn ? (
                <motion.div
                  key="login-form-active"
                  initial={{ opacity: 0, x: 35, filter: 'blur(8px)' }}
                  animate={{ opacity: 1, x: 0, filter: 'blur(0px)' }}
                  exit={{ opacity: 0, x: 25, filter: 'blur(6px)' }}
                  transition={{ duration: 0.65, ease: [0.16, 1, 0.3, 1] }}
                  className="w-full flex justify-center"
                >
                  <LoginForm isLightOn={true} />
                </motion.div>
              ) : (
                <motion.div
                  key="login-form-placeholder"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.4 }}
                  onClick={toggleLight}
                  className="w-full max-w-md cursor-pointer group"
                >
                  <div className="rounded-3xl border border-white/5 bg-slate-900/20 backdrop-blur-sm p-10 text-center space-y-4 hover:border-amber-500/30 transition-all duration-300">
                    <div className="w-12 h-12 mx-auto rounded-2xl bg-slate-800/60 border border-slate-700/50 flex items-center justify-center text-slate-500 group-hover:text-amber-400 group-hover:border-amber-500/40 transition-colors">
                      <Sparkles className="w-6 h-6 animate-pulse" />
                    </div>
                    <div className="space-y-1">
                      <h3 className="text-base font-bold text-slate-400 group-hover:text-slate-200 transition-colors">
                        PolicyLens Intelligence Portal
                      </h3>
                      <p className="text-xs text-slate-500">
                        The workspace is currently in resting mode.
                      </p>
                    </div>
                    <p className="text-xs font-semibold text-amber-400/90 pt-2 inline-flex items-center gap-1.5 group-hover:underline">
                      <span>Click the lamp or tap here to illuminate login</span>
                      <span className="text-sm">→</span>
                    </p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* MOBILE LAYOUT: Compact Stacked Layout */}
        <div className="md:hidden flex flex-col items-center justify-center space-y-4 py-2">
          {/* Mobile Lamp at the Top */}
          <div className="w-full max-w-sm flex justify-center">
            <Lamp 
              isOn={isLightOn} 
              onToggle={toggleLight} 
              compact={true}
            />
          </div>

          {/* Mobile Login Panel Below */}
          <div className="w-full max-w-sm">
            <AnimatePresence mode="wait">
              {isLightOn ? (
                <motion.div
                  key="mobile-login-active"
                  initial={{ opacity: 0, y: 25 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 15 }}
                  transition={{ duration: 0.5 }}
                >
                  <LoginForm isLightOn={true} />
                </motion.div>
              ) : (
                <motion.div
                  key="mobile-login-placeholder"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  onClick={toggleLight}
                  className="rounded-2xl border border-white/5 bg-slate-900/30 backdrop-blur-sm p-6 text-center space-y-2 cursor-pointer"
                >
                  <p className="text-xs text-slate-400">
                    Room is dark. Tap the lamp above to turn on light.
                  </p>
                  <span className="text-xs font-bold text-amber-400 block">
                    Turn on light to log in →
                  </span>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

      </main>

      {/* =========================================================================
          BOTTOM FOOTER
          ========================================================================= */}
      <footer className="relative z-30 w-full px-6 py-4 flex flex-col sm:flex-row items-center justify-between text-[11px] text-slate-500 border-t border-white/5 gap-2">
        <div>
          <span>© {new Date().getFullYear()} PolicyLens AI. All rights reserved.</span>
        </div>
        <div className="flex items-center gap-4 text-slate-500">
          <span className="hover:text-slate-400 transition-colors">Privacy Policy</span>
          <span>•</span>
          <span className="hover:text-slate-400 transition-colors">Terms of Service</span>
          <span>•</span>
          <span className="text-amber-400/80 font-mono">v1.2.0</span>
        </div>
      </footer>
    </div>
  );
};

export default LoginPage;
