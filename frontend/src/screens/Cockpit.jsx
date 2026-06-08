import { useState, useEffect } from 'react';
import { ghost, domains, flagged as mockFlagged } from '../mockData.js';
import './Cockpit.css';

const API_BASE = '';

// ── helpers ──────────────────────────────────────────────────
// Cover both mock issue types and live Arize eval labels.
const ISSUE_LABELS = {
  'drifted':               'Drifted',
  'low-confidence':        'Low confidence',
  'should-have-escalated': 'Should have escalated',
  'hallucinated':          'Hallucinated',
  'incorrect':             'Incorrect',
};

const ISSUE_CLASS = {
  'drifted':               'tag--gap',
  'low-confidence':        'tag--warn',
  'should-have-escalated': 'tag--warn',
  'hallucinated':          'tag--gap',
  'incorrect':             'tag--gap',
};

function ConfidenceBar({ value }) {
  const pct = Math.round(value * 100);
  const cls = value >= 0.75 ? 'bar--good' : value >= 0.5 ? 'bar--warn' : 'bar--bad';
  return (
    <div className="confidence-bar" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`Confidence ${pct}%`}>
      <div className={`confidence-bar__fill ${cls}`} style={{ width: `${pct}%` }} />
      <span className="confidence-bar__label">{pct}%</span>
    </div>
  );
}

