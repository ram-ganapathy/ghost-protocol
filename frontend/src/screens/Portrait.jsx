import { useState, useRef, useEffect } from 'react';
import { ghost, users } from '../mockData.js';
import './Portrait.css';

const API_BASE = '';

// ─── trust-tier helpers ──────────────────────────────────────
const TIER_LABELS = {
  stranger: 'Stranger',
  earned:   'Earned trust',
  circle:   'Inner circle',
};

const TIER_CLASS = {
  stranger: 'tier-stranger',
  earned:   'tier-earned',
  circle:   'tier-circle',
};

// ─── component ──────────────────────────────────────────────
export default function Portrait({ ghostReady }) {
  const [currentUserIdx, setCurrentUserIdx] = useState(0);
  const [inputValue, setInputValue]         = useState('');
  const [mode, setMode]                     = useState('idle');   // idle | loading | checking | speaking | deferring | error
  const [answer, setAnswer]                 = useState('');
  const [question, setQuestion]             = useState('');
  const [toolUsed, setToolUsed]             = useState(null);
  const inputRef = useRef(null);
  const abortRef = useRef(null);

  const currentUser = users[currentUserIdx];

  // B3: reset the initial user's session on first mount
  useEffect(() => {
    fetch(`${API_BASE}/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: users[0].id }),
    }).catch(() => {}); // non-blocking — backend may not be up yet during dev
  }, []);

  // reset to idle after a delay so the demo can cycle questions
  useEffect(() => {
    if (mode === 'speaking' || mode === 'deferring' || mode === 'error') {
      const t = setTimeout(() => {
        setMode('idle');
        setAnswer('');
        setQuestion('');
        setToolUsed(null);
      }, 14000);
      return () => clearTimeout(t);
    }
  }, [mode]);

  async function handleSend() {
    const trimmed = inputValue.trim();
    if (!trimmed || mode === 'loading') return;

    // cancel any in-flight request
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setQuestion(trimmed);
    setInputValue('');
    setMode('loading');

    try {
      const res = await fetch(`${API_BASE}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmed, trust_tier: currentUser.trustTier, user_id: currentUser.id }),
        signal: controller.signal,
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      setAnswer(data.answer);

      // T4: if a tool was called, show the "checking" beat before the answer
      if (data.tool_used) {
        setToolUsed(data.tool_used);
        setMode('checking');
        setTimeout(() => {
          setToolUsed(null);
          setMode(data.deferred ? 'deferring' : 'speaking');
        }, 1800);
      } else {
        setMode(data.deferred ? 'deferring' : 'speaking');
      }
    } catch (err) {
      if (err.name === 'AbortError') return;
      setAnswer('');
      setMode('error');
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const frameClass = [
    'portrait-frame',
    (mode === 'speaking' || mode === 'loading' || mode === 'checking') && 'frame-speaking',
    mode === 'deferring' && 'frame-deferring',
  ].filter(Boolean).join(' ');

  return (
    <div className="portrait-root">

      {/* ── ghost not yet assembled ──────── */}
      {!ghostReady && (
        <div className="portrait-locked" aria-live="polite">
          <div className="portrait-locked__frame">
            <div className="portrait-locked__silhouette" aria-hidden="true" />
          </div>
          <p className="portrait-locked__title">Ghost not yet assembled</p>
          <p className="portrait-locked__hint">
            Go to <strong>Dossier</strong> and add all fragments to bring Daniel online.
          </p>
        </div>
      )}

      {/* ── rest of portrait (hidden until ready) ── */}
      <div className={ghostReady ? undefined : 'portrait-hidden'}>

      {/* ── user switcher ────────────────── */}
      <div className="user-switcher" role="group" aria-label="Active user">
        <span className="user-switcher__label">Asking as</span>
        {users.map((u, i) => (
          <button
            key={u.id}
            className={`user-btn${i === currentUserIdx ? ' user-btn--active' : ''}`}
            onClick={() => {
            const newUser = users[i];
            setCurrentUserIdx(i);
            setMode('idle');
            setAnswer('');
            setToolUsed(null);
            // B3: reset session on persona switch — prevents history leaking across tiers
            fetch(`${API_BASE}/reset`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ user_id: newUser.id }),
            }).catch(() => {});
          }}
            aria-pressed={i === currentUserIdx}
          >
            {u.name}
          </button>
        ))}
      </div>

      {/* ── portrait + nameplate ─────────── */}
      <div className="portrait-stage">

        {/* frame wrap — glow ring is positioned relative to this, not the whole stage */}
        <div className="portrait-frame-wrap">
          {/* glow ring — visible when speaking or loading */}
          <div className={`glow-ring${(mode === 'speaking' || mode === 'loading' || mode === 'checking') ? ' glow-ring--active' : ''}`} aria-hidden="true" />

          {/* gilt frame */}
          <div className={frameClass}>
            <div className="frame-inner">
              <div className="portrait-img-wrap">
                <img
                  src={ghost.portraitUrl}
                  alt={`Portrait of ${ghost.name}`}
                  className={`portrait-img${mode === 'deferring' ? ' portrait-img--dim' : ''}`}
                  draggable="false"
                />
                {/* breathing overlay — idle only */}
                {mode === 'idle' && (
                  <div className="portrait-breathe" aria-hidden="true" />
                )}
              </div>
            </div>

            {/* frame corner ornaments */}
            <span className="frame-corner frame-corner--tl" aria-hidden="true" />
            <span className="frame-corner frame-corner--tr" aria-hidden="true" />
            <span className="frame-corner frame-corner--bl" aria-hidden="true" />
            <span className="frame-corner frame-corner--br" aria-hidden="true" />
          </div>
        </div>

        {/* nameplate — beside the portrait */}
        <div className="nameplate">
          <div className="nameplate__name">{ghost.name}</div>
          <div className="nameplate__divider" aria-hidden="true" />
          <div className="nameplate__title">{ghost.title}</div>
          <div className={`trust-badge ${TIER_CLASS[currentUser.trustTier]}`}>
            <span className="trust-badge__dot" aria-hidden="true" />
            {TIER_LABELS[currentUser.trustTier]}
          </div>
        </div>
      </div>

      {/* ── speech area ──────────────────── */}
      <div className="speech-area" aria-live="polite" aria-atomic="true">
        {mode === 'idle' && (
          <p className="speech-idle">—</p>
        )}

        {/* Asker bubble — appears as soon as a question is sent */}
        {mode !== 'idle' && question && (
          <div className="speech-asker-row">
            <div className="speech-asker-bubble">{question}</div>
          </div>
        )}

        {mode === 'loading' && (
          <div className="speech-ghost-row">
            <div className="speech-bubble speech-bubble--loading" aria-busy="true">
              <p className="speech-loading-dots"><span /><span /><span /></p>
            </div>
          </div>
        )}
        {mode === 'speaking' && (
          <div className="speech-ghost-row">
            <div className="speech-bubble speech-bubble--speaking">
              {answer.trim() && (
                <p className="speech-answer">{answer}</p>
              )}
            </div>
          </div>
        )}
        {mode === 'deferring' && (
          <div className="speech-ghost-row">
            <div className="speech-bubble speech-bubble--deferring">
              <p className="speech-defer-label">past what I'd trust myself on</p>
              <p className="speech-defer-body">
                {answer || `ask the real ${ghost.name.split(' ')[0]}`}
              </p>
            </div>
          </div>
        )}
        {mode === 'checking' && (
          <div className="speech-ghost-row">
            <div className="speech-bubble speech-bubble--checking">
              <p className="speech-checking">
                {toolUsed === 'calendar'
                  ? 'Daniel is checking his calendar…'
                  : toolUsed === 'phoenix'
                  ? 'Recalling past corrections…'
                  : 'Daniel is looking something up…'}
              </p>
            </div>
          </div>
        )}
        {mode === 'error' && (
          <div className="speech-ghost-row">
            <div className="speech-bubble speech-bubble--error">
              <p className="speech-error">couldn't reach Daniel — check the backend is running</p>
            </div>
          </div>
        )}
      </div>

      {/* ── input bar ────────────────────── */}
      <div className="input-bar">
        <input
          ref={inputRef}
          type="text"
          className="input-bar__field"
          placeholder={`Ask ${ghost.name.split(' ')[0]} something…`}
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          aria-label="Question input"
          maxLength={400}
        />
        <button
          className="input-bar__send"
          onClick={handleSend}
          disabled={!inputValue.trim() || mode === 'loading'}
          aria-label="Send question"
        >
          {mode === 'loading' ? '…' : 'Send'}
        </button>
      </div>

      <p className="portrait-hint">
        Try asking anything &mdash; answers shift depth by trust tier (switch users above)
      </p>

      </div>{/* end portrait-hidden wrapper */}
    </div>
  );
}
