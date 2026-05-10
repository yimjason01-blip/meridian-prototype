#!/usr/bin/env python3
"""
Real BioMCP-grounded Vitality Action Layer run for jason-real.json.
Mirrors the Adjuncts head-to-head harness — Claude 4.7 + biomcp CLI tools.
"""
import json, os, subprocess, sys, time, re, pathlib
import anthropic

ROOT = pathlib.Path(__file__).parent
PATIENT = json.load(open(ROOT / "jason-real.json"))
RISK_ADJUNCTS = json.load(open(ROOT / "jason-real-action-layer-v15.json"))
PROMPT_PATH = pathlib.Path("/Users/jasonyim/Projects/MeridianPatient/prompts/vitality-action-layer-prompt.md")
PROMPT = PROMPT_PATH.read_text()

# --- Vitality sensitivity map: derived from jason-real.json + Jason's profile facts ---
VITALITY_MAP = {
    "as_of": "2026-05",
    "axes": {
        "autonomic_recovery": {
            "hrv_30d_avg_ms": 76,
            "percentile_age_sex": "elite (>90th)",
            "perturbation": {
                "window": "May 2026",
                "hrv_avg_ms": 61,
                "low_ms": 50,
                "delta_from_baseline_ms": -15,
                "duration": "ongoing"
            },
            "trend_direction": "deflecting_downward",
            "load_bearing": True
        },
        "sleep_architecture": {
            "avg_total_hours": 7.0,
            "deep_min": 19,
            "rem_min": 27,
            "sub_5h_nights_per_month": "2-3",
            "thresholds_met": "deep + rem above floor",
            "trend_direction": "stable_with_disruption_pockets",
            "load_bearing": True
        },
        "conditioning_capacity": {
            "vo2max_mlkgmin": 54,
            "method": "CPET",
            "percentile_age_sex": "~95th",
            "trend_direction": "elite_stable",
            "load_bearing": False,
            "note": "Already elite; protect against decline rather than chase further marginal gain."
        },
        "recovery_valves": {
            "active": ["MTB", "snowboard", "gym (social — Nelson, Rafa)"],
            "lost_or_sidelined": [
                {
                    "name": "BJJ",
                    "status": "sidelined",
                    "function_lost": [
                        "high-intensity sympathetic discharge (rolling)",
                        "social channel (training partners)",
                        "skill-acquisition novelty",
                        "structured combat-sport recovery valve"
                    ],
                    "estimated_loss_duration": "ongoing — no near-term return"
                }
            ]
        },
        "subjective_life": {
            "value": 75,
            "scale": "0-100 self-reported",
            "trend_direction": "below personal baseline (was higher pre-BJJ-sidelining)",
            "load_bearing": True
        },
        "social_physical_recovery": {
            "channels": [
                {"name": "gym social (Nelson, Rafa)", "frequency": "regular", "function": "social channel"},
                {"name": "BJJ partners", "status": "lost"}
            ],
            "trend_direction": "narrowed since BJJ loss",
            "load_bearing": True
        }
    },
    "load_bearing_summary": [
        "Autonomic recovery deflecting (May 2026 HRV dip 76→61, low 50)",
        "Sub-5h nights 2-3/month — sleep-disruption pocket",
        "Lost BJJ recovery valve — sympathetic discharge + social channel + skill novelty unmet",
        "Subjective Life 75 — below personal baseline since BJJ sidelining"
    ],
    "elite_axes_to_protect": ["VO2max 54 (~95th)", "HRV 30d avg 76ms (elite when not in dip)"]
}

# --- BioMCP tool wiring (same shape as Adjuncts harness) ---
BIOMCP_TOOL = {
    "name": "biomcp_search",
    "description": "Search biomedical literature via BioMCP CLI. Returns PMIDs + titles + abstracts. Use for grounding every claim.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Free-text PubMed-style query"},
            "max_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10}
        },
        "required": ["query"]
    }
}