// ── Teach modal ──────────────────────────────────────────────
function TeachModal({ item, onClose, onTaught }) {
  const [text, setText]       = useState('');
  const [domain, setDomain]   = useState(item.domainId ?? 'general');
  const [status, setStatus]   = useState('idle'); // idle | submitting | done | error
  const [errMsg, setErrMsg]   = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    if (!text.trim()) return;
    setStatus('submitting');
    setErrMsg('');
    try {
      const res = await fetch(`${API_BASE}/teach`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: item.question,
          fragment_text: text.trim(),
          domain: domain.trim() || 'general',
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      setStatus('done');
      onTaught(item.id, data.fragment_count);
    } catch (err) {
      setErrMsg(err.message);
      setStatus('error');
    }
  }

  return (
    <div className="teach-backdrop" role="dialog" aria-modal="true" aria-labelledby="teach-title">
      <div className="teach-modal">
        <header className="teach-modal__head">
          <h4 className="teach-modal__title" id="teach-title">Teach the ghost</h4>
          <button className="teach-modal__close" onClick={onClose} aria-label="Close">✕</button>
        </header>

        {status === 'done' ? (
          <div className="teach-modal__done">
            <span className="teach-done__icon" aria-hidden="true">✓</span>
            <p>Fragment added. The ghost will use it on the next ask.</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="teach-form">
            <label className="teach-form__label" htmlFor="teach-question">
              Flagged question
            </label>
            <div className="teach-form__readonly" id="teach-question" aria-readonly="true">
              {item.question || <em>(no question text)</em>}
            </div>

            <label className="teach-form__label" htmlFor="teach-text">
              Corrective fragment
              <span className="teach-form__hint">
                Write what Daniel would actually say — this becomes the grounding context for future answers.
              </span>
            </label>
            <textarea
              id="teach-text"
              className="teach-form__textarea"
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder="e.g. For webhook deduplication, always use an idempotency key stored in a durable store — a unique index alone is not enough because…"
              rows={5}
              maxLength={4000}
              required
              autoFocus
            />

            <label className="teach-form__label" htmlFor="teach-domain">
              Domain <span className="teach-form__hint">(optional tag)</span>
            </label>
            <input
              id="teach-domain"
              className="teach-form__input"
              value={domain}
              onChange={e => setDomain(e.target.value)}
              placeholder="e.g. webhook, reliability, auth"
              maxLength={60}
            />

            {status === 'error' && (
              <p className="teach-form__error">{errMsg}</p>
            )}

            <div className="teach-form__actions">
              <button type="button" className="action-btn action-btn--boundary" onClick={onClose}>
                Cancel
              </button>
              <button
                type="submit"
                className="action-btn action-btn--teach"
                disabled={status === 'submitting' || !text.trim()}
              >
                {status === 'submitting' ? 'Teaching…' : 'Add fragment'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

function DomainTile({ domain }) {
  const stateClass = {
    known:  'tile--known',
    shaky:  'tile--shaky',
    gap:    'tile--gap',
  }[domain.state] ?? '';

  const pct = Math.round(domain.coverage * 100);

  const stateIcon = { known: '◉', shaky: '◎', gap: '○' }[domain.state] ?? '○';

  return (
    <div className={`domain-tile ${stateClass}`} title={`${domain.label} — ${pct}% coverage`}>
      {/* fog overlay — heavier for gap/shaky */}
      <div className="tile__fog" aria-hidden="true" />
      {/* lit region — width = coverage */}
      <div className="tile__lit" style={{ width: `${pct}%` }} aria-hidden="true" />
      <div className="tile__body">
        <span className="tile__state-icon" aria-hidden="true">{stateIcon}</span>
        <span className="tile__label">{domain.label}</span>
        <span className="tile__pct">{pct}%</span>
      </div>
      <div className="tile__bar-track">
        <div className="tile__bar-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// ── component ────────────────────────────────────────────────
export default function Cockpit() {
  const [resolvedIds, setResolvedIds] = useState(new Set());
  const [taughtIds, setTaughtIds]     = useState(new Set());
  const [teachTarget, setTeachTarget] = useState(null); // item being taught, or null
  const [fragmentCount, setFragmentCount] = useState(null); // last known KB size
  const [teachMemory, setTeachMemory] = useState(null);

  // Live Arize data — fidelity + flagged queue
  const [liveData, setLiveData]   = useState(null);   // null = not loaded yet
  const [loading, setLoading]     = useState(true);
  const [fetchError, setFetchError] = useState(null);

  async function refreshTeachMemory() {
    try {
      const res = await fetch(`${API_BASE}/teach-memory`);
      if (!res.ok) return;
      const data = await res.json();
      setTeachMemory(data);
      if (data?.total_fragments != null) {
        setFragmentCount(data.total_fragments);
      }
    } catch {
      // Teach-memory visibility is best-effort. Ignore when endpoint is unavailable.
    }
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFetchError(null);

    fetch(`${API_BASE}/cockpit-data`)
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(data => {
        if (!cancelled) {
          setLiveData(data);
          setLoading(false);
        }
      })
      .catch(err => {
        if (!cancelled) {
          setFetchError(err.message);
          setLoading(false);
        }
      });

    refreshTeachMemory();

    return () => { cancelled = true; };
  }, []);

  // Use live flagged when available, fall back to mock while loading or on error
  const liveFlagged  = liveData?.flagged ?? null;
  const allFlagged   = liveFlagged ?? mockFlagged;
  const openItems    = allFlagged.filter(f => !resolvedIds.has(f.id));

  // Domains: live from backend (includes taught-fragment coverage bumps) or mock fallback
  const liveDomains  = liveData?.domains ?? null;
  const activeDomains = liveDomains ?? domains;

  // Fidelity: live when available, mock fallback
  const fidelityRaw = liveData?.fidelity ?? ghost.fidelity;
  const fidelityPct = fidelityRaw != null ? Math.round(fidelityRaw * 100) : '—';

  const handledCount = liveData?.handled ?? null;
  const knownCount   = activeDomains.filter(d => d.state === 'known').length;
  const gapCount     = activeDomains.filter(d => d.state === 'gap').length;

  function handleTeach(item) {
    setTeachTarget(item);
  }

  function handleTaught(id, newCount) {
    setTaughtIds(prev => new Set([...prev, id]));
    if (newCount != null) setFragmentCount(newCount);
    refreshTeachMemory();
    // Short delay so the "done" state is visible before the modal auto-closes.
    setTimeout(() => {
      setResolvedIds(prev => new Set([...prev, id]));
      setTeachTarget(null);
    }, 1200);
  }

  function handleBoundary(id) {
    // stub: sets an escalation boundary in the agent
    setResolvedIds(prev => new Set([...prev, id]));
  }

  return (
    <div className="cockpit-root">
      {teachTarget && (
        <TeachModal
          item={teachTarget}
          onClose={() => setTeachTarget(null)}
          onTaught={handleTaught}
        />
      )}

      {/* ── header stats ──────────────── */}
      <header className="cockpit-header">
        <div className="cockpit-header__title">
          <h2 className="cockpit-title">Cockpit</h2>
          <p className="cockpit-subtitle">Expert review &amp; teaching interface</p>
        </div>
        <div className="cockpit-stats">
          <div className="stat-chip">
            <span className="stat-chip__value" style={{ color: 'var(--accent-fidelity)' }}>
              {loading ? '…' : `${fidelityPct}%`}
            </span>
            <span className="stat-chip__label">
              Overall fidelity{liveData && !loading ? ' (live)' : ''}
            </span>
          </div>
          <div className="stat-chip">
            <span className="stat-chip__value">
              {loading ? '…' : (handledCount ?? knownCount)}
            </span>
            <span className="stat-chip__label">
              {handledCount != null ? 'Spans scored' : 'Domains known'}
            </span>
          </div>
          <div className="stat-chip">
            <span className="stat-chip__value" style={{ color: 'var(--gap)' }}>{gapCount}</span>
            <span className="stat-chip__label">Knowledge gaps</span>
          </div>
          <div className="stat-chip">
            <span className="stat-chip__value" style={{ color: resolvedIds.size > 0 ? 'var(--accent-fidelity)' : 'var(--warn)' }}>
              {loading ? '…' : openItems.length}
            </span>
            <span className="stat-chip__label">Flagged open</span>
          </div>
          {fragmentCount != null && (
            <div className="stat-chip">
              <span className="stat-chip__value" style={{ color: 'var(--accent-fidelity)' }}>{fragmentCount}</span>
              <span className="stat-chip__label">Fragments taught</span>
            </div>
          )}
        </div>
      </header>

      <div className="cockpit-body">

        {/* ── fog-of-war map ──────────── */}
        <section className="cockpit-section" aria-labelledby="fog-title">
          <h3 className="section-title" id="fog-title">Knowledge Territory</h3>
          <p className="section-desc">
            Lit territory is known ground. Haze is uncertain. Dark is uncharted. Teaching a gap lights its region.
          </p>
          <div className="fog-map">
            {activeDomains.map(d => <DomainTile key={d.id} domain={d} />)}
          </div>
        </section>

        {/* ── flagged queue ────────────── */}
        <section className="cockpit-section" aria-labelledby="flagged-title">
          <h3 className="section-title" id="flagged-title">Flagged for Review</h3>
          <p className="section-desc">
            Answers the ghost got wrong or should have deferred. Teach or set a boundary.
            {liveData && !loading && <span className="section-source"> · live from Arize</span>}
          </p>

          {teachMemory && (
            <div className="teach-memory-panel" aria-live="polite">
              <div className="teach-memory-panel__head">
                <span className="teach-memory-title">Runtime teach memory</span>
                <span className="teach-memory-count">{teachMemory.taught_count ?? 0} taught</span>
              </div>
              {(teachMemory.taught ?? []).length > 0 ? (
                <ul className="teach-memory-list">
                  {(teachMemory.taught ?? []).slice(-4).reverse().map(f => (
                    <li key={f.id} className="teach-memory-item">
                      <span className="teach-memory-item__id">{f.id}</span>
                      <span className="teach-memory-item__domain">{f.domain}</span>
                      <span className="teach-memory-item__moral">{f.moral}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="teach-memory-empty">No taught fragments in memory yet.</p>
              )}
            </div>
          )}

          {loading && (
            <div className="flagged-loading" aria-busy="true">
              Pulling scored spans from Arize…
            </div>
          )}

          {!loading && fetchError && (
            <div className="flagged-fetch-error">
              Could not load live data — showing demo data. ({fetchError})
            </div>
          )}

          {!loading && liveData?.error && (
            <div className="flagged-fetch-error">
              {liveData.error} — showing demo data.
            </div>
          )}

          {!loading && openItems.length === 0 && (
            <div className="flagged-empty">
              <span className="flagged-empty__icon" aria-hidden="true">✓</span>
              All flagged items resolved
            </div>
          )}

          <div className="flagged-list">
            {!loading && openItems.map(item => {
              return (
                <div key={item.id} className={`flagged-card${taughtIds.has(item.id) ? ' flagged-card--resolving' : ''}`}>
                  <div className="flagged-card__head">
                    <span className={`issue-tag ${ISSUE_CLASS[item.issue] ?? 'tag--warn'}`}>
                      {ISSUE_LABELS[item.issue] ?? item.issue}
                    </span>
                    {item.domainId && (
                      <span className="flagged-domain">{item.domainId}</span>
                    )}
                  </div>

                  <p className="flagged-question">&ldquo;{item.question}&rdquo;</p>

                  <div className="flagged-answer-block">
                    <span className="flagged-answer-label">Ghost answered:</span>
                    <p className="flagged-answer">{item.answer}</p>
                  </div>

                  {item.explanation && (
                    <p className="flagged-explanation">{item.explanation}</p>
                  )}

                  <div className="flagged-card__foot">
                    {item.confidence != null && (
                      <ConfidenceBar value={item.confidence} />
                    )}
                    <div className="flagged-actions">
                      <button
                        className="action-btn action-btn--teach"
                        onClick={() => handleTeach(item)}
                        disabled={taughtIds.has(item.id)}
                        aria-label={`Teach the ghost about: ${item.question}`}
                      >
                        {taughtIds.has(item.id) ? 'Taught ✓' : 'Teach the ghost'}
                      </button>
                      {item.issue === 'should-have-escalated' && (
                        <button
                          className="action-btn action-btn--boundary"
                          onClick={() => handleBoundary(item.id)}
                          aria-label={`Set boundary for: ${item.question}`}
                        >
                          Set a boundary
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
