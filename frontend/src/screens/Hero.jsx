import { useState, useRef, useEffect } from 'react';
import { ghost, fragments as mockFragments, domains } from '../mockData.js';
import './Hero.css';

const API_BASE = '';

const KIND_LABELS = {
  'decision-log': 'Decision Log',
  'postmortem':   'Post-Mortem',
  'code-review':  'Code Review',
  'design-doc':   'Design Doc',
  'slack-thread': 'Slack Thread',
};

const KIND_ICON = {
  'decision-log': '📋',
  'postmortem':   '🔍',
  'code-review':  '👁',
  'design-doc':   '📐',
  'slack-thread': '💬',
};

// Map fidelity 0..1 → blur px and opacity for the portrait
function fidelityToFilter(fidelity) {
  const blur    = Math.max(0, (1 - fidelity) * 16);
  const opacity = 0.15 + fidelity * 0.85;
  return { blur, opacity };
}

// fidelity constants computed dynamically once fragments are known
const FIDELITY_SEED = 0.12;

export default function Hero({ onConfirmed, onReset, ghostReady }) {
  const [fragments, setFragments]       = useState(mockFragments);
  const [fidelity, setFidelity]         = useState(FIDELITY_SEED);
  const [dockedIds, setDockedIds]       = useState([]);
  const [lastDocked, setLastDocked]     = useState(null);
  const addBtnRef = useRef(null);

  // Fetch real fragments from the backend; fall back to mockData silently
  useEffect(() => {
    fetch(`${API_BASE}/fragments`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.fragments?.length) setFragments(data.fragments);
      })
      .catch(() => {}); // backend not running → mockData stays
  }, []);

  // confirmed is authoritative in App; mirror it locally only for the banner
  const confirmed = ghostReady;

  const fidelityPerFragment = (ghost.fidelity - FIDELITY_SEED) / fragments.length;

  const nextFragment = fragments.find(f => !dockedIds.includes(f.id));
  const allDocked    = !nextFragment;

  const { blur, opacity } = fidelityToFilter(fidelity);

  const fidelityPct = Math.round(fidelity * 100);
  const meterWidth  = `${fidelityPct}%`;

  function handleAddFragment() {
    if (!nextFragment) return;
    const newFidelity = Math.min(ghost.fidelity, fidelity + fidelityPerFragment);
    setDockedIds(prev => [...prev, nextFragment.id]);
    setLastDocked(nextFragment.id);
    setFidelity(newFidelity);

    if (dockedIds.length + 1 >= fragments.length) {
      setTimeout(() => onConfirmed && onConfirmed(), 600);
    }
  }

  function handleReset() {
    setFidelity(FIDELITY_SEED);
    setDockedIds([]);
    setLastDocked(null);
    onReset && onReset();
  }

  const dockedFragments = fragments.filter(f => dockedIds.includes(f.id));

  return (
    <div className="hero-root">

      {/* ── confirmed banner ─────────── */}
      {confirmed && (
        <div className="identity-confirmed" role="status" aria-live="polite">
          <span className="confirmed-icon" aria-hidden="true">◈</span>
          Identity confirmed — ghost is active
        </div>
      )}

      <div className="hero-body">

        {/* ── left: portrait resolve ─── */}
        <div className="hero-portrait-col">
          <div className={`hero-frame${confirmed ? ' hero-frame--confirmed' : ''}`}>
            <div className="hero-frame-inner">
              <img
                src={ghost.portraitUrl}
                alt={`Portrait of ${ghost.name} resolving from evidence`}
                className="hero-portrait-img"
                style={{
                  filter:  `blur(${blur}px) saturate(${0.3 + fidelity * 0.7})`,
                  opacity: opacity,
                }}
                draggable="false"
              />
              {/* scanline overlay — fades out as fidelity rises */}
              <div
                className="hero-scanlines"
                aria-hidden="true"
                style={{ opacity: Math.max(0, 1 - fidelity * 1.5) }}
              />
            </div>
            <span className="frame-corner frame-corner--tl" aria-hidden="true" />
            <span className="frame-corner frame-corner--tr" aria-hidden="true" />
            <span className="frame-corner frame-corner--bl" aria-hidden="true" />
            <span className="frame-corner frame-corner--br" aria-hidden="true" />
          </div>

          <div className="hero-nameplate">
            <div className="hero-name">{ghost.name}</div>
            <div className="hero-role">{ghost.title}</div>
          </div>

          {/* fidelity meter */}
          <div className="fidelity-meter" aria-label={`Ghost fidelity: ${fidelityPct}%`}>
            <div className="fidelity-meter__head">
              <span className="fidelity-meter__label">Ghost fidelity</span>
              <span className="fidelity-meter__pct" style={{ color: fidelity > 0.7 ? 'var(--accent-fidelity)' : 'var(--warn)' }}>
                {fidelityPct}%
              </span>
            </div>
            <div className="fidelity-track" role="meter" aria-valuenow={fidelityPct} aria-valuemin={0} aria-valuemax={100}>
              <div
                className={`fidelity-fill${confirmed ? ' fidelity-fill--full' : ''}`}
                style={{ width: meterWidth }}
              />
            </div>
          </div>
        </div>

        {/* ── right: dossier + actions ─ */}
        <div className="hero-dossier-col">
          <div className="dossier-header">
            <h2 className="dossier-title">Dossier</h2>
            <p className="dossier-desc">
              The ghost is assembled from evidence. Each fragment you add raises fidelity and resolves the portrait.
            </p>
          </div>

          {/* fragment list */}
          <div className="fragment-list" aria-label="Docked fragments">
            {fragments.map((frag, idx) => {
              const isDocked = dockedIds.includes(frag.id);
              const isNew    = frag.id === lastDocked;
              const domain   = domains.find(d => d.id === frag.domainId);
              return (
                <div
                  key={frag.id}
                  className={[
                    'fragment-card',
                    isDocked ? 'fragment-card--docked' : 'fragment-card--pending',
                    isNew    ? 'fragment-card--new'    : '',
                  ].join(' ')}
                  aria-label={isDocked ? `Fragment docked: ${frag.label}` : `Fragment pending: ${frag.label}`}
                >
                  <span className="fragment-icon" aria-hidden="true">{KIND_ICON[frag.kind] ?? '◻'}</span>
                  <div className="fragment-body">
                    <span className="fragment-kind">{KIND_LABELS[frag.kind] ?? frag.kind}</span>
                    <span className="fragment-label">{frag.label}</span>
                    {domain && (
                      <span className="fragment-domain">{domain.label}</span>
                    )}
                  </div>
                  <span className="fragment-status" aria-hidden="true">
                    {isDocked ? '◈' : '○'}
                  </span>
                </div>
              );
            })}
          </div>

          {/* action row */}
          <div className="dossier-actions">
            {!allDocked && !confirmed && (
              <button
                ref={addBtnRef}
                className="dossier-btn dossier-btn--add"
                onClick={handleAddFragment}
                aria-label={`Add fragment: ${nextFragment?.label}`}
              >
                <span aria-hidden="true">+</span>
                Add fragment
                {nextFragment && (
                  <span className="dossier-btn__hint">{nextFragment.label}</span>
                )}
              </button>
            )}
            {dockedIds.length > 0 && !confirmed && (
              <button className="dossier-btn dossier-btn--reset" onClick={handleReset}>
                Reset
              </button>
            )}
            {confirmed && (
              <button className="dossier-btn dossier-btn--reset" onClick={handleReset}>
                Reconstruct from scratch
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
