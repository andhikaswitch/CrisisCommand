"""LLM prompt templates — the single source is PROMPTS.md.

These are string templates for P1 (briefing), P2 (policy options), P3 (ingest
summarizer), and P-R (universal JSON repair). Placeholders use {braces}.
Routing (CLAUDE.md): P1 -> Fireworks; P2/P3 -> local vLLM (fallback
Fireworks); P-R -> same backend as the failed call.

Prompts are backend-agnostic: both vLLM and Fireworks speak the
OpenAI-compatible chat protocol, so the same messages work on either.
"""

# --- P1: Situation Briefing Writer (Fireworks), temperature 0.3 -----------

P1_SYSTEM = (
    "You are a senior crisis-operations analyst writing for government and NGO\n"
    "decision-makers. You are precise, calm, and never sensational. You clearly\n"
    "separate confirmed facts from assessments. You never invent numbers: every\n"
    "figure you state must come from the data provided to you, or be explicitly\n"
    "framed as unknown."
)

P1_USER = """Write a situation briefing for this event.

EVENT DATA (verified feed data):
{event_json}

POPULATION CONTEXT:
{population_context_json}

FORMAT — respond with a single JSON object, no markdown fences:
{{
  "headline": "max 12 words, factual",
  "summary": "120-160 words. Structure: what happened (facts from data), \
who/what is exposed (from population context), key unknowns. \
Plain language, no jargon.",
  "confirmed_facts": ["3-5 short bullets, each traceable to EVENT DATA"],
  "key_unknowns": ["2-4 short bullets"],
  "watch_indicators": ["2-3 things that would signal escalation"]
}}

Rules:
- If a detail is not in the provided data, it belongs in key_unknowns,
  not in summary.
- Neutral tone. No adjectives like "devastating" or "catastrophic".
- Do not recommend actions here — that is a separate analysis step.
"""

P1_TEMPERATURE = 0.3


# --- P2: Policy Option Generator (vLLM, 3 branches batched), temp 0.5 ------

# {branch_directive} differs per branch — order guarantees the UI spectrum.
P2_BRANCH_DIRECTIVES: list[str] = [
    "an immediate, aggressive intervention (act now, higher cost, "
    "fastest risk reduction)",
    "a staged/preparatory response (pre-position resources, act on "
    "trigger conditions)",
    "an enhanced monitoring posture (lowest cost, defines explicit "
    "escalation triggers)",
]

P2_SYSTEM = (
    "You are a disaster-response planning specialist. You design realistic,\n"
    "logistically-grounded response options for crisis leaders. You are honest\n"
    "about trade-offs and never overstate what an option achieves.\n\n"
    "CRITICAL RULE: You NEVER invent quantitative outcomes. You are given\n"
    "simulated exposure ranges from a Monte Carlo model. Your option may claim\n"
    "to reduce exposure ONLY by applying the stated mitigation_factors to those\n"
    "given ranges. All numbers in your output must be arithmetic on provided\n"
    "numbers."
)

P2_USER = """EVENT:
{event_json}

SIMULATED BASELINE (Monte Carlo, {n_runs} runs on the given horizon):
- horizon: {horizon}
- exposed_population_range: [{exposed_p10}, {exposed_p90}]
- severity_curve: {severity_curve}
- drivers: {drivers}

MITIGATION FACTORS (empirically-derived multipliers you may apply):
{mitigation_factors_json}

Design ONE response option in this direction: {branch_directive}.

Respond with a single JSON object, no markdown fences:
{{
  "name": "max 6 words",
  "description": "60-90 words: concrete actions, sequence, who executes",
  "applied_factors": ["factor keys you used"],
  "exposed_population_after": [int, int],
  "est_cost_usd": [int, int],
  "response_time_hours": float,
  "tradeoffs": ["2-4 honest cons, short"],
  "affected_zones": [
    {{"shape": "circle", "lat": 0.0, "lon": 0.0, "radius_km": 0.0,
     "role": "evacuation|hazard|staging"}}
  ]
}}

Rules:
- exposed_population_after = baseline range × applied factor ranges. Show
  your arithmetic implicitly by staying consistent with it.
- est_cost_usd: order-of-magnitude realistic for the region and action;
  wide ranges are acceptable and preferred over false precision.
- affected_zones must be geographically plausible relative to the event
  coordinates (within ~150km).
- tradeoffs must include at least one political/social cost, not only money.
"""

P2_TEMPERATURE = 0.5


# --- P3: Event Summarizer for Ingest (vLLM, high volume), temp 0.1 --------

P3_USER = """Normalize this raw feed item into a one-line event title and classification.

RAW ITEM:
{raw_item_text}

Respond with only JSON:
{{"title": "max 10 words, factual",
 "kind": "earthquake|flood|cyclone|wildfire|volcano|drought|tension|other",
 "severity_hint": 0.0}}

severity_hint: 0-1, your read of seriousness from the text alone.
"other" items will be discarded — use it when unsure.
"""

P3_TEMPERATURE = 0.1


# --- P-R: Universal JSON Repair (any backend), temp 0.1 -------------------

PR_REPAIR = """Your previous response was not valid JSON or violated the schema.
Error: {validation_error}

Respond again with ONLY the corrected JSON object. No other text.
"""

PR_TEMPERATURE = 0.1
