import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Shield, 
  Mail, 
  Lock, 
  Eye, 
  EyeOff, 
  ArrowRight, 
  Loader2, 
  AlertCircle, 
  CheckCircle2, 
  KeyRound, 
  X, 
  Sparkles,
  Info
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { validateEmail, DEMO_CREDENTIALS } from '../services/authService';

export const LoginForm = ({ isLightOn }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState({});
  const [authError, setAuthError] = useState(null);
  
  // Forgot password modal state
  const [forgotModalOpen, setForgotModalOpen] = useState(false);
  const [resetEmail, setResetEmail] = useState('');
  const [resetSubmitted, setResetSubmitted] = useState(false);

  const { login } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();

  // Validate fields on submit
  const validateForm = () => {
    const newErrors = {};
    const trimmedEmail = email.trim();

    if (!trimmedEmail) {
      newErrors.email = 'Email address is required.';
    } else if (!validateEmail(trimmedEmail)) {
      newErrors.email = 'Please enter a valid email address (e.g., analyst@policylens.ai).';
    }

    if (!password) {
      newErrors.password = 'Password is required.';
    } else if (password.length < 6) {
      newErrors.password = 'Password must be at least 6 characters.';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setAuthError(null);

    if (!validateForm()) {
      return;
    }

    setIsSubmitting(true);

    try {
      const result = await login({
        email: email.trim(),
        password,
        rememberMe
      });

      toast.success(`Welcome back, ${result.user.name || 'PolicyLens User'}!`);
      // Redirect to the dashboard
      navigate('/', { replace: true });
    } catch (err) {
      const message = err.message || 'Authentication failed. Please verify your credentials.';
      setAuthError(message);
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Quick fill helper for development & testing
  const handleQuickFill = (demo) => {
    setEmail(demo.email);
    setPassword(demo.password);
    setErrors({});
    setAuthError(null);
    toast.info(`Filled credentials for ${demo.name} (${demo.role})`, 2500);
  };

  // Handle forgot password modal submission
  const handleResetSubmit = (e) => {
    e.preventDefault();
    if (!resetEmail || !validateEmail(resetEmail)) {
      toast.error('Please enter a valid registered email address.');
      return;
    }
    setResetSubmitted(true);
    setTimeout(() => {
      setForgotModalOpen(false);
      setResetSubmitted(false);
      setResetEmail('');
      toast.success('Password reset instructions sent to your email.');
    }, 1200);
  };

  return (
    <div className="w-full max-w-md mx-auto relative z-20">
      {/* =========================================================================
          MAIN GLASSMORPHISM LOGIN CARD
          ========================================================================= */}
      <div 
        className={`relative overflow-hidden rounded-3xl transition-all duration-700 backdrop-blur-2xl bg-slate-900/75 border border-white/10 shadow-2xl p-6 sm:p-9 ${
          isLightOn
            ? 'shadow-[0_20px_60px_-15px_rgba(0,0,0,0.7),-12px_0_40px_-10px_rgba(251,191,36,0.22)] border-l-amber-500/40'
            : 'shadow-black/60 opacity-40 blur-[1px]'
        }`}
      >
        {/* Subtle interior ambient gradient rim */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-amber-500/80 via-blue-500/50 to-transparent" />
        <div className="absolute -top-24 -right-24 w-48 h-48 rounded-full bg-amber-500/10 blur-3xl pointer-events-none" />
        <div className="absolute -bottom-24 -left-24 w-48 h-48 rounded-full bg-blue-600/10 blur-3xl pointer-events-none" />

        {/* -------------------------------------------------------------
            BRAND HEADER & LOGO
            ------------------------------------------------------------- */}
        <div className="flex flex-col items-center text-center mb-7">
          <div className="relative mb-3.5 group">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-amber-500/20 via-slate-800 to-blue-600/30 border border-amber-500/40 flex items-center justify-center text-amber-400 shadow-lg shadow-amber-500/10 transition-transform group-hover:scale-105">
              <Shield className="w-7 h-7 text-amber-400" />
            </div>
            {/* Glowing amber aura behind logo */}
            <div className="absolute -inset-1 rounded-2xl bg-gradient-to-r from-amber-500/30 to-blue-500/30 blur-md opacity-60 -z-10 animate-pulse" />
          </div>

          <div className="space-y-1">
            <div className="flex items-center justify-center gap-2">
              <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
                Policy<span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 to-amber-200">Lens</span>
              </h1>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wider uppercase bg-amber-500/15 text-amber-400 border border-amber-500/30">
                AI Platform
              </span>
            </div>
            <p className="text-xs font-medium text-amber-300/80 tracking-wide uppercase font-mono">
              Understand Your Policy. Secure Your Future.
            </p>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-800/80 w-full">
            <h2 className="text-xl font-bold text-slate-100">Welcome Back</h2>
            <p className="text-xs sm:text-sm text-slate-400 mt-0.5">
              Your insurance journey, made simple and intelligent.
            </p>
          </div>
        </div>

        {/* -------------------------------------------------------------
            GLOBAL AUTH ERROR BANNER
            ------------------------------------------------------------- */}
        <AnimatePresence>
          {authError && (
            <motion.div
              initial={{ opacity: 0, y: -8, height: 0 }}
              animate={{ opacity: 1, y: 0, height: 'auto' }}
              exit={{ opacity: 0, y: -8, height: 0 }}
              transition={{ duration: 0.2 }}
              role="alert"
              className="mb-5 p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/40 text-rose-300 text-xs sm:text-sm flex items-start gap-2.5 backdrop-blur-md"
            >
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div className="flex-1 font-medium">{authError}</div>
              <button
                type="button"
                onClick={() => setAuthError(null)}
                className="text-rose-400 hover:text-rose-200 p-0.5 rounded"
                aria-label="Dismiss error"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* -------------------------------------------------------------
            LOGIN FORM
            ------------------------------------------------------------- */}
        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          {/* Email Input */}
          <div className="space-y-1.5">
            <label 
              htmlFor="login-email"
              className="block text-xs font-medium text-slate-300 tracking-wide"
            >
              Email Address
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                <Mail className="w-4 h-4" />
              </div>
              <input
                id="login-email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (errors.email) setErrors((prev) => ({ ...prev, email: null }));
                  if (authError) setAuthError(null);
                }}
                placeholder="name@policylens.ai"
                disabled={isSubmitting}
                aria-invalid={Boolean(errors.email)}
                aria-describedby={errors.email ? 'email-error' : undefined}
                className={`w-full pl-10 pr-4 py-2.5 rounded-xl text-sm bg-slate-950/60 text-slate-100 placeholder:text-slate-500 border transition-all duration-200 outline-none ${
                  errors.email
                    ? 'border-rose-500/80 focus:ring-2 focus:ring-rose-500/30'
                    : 'border-slate-700/80 hover:border-slate-600 focus:border-amber-400 focus:ring-2 focus:ring-amber-400/20'
                }`}
              />
            </div>
            {errors.email && (
              <p id="email-error" className="text-xs text-rose-400 flex items-center gap-1.5 mt-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.email}</span>
              </p>
            )}
          </div>

          {/* Password Input */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label 
                htmlFor="login-password"
                className="block text-xs font-medium text-slate-300 tracking-wide"
              >
                Password
              </label>
              <button
                type="button"
                onClick={() => setForgotModalOpen(true)}
                className="text-xs font-medium text-amber-400 hover:text-amber-300 hover:underline transition-colors focus:outline-none"
              >
                Forgot Password?
              </button>
            </div>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                <Lock className="w-4 h-4" />
              </div>
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (errors.password) setErrors((prev) => ({ ...prev, password: null }));
                  if (authError) setAuthError(null);
                }}
                placeholder="••••••••••••"
                disabled={isSubmitting}
                aria-invalid={Boolean(errors.password)}
                aria-describedby={errors.password ? 'password-error' : undefined}
                className={`w-full pl-10 pr-11 py-2.5 rounded-xl text-sm bg-slate-950/60 text-slate-100 placeholder:text-slate-500 border transition-all duration-200 outline-none ${
                  errors.password
                    ? 'border-rose-500/80 focus:ring-2 focus:ring-rose-500/30'
                    : 'border-slate-700/80 hover:border-slate-600 focus:border-amber-400 focus:ring-2 focus:ring-amber-400/20'
                }`}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-200 transition-colors focus:outline-none"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {errors.password && (
              <p id="password-error" className="text-xs text-rose-400 flex items-center gap-1.5 mt-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.password}</span>
              </p>
            )}
          </div>

          {/* Remember Me Checkbox */}
          <div className="flex items-center justify-between pt-1">
            <label className="flex items-center gap-2.5 cursor-pointer text-xs sm:text-sm text-slate-300 select-none group">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="w-4 h-4 rounded border-slate-700 bg-slate-950/80 text-amber-500 focus:ring-amber-400/30 focus:ring-offset-0 transition-colors cursor-pointer accent-amber-500"
              />
              <span className="group-hover:text-white transition-colors">Remember this device</span>
            </label>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full relative group overflow-hidden py-3 px-5 rounded-xl font-semibold text-sm text-slate-950 bg-gradient-to-r from-amber-400 via-amber-300 to-amber-500 hover:from-amber-300 hover:to-amber-400 shadow-lg shadow-amber-500/25 hover:shadow-amber-500/40 focus:ring-2 focus:ring-amber-400/50 outline-none transition-all duration-300 disabled:opacity-70 disabled:cursor-not-allowed cursor-pointer mt-2"
          >
            {/* Button subtle animated sheen */}
            <div className="absolute inset-0 w-1/2 h-full bg-white/20 skew-x-12 -translate-x-full group-hover:translate-x-[300%] transition-transform duration-1000 ease-in-out pointer-events-none" />

            <div className="relative flex items-center justify-center gap-2">
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin text-slate-950" />
                  <span>Authenticating...</span>
                </>
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                </>
              )}
            </div>
          </button>
        </form>

        {/* -------------------------------------------------------------
            DEVELOPMENT & DEMO ACCOUNTS HELPER
            ------------------------------------------------------------- */}
        <div className="mt-6 pt-5 border-t border-slate-800/80">
          <div className="flex items-center justify-between mb-2.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <KeyRound className="w-3.5 h-3.5 text-amber-400" />
              Demo Testing Accounts
            </span>
            <span className="text-[10px] text-amber-400/80 font-mono">Click to autofill</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {DEMO_CREDENTIALS.map((demo) => (
              <button
                key={demo.email}
                type="button"
                onClick={() => handleQuickFill(demo)}
                className="px-2.5 py-2 rounded-lg bg-slate-950/50 hover:bg-slate-800/80 border border-slate-800 hover:border-amber-500/40 text-left transition-all duration-150 group"
              >
                <div className="text-[11px] font-bold text-slate-200 group-hover:text-amber-300 truncate">
                  {demo.role.split(' ')[0]}
                </div>
                <div className="text-[10px] text-slate-500 group-hover:text-slate-400 truncate font-mono">
                  {demo.email.split('@')[0]}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* -------------------------------------------------------------
            FOOTER GUARANTEE
            ------------------------------------------------------------- */}
        <div className="mt-6 text-center">
          <p className="text-[11px] text-slate-500 flex items-center justify-center gap-1.5">
            <Lock className="w-3 h-3 text-amber-400/80" />
            <span>Secure access to your insurance dashboard.</span>
          </p>
        </div>
      </div>

      {/* =========================================================================
          FORGOT PASSWORD MODAL DIALOG
          ========================================================================= */}
      <AnimatePresence>
        {forgotModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-md bg-slate-900 border border-slate-700/80 rounded-2xl p-6 text-slate-200 shadow-2xl"
            >
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <div className="flex items-center gap-2">
                  <KeyRound className="w-5 h-5 text-amber-400" />
                  <h3 className="font-bold text-white text-base">Reset Your Password</h3>
                </div>
                <button
                  onClick={() => setForgotModalOpen(false)}
                  className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <p className="text-xs text-slate-400 mt-3 leading-relaxed">
                Enter your registered PolicyLens organizational email address to receive secure reset credentials.
              </p>

              <form onSubmit={handleResetSubmit} className="mt-4 space-y-4">
                <div>
                  <label htmlFor="reset-email" className="block text-xs font-medium text-slate-300 mb-1.5">
                    Account Email
                  </label>
                  <input
                    id="reset-email"
                    type="email"
                    value={resetEmail}
                    onChange={(e) => setResetEmail(e.target.value)}
                    placeholder="analyst@policylens.ai"
                    required
                    className="w-full px-3.5 py-2.5 rounded-xl text-sm bg-slate-950 border border-slate-700 text-white placeholder:text-slate-500 focus:outline-none focus:border-amber-400 focus:ring-1 focus:ring-amber-400"
                  />
                </div>

                <div className="flex items-center justify-end gap-2.5 pt-2">
                  <button
                    type="button"
                    onClick={() => setForgotModalOpen(false)}
                    className="px-4 py-2 rounded-xl text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={resetSubmitted}
                    className="px-4 py-2 rounded-xl text-xs font-bold text-slate-950 bg-amber-400 hover:bg-amber-300 transition-colors disabled:opacity-50"
                  >
                    {resetSubmitted ? 'Sending...' : 'Send Reset Link'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default LoginForm;
