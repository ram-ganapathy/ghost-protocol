// ─────────────────────────────────────────────────────────────
//  MOCK DATA CONTRACT
//  Single source of truth for all UI screens.
//  When the real backend lands, replace this module only.
//  Components must never inline their own fake data.
// ─────────────────────────────────────────────────────────────

export const ghost = {
  name: "Daniel Cross",
  title: "Principal Engineer · Platform & Integrations",
  fidelity: 0.94,
  portraitUrl: "/portrait.png",
};

// Trust is a VISIBLE property of the asker, not inferred.
// stranger | earned | circle
export const users = [
  { id: "u_contractor", name: "Sam (contractor)",  trustTier: "stranger" },
  { id: "u_lead",       name: "Priya (tech lead)", trustTier: "circle"   },
];

// Per-domain coverage — drives the fog-of-war map.
// state: known | shaky | gap
export const domains = [
  { id: "retry",   label: "Retry & idempotency",   coverage: 0.96, state: "known"  },
  { id: "gateway", label: "API gateway patterns",   coverage: 0.88, state: "known"  },
  { id: "auth",    label: "OAuth / auth flows",     coverage: 0.61, state: "shaky"  },
  { id: "webhook", label: "Webhook delivery",       coverage: 0.34, state: "gap"    },
  { id: "esb",     label: "Legacy ESB migration",   coverage: 0.22, state: "gap"    },
];

// Dossier fragments — evidence the ghost is built from (Hero screen).
// Grounded in Daniel's actual scars and documented patterns.
export const fragments = [
  { id: "f1", kind: "decision-log",  label: "Decision log — idempotency keys & retry envelope",  domainId: "retry"   },
  { id: "f2", kind: "postmortem",    label: "Post-mortem — the retry storm that took us down at 3am", domainId: "retry" },
  { id: "f3", kind: "slack-thread",  label: "Slack thread — ADR graveyard (why we stopped mandating them)", domainId: "gateway" },
  { id: "f4", kind: "code-review",   label: "Code review — OAuth token rotation, auth refactor",  domainId: "auth"    },
  { id: "f5", kind: "design-doc",    label: "Design doc — webhook delivery guarantees & dedup",   domainId: "webhook" },
  { id: "f6", kind: "postmortem",    label: "Post-mortem — billing ESB brownout, Q3",             domainId: "esb"     },
];

// Arize-flagged answers — expert review queue (Cockpit screen).
// issue: drifted | low-confidence | should-have-escalated
export const flagged = [
  {
    id: "fl1",
    question:   "How do we handle duplicate webhook deliveries?",
    answer:     "Just add a unique index and let inserts fail.",
    issue:      "drifted",
    confidence: 0.42,
    domainId:   "webhook",
  },
  {
    id: "fl2",
    question:   "Should we migrate the billing ESB this quarter?",
    answer:     "Yes, do it now.",
    issue:      "should-have-escalated",
    confidence: 0.71,
    domainId:   "esb",
  },
  {
    id: "fl3",
    question:   "Can we skip the idempotency key for read-only endpoints?",
    answer:     "Reads are fine without it — POST only.",
    issue:      "low-confidence",
    confidence: 0.55,
    domainId:   "retry",
  },
];

// Canned answers — keyed by message slug then trustTier.
// Same question, different depth by trust tier — that's the whole point.
export const cannedAnswers = {
  "5643 alarm": {
    stranger: "which metric",
    earned:   "which metric. if it's CPU it's the month-end batch — been there before. health check is a different story.",
    circle:   "which metric. if it's CPU it's the month-end job, ignore it — same one ops has been \"about to fix\" since March. health check though, that's real. ping me before you touch 5643",
  },
  "retry storm": {
    stranger: "exponential backoff with jitter. don't poll on a fixed interval.",
    earned:   "exponential backoff with jitter — seen fixed intervals take down a service at 3am. add a dead-letter queue for the stragglers.",
    circle:   "exponential backoff with jitter. we learned this the hard way — that 3am incident started with a flat retry loop. dead-letter queue, circuit breaker, and for god's sake don't let the retry period coincide with your billing window.",
  },
  "oauth": {
    stranger: "which flow? authorization code for user-facing, client credentials for service-to-service.",
    earned:   "which flow? for user-facing, authorization code with PKCE. for service-to-service, client credentials. what's the use case?",
    circle:   "which flow? PKCE for anything touching a browser — don't skip it. client credentials for the service mesh, but scope it down hard. the auth refactor last quarter shows what happens when you don't. what are you wiring up?",
  },
};