def run_biomcp(query, max_results=5):
    try:
        proc = subprocess.run(
            ["biomcp", "search", "article", "-q", query, "--limit", str(max_results), "--json"],
            capture_output=True, text=True, timeout=60
        )
        if proc.returncode != 0:
            return {"error": f"biomcp exit {proc.returncode}", "stderr": proc.stderr[:400]}
        out = proc.stdout.strip()
        try:
            data = json.loads(out)
            # Trim each result to essentials to keep tokens low
            slim = []
            for r in (data.get("results") or [])[:max_results]:
                slim.append({
                    "pmid": r.get("pmid"),
                    "doi": r.get("doi"),
                    "title": r.get("title"),
                    "journal": r.get("journal"),
                    "date": r.get("date"),
                    "abstract": (r.get("abstract") or "")[:1200]
                })
            return {"query": query, "count": len(slim), "results": slim}
        except Exception:
            return {"raw": out[:6000]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except FileNotFoundError:
        return {"error": "biomcp CLI not found"}

# --- Build payload ---
PAYLOAD = {
    "raw_patient_data": PATIENT,
    "vitality_model_sensitivity_map": VITALITY_MAP,
    "risk_model_cross_reference": {
        "active_risk_adjuncts_summary": [
            c["action_name"] for c in RISK_ADJUNCTS.get("adjuncts_ranked_candidates", [])
        ],
        "instruction": "Vitality candidates that touch alcohol, training intensity, or radiation must flag risk_interaction. Do NOT contradict an active Risk Adjunct."
    },
    "compute_tier": "deep"
}

USER_MSG = f"""Run the Vitality Action Layer for this patient. Follow the system prompt exactly.

Use BioMCP to ground every candidate. Cite real PMIDs. Return JSON only.

Patient + vitality payload:
```json
{json.dumps(PAYLOAD, indent=2)}
```
"""

# --- Run Claude with BioMCP tool loop ---
client = anthropic.Anthropic()
MODEL = "claude-opus-4-5"  # fall back if unavailable
# Try a current strong model
for candidate in ["claude-opus-4-7", "claude-opus-4-5", "claude-sonnet-4-5", "claude-3-5-sonnet-latest"]:
    try:
        client.messages.create(model=candidate, max_tokens=4, messages=[{"role":"user","content":"hi"}])
        MODEL = candidate
        print(f"[model] using {MODEL}", file=sys.stderr)
        break
    except Exception as e:
        print(f"[model] {candidate} unavailable: {str(e)[:120]}", file=sys.stderr)

messages = [{"role": "user", "content": USER_MSG}]
biomcp_calls = 0
biomcp_log = []
MAX_BIOMCP = 25
MAX_TURNS = 40

print(f"[start] vitality run, model={MODEL}", file=sys.stderr)
for turn in range(MAX_TURNS):
    resp = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=PROMPT,
        tools=[BIOMCP_TOOL],
        messages=messages
    )
    print(f"[turn {turn}] stop_reason={resp.stop_reason} biomcp_calls={biomcp_calls}", file=sys.stderr)
    messages.append({"role": "assistant", "content": resp.content})
    if resp.stop_reason == "end_turn":
        # Final text response
        final_text = ""
        for block in resp.content:
            if block.type == "text":
                final_text += block.text
        # Try parse JSON — strip ``` fences if present
        cleaned = final_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
        try:
            parsed = json.loads(cleaned)
        except Exception as e:
            # Fallback: greedy match outermost {...}
            m = re.search(r"\{[\s\S]*\}", cleaned)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except Exception as e2:
                    parsed = {"_parse_error": str(e2), "_raw_full": cleaned}
            else:
                parsed = {"_parse_error": str(e), "_raw_full": cleaned}
        result = {
            "model": MODEL,
            "biomcp_calls": biomcp_calls,
            "biomcp_log": biomcp_log,
            "output": parsed,
            "raw_text_full": final_text
        }
        json.dump(result, open(ROOT / "jason-real-vitality-action-layer.json", "w"), indent=2, ensure_ascii=False)
        print(f"[done] wrote jason-real-vitality-action-layer.json (biomcp_calls={biomcp_calls})", file=sys.stderr)
        break
    if resp.stop_reason == "tool_use":
        tool_results = []
        for block in resp.content:
            if block.type == "tool_use" and block.name == "biomcp_search":
                if biomcp_calls >= MAX_BIOMCP:
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": json.dumps({"error": "biomcp budget exhausted; finalize with what you have"})
                    })
                    continue
                q = block.input.get("query", "")
                mr = block.input.get("max_results", 5)
                print(f"  [biomcp #{biomcp_calls+1}] {q[:90]}", file=sys.stderr)
                r = run_biomcp(q, mr)
                biomcp_calls += 1
                biomcp_log.append({"q": q, "r_size": len(json.dumps(r))})
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": json.dumps(r)[:9000]
                })
        messages.append({"role": "user", "content": tool_results})
        continue
    # Other stop reason — bail
    print(f"[bail] unexpected stop_reason {resp.stop_reason}", file=sys.stderr)
    break
else:
    print("[bail] exceeded MAX_TURNS", file=sys.stderr)
