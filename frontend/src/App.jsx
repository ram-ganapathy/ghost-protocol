import './App.css';
import Portrait from './screens/Portrait.jsx';
import Hero     from './screens/Hero.jsx';
import Cockpit  from './screens/Cockpit.jsx';
import { useState } from 'react';

const SCREENS = [
  { id: 'hero',     label: 'Dossier',    shortLabel: 'Dossier'   },
  { id: 'portrait', label: 'Portrait',   shortLabel: 'Portrait'  },
  { id: 'cockpit',  label: 'Cockpit',    shortLabel: 'Cockpit'   },
];

const API_BASE = '';

export default function App() {
  const [screen, setScreen]         = useState('hero');
  const [ghostReady, setGhostReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [codeInput, setCodeInput]   = useState('');
  const [shake, setShake]           = useState(false);
  const [checking, setChecking]     = useState(false);

  async function handleCodeSubmit(e) {
    e.preventDefault();
    if (!codeInput || checking) return;
    setChecking(true);
    try {
      const res = await fetch(`${API_BASE}/auth`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: codeInput }),
      });
      const data = await res.json();
      if (data.ok) {
        setAuthenticated(true);
      } else {
        setShake(true);
        setCodeInput('');
        setTimeout(() => setShake(false), 500);
      }
    } catch {
      setShake(true);
      setCodeInput('');
      setTimeout(() => setShake(false), 500);
    } finally {
      setChecking(false);
    }
  }

  if (!authenticated) {
    return (
      <div className="gate-screen">
        <form
          className={`gate-form${shake ? ' gate-form--shake' : ''}`}
          onSubmit={handleCodeSubmit}
          aria-label="Access gate"
        >
          <span className="gate-wordmark">Ghost Protocol</span>
          <label className="gate-label" htmlFor="gate-input">Enter access code</label>
          <input
            id="gate-input"
            className="gate-input"
            type="password"
            value={codeInput}
            onChange={e => setCodeInput(e.target.value)}
            autoComplete="off"
            autoFocus
            spellCheck={false}
          />
          <button className="gate-submit" type="submit" disabled={checking}>
            {checking ? 'Checking…' : 'Proceed'}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="app-shell">
      {/* ── top navigation ─────────────────── */}
      <nav className="top-nav" aria-label="Screen navigation">
        <span className="top-nav__wordmark">Ghost Protocol</span>
        <div className="top-nav__tabs" role="tablist">
          {SCREENS.map(s => (
            <button
              key={s.id}
              role="tab"
              aria-selected={screen === s.id}
              className={`nav-tab${screen === s.id ? ' nav-tab--active' : ''}`}
              onClick={() => setScreen(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </nav>

      {/* ── screen outlet ──────────────────── */}
      <main className="app-content" role="main">
        {screen === 'portrait' && <Portrait ghostReady={ghostReady} />}
        {screen === 'hero'     && <Hero onConfirmed={() => setGhostReady(true)} onReset={() => setGhostReady(false)} ghostReady={ghostReady} />}
        {screen === 'cockpit'  && <Cockpit />}
      </main>
    </div>
  );
}
