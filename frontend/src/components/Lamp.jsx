import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, Lightbulb, SunMedium } from 'lucide-react';
import { playLampClickSound } from '../utils/soundEffects';

export const Lamp = ({ isOn, onToggle, compact = false }) => {
  const [isHovered, setIsHovered] = useState(false);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReducedMotion(mediaQuery.matches);

    const handler = (e) => setPrefersReducedMotion(e.matches);
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  const handleToggle = () => {
    playLampClickSound(!isOn);
    onToggle();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleToggle();
    }
  };

  // Light motes/particles definition
  const particles = [
    { id: 1, top: '42%', left: '38%', size: 4, delay: 0, duration: 4.5 },
    { id: 2, top: '55%', left: '46%', size: 3, delay: 0.8, duration: 5.2 },
    { id: 3, top: '65%', left: '32%', size: 5, delay: 1.5, duration: 6.0 },
    { id: 4, top: '48%', left: '58%', size: 3, delay: 2.1, duration: 4.8 },
    { id: 5, top: '72%', left: '52%', size: 4, delay: 1.0, duration: 5.6 },
    { id: 6, top: '58%', left: '26%', size: 2.5, delay: 2.7, duration: 4.2 },
    { id: 7, top: '80%', left: '40%', size: 3.5, delay: 0.4, duration: 6.2 },
    { id: 8, top: '62%', left: '68%', size: 4, delay: 1.9, duration: 5.0 },
  ];

  return (
    <div 
      className={`relative flex flex-col items-center justify-center select-none ${
        compact ? 'w-full py-4' : 'w-full h-full min-h-[480px] lg:min-h-[640px]'
      }`}
    >
      {/* =========================================================================
          BACKGROUND VOLUMETRIC LIGHT & GLOW EFFECTS
          ========================================================================= */}
      
      {/* 1. Ambient Warm Room Bloom (Behind Lamp) */}
      <div
        className={`absolute inset-0 pointer-events-none transition-opacity duration-1000 ease-out ${
          isOn ? 'opacity-100' : 'opacity-0'
        }`}
        style={{
          background: compact
            ? 'radial-gradient(circle 320px at 50% 35%, rgba(251, 191, 36, 0.28) 0%, rgba(245, 158, 11, 0.12) 45%, transparent 75%)'
            : 'radial-gradient(ellipse 650px 650px at 45% 42%, rgba(251, 191, 36, 0.24) 0%, rgba(245, 158, 11, 0.14) 38%, rgba(217, 119, 6, 0.05) 60%, transparent 80%)'
        }}
      />

      {/* 2. Realistic Volumetric Light Cone projecting downward and outward */}
      <div
        className={`absolute pointer-events-none transition-all duration-1000 ease-out ${
          isOn ? 'opacity-90 scale-100' : 'opacity-0 scale-95'
        } ${
          compact
            ? 'top-[110px] w-full max-w-[340px] h-[260px]'
            : 'top-[180px] lg:top-[210px] left-[15%] right-[-30%] lg:right-[-45%] h-[560px]'
        }`}
        style={{
          clipPath: compact
            ? 'polygon(35% 0%, 65% 0%, 95% 100%, 5% 100%)'
            : 'polygon(28% 0%, 52% 0%, 100% 95%, 8% 100%)',
          background: 'linear-gradient(180deg, rgba(254, 240, 138, 0.55) 0%, rgba(251, 191, 36, 0.32) 20%, rgba(245, 158, 11, 0.16) 55%, rgba(180, 83, 9, 0.03) 85%, transparent 100%)',
          filter: 'blur(14px)',
        }}
      />

      {/* 3. Desk / Surface Illumination Puddle */}
      <div
        className={`absolute pointer-events-none transition-opacity duration-1000 ease-out ${
          isOn ? 'opacity-100' : 'opacity-0'
        } ${
          compact
            ? 'bottom-2 w-64 h-16'
            : 'bottom-4 lg:bottom-12 left-[10%] lg:left-[15%] w-[380px] lg:w-[480px] h-24 lg:h-32'
        }`}
        style={{
          background: 'radial-gradient(ellipse at center, rgba(251, 191, 36, 0.45) 0%, rgba(245, 158, 11, 0.25) 35%, rgba(217, 119, 6, 0.08) 65%, transparent 80%)',
          filter: 'blur(10px)',
        }}
      />

      {/* 4. Ceiling / Upward Light Bloom */}
      <div
        className={`absolute pointer-events-none transition-opacity duration-700 ${
          isOn ? 'opacity-70' : 'opacity-0'
        } ${
          compact ? 'top-2 w-48 h-12' : 'top-6 lg:top-14 left-[20%] lg:left-[28%] w-64 lg:w-80 h-16'
        }`}
        style={{
          background: 'radial-gradient(ellipse at center, rgba(254, 240, 138, 0.3) 0%, rgba(251, 191, 36, 0.12) 40%, transparent 75%)',
          filter: 'blur(12px)',
        }}
      />

      {/* 5. Drifting Dust Motes / Light Particles (Visible when ON) */}
      {isOn && !prefersReducedMotion && (
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          {particles.map((p) => (
            <motion.div
              key={p.id}
              className="absolute rounded-full bg-amber-200/80 shadow-[0_0_8px_rgba(251,191,36,0.9)]"
              style={{
                top: p.top,
                left: p.left,
                width: p.size,
                height: p.size,
              }}
              animate={{
                y: [-12, 12, -12],
                x: [-8, 8, -8],
                opacity: [0.2, 0.85, 0.2],
                scale: [0.9, 1.25, 0.9],
              }}
              transition={{
                duration: p.duration,
                delay: p.delay,
                repeat: Infinity,
                ease: 'easeInOut',
              }}
            />
          ))}
        </div>
      )}

      {/* =========================================================================
          INTERACTION HINT & TOOLTIP (Turn on the light to get started)
          ========================================================================= */}
      <AnimatePresence>
        {!isOn && (
          <motion.div
            initial={{ opacity: 0, y: 15, scale: 0.92 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            transition={{ duration: 0.4 }}
            className={`absolute z-30 cursor-pointer ${
              compact
                ? 'top-2 right-4'
                : 'top-[35%] lg:top-[38%] left-1/2 lg:left-[62%] -translate-x-1/2'
            }`}
            onClick={handleToggle}
          >
            <motion.div
              animate={{
                y: [0, -6, 0],
                boxShadow: [
                  '0 0 15px rgba(245, 158, 11, 0.25)',
                  '0 0 30px rgba(245, 158, 11, 0.55)',
                  '0 0 15px rgba(245, 158, 11, 0.25)',
                ],
              }}
              transition={{
                duration: 2.2,
                repeat: Infinity,
                ease: 'easeInOut',
              }}
              className="flex items-center gap-2.5 px-4 py-2 rounded-full bg-slate-900/90 border border-amber-500/50 backdrop-blur-md text-amber-300 shadow-xl text-xs sm:text-sm font-semibold tracking-wide whitespace-nowrap hover:border-amber-400 hover:text-white transition-colors"
            >
              <Lightbulb className="w-4 h-4 text-amber-400 animate-pulse shrink-0" />
              <span>Turn on the light to get started</span>
              <Sparkles className="w-3.5 h-3.5 text-amber-400/90 shrink-0" />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Hover prompt when lamp is already ON */}
      <AnimatePresence>
        {isOn && isHovered && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            className={`absolute z-30 pointer-events-none ${
              compact
                ? 'top-2 right-4'
                : 'top-[36%] lg:top-[40%] left-1/2 lg:left-[62%] -translate-x-1/2'
            }`}
          >
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/80 border border-slate-700/80 backdrop-blur-md text-slate-300 shadow-lg text-xs font-medium">
              <SunMedium className="w-3.5 h-3.5 text-amber-400" />
              <span>Click lamp to switch off</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* =========================================================================
          THE REALISTIC DESIGNER LAMP (Interactive SVG & Structural Canvas)
          ========================================================================= */}
      <div
        className="relative z-20 flex flex-col items-center cursor-pointer group"
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
        tabIndex={0}
        role="switch"
        aria-checked={isOn}
        aria-label="Interactive Lamp Switch. Turn on the light to illuminate login form."
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <svg
          viewBox="0 0 320 480"
          className={`transition-transform duration-300 ease-out group-hover:scale-[1.015] filter drop-shadow-2xl ${
            compact ? 'w-48 h-56' : 'w-72 sm:w-80 lg:w-[340px] h-[380px] sm:h-[430px] lg:h-[480px]'
          }`}
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            {/* Gradients for Brass Elements */}
            <linearGradient id="brassMetallic" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#784712" />
              <stop offset="25%" stopColor="#ca8a04" />
              <stop offset="50%" stopColor="#fef08a" />
              <stop offset="75%" stopColor="#ca8a04" />
              <stop offset="100%" stopColor="#784712" />
            </linearGradient>

            <linearGradient id="brassStem" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#854d0e" />
              <stop offset="35%" stopColor="#eab308" />
              <stop offset="60%" stopColor="#fef9c3" />
              <stop offset="85%" stopColor="#ca8a04" />
              <stop offset="100%" stopColor="#713f12" />
            </linearGradient>

            <linearGradient id="basePedestal" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#0f172a" />
              <stop offset="20%" stopColor="#1e293b" />
              <stop offset="50%" stopColor="#334155" />
              <stop offset="80%" stopColor="#1e293b" />
              <stop offset="100%" stopColor="#0f172a" />
            </linearGradient>

            {/* Lamp Shade Off Gradient (Deep textured charcoal obsidian) */}
            <linearGradient id="shadeOff" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#090d16" />
              <stop offset="18%" stopColor="#1a2233" />
              <stop offset="50%" stopColor="#253248" />
              <stop offset="82%" stopColor="#1a2233" />
              <stop offset="100%" stopColor="#090d16" />
            </linearGradient>

            {/* Lamp Shade On Gradient (Radiant warm glowing amber gold) */}
            <linearGradient id="shadeOn" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#9a3412" />
              <stop offset="18%" stopColor="#ea580c" />
              <stop offset="40%" stopColor="#f59e0b" />
              <stop offset="50%" stopColor="#fde047" />
              <stop offset="60%" stopColor="#f59e0b" />
              <stop offset="82%" stopColor="#ea580c" />
              <stop offset="100%" stopColor="#9a3412" />
            </linearGradient>

            {/* Inner Bulb Radial Glow */}
            <radialGradient id="bulbGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#ffffff" />
              <stop offset="35%" stopColor="#fef08a" />
              <stop offset="70%" stopColor="#f59e0b" />
              <stop offset="100%" stopColor="rgba(245, 158, 11, 0)" />
            </radialGradient>

            {/* Switch Glow */}
            <radialGradient id="switchLedGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#ffffff" />
              <stop offset="50%" stopColor="#f59e0b" />
              <stop offset="100%" stopColor="rgba(245, 158, 11, 0)" />
            </radialGradient>
          </defs>

          {/* -------------------------------------------------------------
              1. Ornamental Brass Finial (Top Cap)
              ------------------------------------------------------------- */}
          <ellipse cx="160" cy="52" rx="7" ry="5" fill="url(#brassMetallic)" />
          <path d="M158 44 C158 40 162 40 162 44 L161 52 L159 52 Z" fill="url(#brassMetallic)" />
          <circle cx="160" cy="38" r="4" fill="url(#brassMetallic)" />

          {/* -------------------------------------------------------------
              2. Lamp Shade Body (Modern Architectural Flared Trapezoid)
              ------------------------------------------------------------- */}
          <g className="transition-all duration-700">
            {/* Top Rim of Shade */}
            <ellipse
              cx="160"
              cy="58"
              rx="46"
              ry="10"
              fill={isOn ? '#fbbf24' : '#1e293b'}
              stroke="url(#brassMetallic)"
              strokeWidth="2.5"
            />

            {/* Main Shade Fabric Surface */}
            <path
              d="M114 58 L82 178 C82 178 120 196 160 196 C200 196 238 178 238 178 L206 58 Z"
              fill={isOn ? 'url(#shadeOn)' : 'url(#shadeOff)'}
              stroke="url(#brassMetallic)"
              strokeWidth="1.5"
              className="transition-all duration-700 ease-out"
            />

            {/* Bottom Shade Elliptical Rim (Brass Ring) */}
            <ellipse
              cx="160"
              cy="180"
              rx="78"
              ry="18"
              fill={isOn ? 'rgba(254, 240, 138, 0.45)' : '#0b0f19'}
              stroke="url(#brassMetallic)"
              strokeWidth="3"
              className="transition-all duration-700"
            />

            {/* Inner Bulb & Filament Glow (Visible under the bottom rim when ON) */}
            {isOn && (
              <g className="transition-opacity duration-500">
                {/* Intense Central Light Core */}
                <ellipse cx="160" cy="180" rx="42" ry="14" fill="url(#bulbGlow)" />
                <circle cx="160" cy="176" r="16" fill="#ffffff" filter="blur(1px)" />
                {/* Filament Sparkle */}
                <path
                  d="M152 176 Q160 170 168 176"
                  stroke="#ffffff"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                />
              </g>
            )}

            {/* Subtle Shade Outer Glow Aura when ON */}
            {isOn && (
              <path
                d="M114 58 L82 178 C82 178 120 196 160 196 C200 196 238 178 238 178 L206 58 Z"
                fill="none"
                stroke="rgba(251, 191, 36, 0.45)"
                strokeWidth="6"
                filter="blur(5px)"
              />
            )}
          </g>

          {/* -------------------------------------------------------------
              3. Interactive Hanging Pull Cord with Brass Beads
              ------------------------------------------------------------- */}
          <g
            className="transition-transform duration-300 group-hover:translate-x-1"
            style={{ transformOrigin: '190px 190px' }}
          >
            {/* Chain link socket under shade */}
            <circle cx="192" cy="190" r="3" fill="url(#brassMetallic)" />
            {/* Hanging beaded cord */}
            <path
              d="M192 192 L192 248"
              stroke="url(#brassMetallic)"
              strokeWidth="1.8"
              strokeDasharray="2,3"
            />
            {/* Brass Pull Weight / Acorn Finial */}
            <path
              d="M189 248 L195 248 L194 260 C194 262 190 262 190 260 Z"
              fill="url(#brassMetallic)"
              stroke="#5c3809"
              strokeWidth="0.8"
            />
            <circle cx="192" cy="263" r="2.5" fill="url(#brassMetallic)" />
            {/* Tactile indicator glow on pull cord when hovered */}
            <circle
              cx="192"
              cy="256"
              r="7"
              fill={isOn ? 'rgba(251, 191, 36, 0.4)' : 'rgba(251, 191, 36, 0.25)'}
              className="animate-pulse"
            />
          </g>

          {/* -------------------------------------------------------------
              4. Metallic Brass Stem & Architectural Neck
              ------------------------------------------------------------- */}
          {/* Stem Socket under bottom shade rim */}
          <ellipse cx="160" cy="195" rx="12" ry="4" fill="url(#brassMetallic)" />

          {/* Main Vertical Polished Brass Column */}
          <rect
            x="154"
            y="198"
            width="12"
            height="182"
            rx="4"
            fill="url(#brassStem)"
            stroke="#5c3809"
            strokeWidth="0.8"
          />

          {/* Polished Highlight Ridge on Stem */}
          <line
            x1="159"
            y1="202"
            x2="159"
            y2="376"
            stroke="#ffffff"
            strokeWidth="1.5"
            strokeOpacity="0.65"
          />

          {/* Decorative Middle Collar Rings */}
          <rect x="151" y="278" width="18" height="6" rx="2" fill="url(#brassMetallic)" />
          <rect x="151" y="286" width="18" height="3" rx="1.5" fill="url(#brassMetallic)" />

          {/* Lower Stem Collar Junction */}
          <rect x="150" y="376" width="20" height="8" rx="2" fill="url(#brassMetallic)" />

          {/* -------------------------------------------------------------
              5. Weighted Slate & Brass Base Pedestal
              ------------------------------------------------------------- */}
          {/* Base Top Tier (Beveled Brass) */}
          <ellipse
            cx="160"
            cy="386"
            rx="42"
            ry="9"
            fill="url(#brassMetallic)"
            stroke="#784712"
            strokeWidth="1.2"
          />

          {/* Base Middle Tier (Charcoal Slate with Specular Edge) */}
          <path
            d="M108 392 C108 392 130 404 160 404 C190 404 212 392 212 392 L216 406 C216 406 192 418 160 418 C128 418 104 406 104 406 Z"
            fill="url(#basePedestal)"
            stroke="url(#brassMetallic)"
            strokeWidth="1.5"
          />

          {/* Base Bottom Pedestal Rim */}
          <ellipse
            cx="160"
            cy="406"
            rx="56"
            ry="12"
            fill="url(#basePedestal)"
            stroke="url(#brassMetallic)"
            strokeWidth="2"
          />

          {/* Bottom Felt Ring / Table Shadow */}
          <ellipse
            cx="160"
            cy="418"
            rx="64"
            ry="10"
            fill="#020617"
            fillOpacity="0.8"
          />

          {/* -------------------------------------------------------------
              6. Base Tactile Switch Button with Illuminated Ring
              ------------------------------------------------------------- */}
          {/* Switch Bezel */}
          <ellipse
            cx="160"
            cy="398"
            rx="9"
            ry="5"
            fill="url(#brassMetallic)"
            stroke="#452305"
            strokeWidth="1"
          />
          {/* Switch Actuator Cap */}
          <ellipse
            cx="160"
            cy={isOn ? 398 : 396}
            rx="6"
            ry="3.5"
            fill={isOn ? '#fbbf24' : '#1e293b'}
            className="transition-all duration-200"
          />
          {/* Switch Glowing Core */}
          <circle
            cx="160"
            cy={isOn ? 398 : 396}
            r="2.5"
            fill={isOn ? '#ffffff' : '#f59e0b'}
            className={isOn ? 'filter drop-shadow-[0_0_4px_#fbbf24]' : 'opacity-70 animate-pulse'}
          />
        </svg>

        {/* Ambient Click Hint underneath base */}
        <div className="mt-2 text-center">
          <span className="text-[11px] font-mono tracking-widest uppercase text-slate-500 group-hover:text-amber-400/90 transition-colors flex items-center justify-center gap-1.5">
            <span className={`inline-block w-1.5 h-1.5 rounded-full ${isOn ? 'bg-amber-400 shadow-[0_0_6px_#fbbf24]' : 'bg-slate-600'}`}></span>
            {isOn ? 'Light Active • Click to Toggle' : 'Lamp Standby • Tap to Ignite'}
          </span>
        </div>
      </div>
    </div>
  );
};

export default Lamp;
