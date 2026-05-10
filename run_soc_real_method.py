#!/usr/bin/env python3
"""Run the real Standard-of-Care method for jason-real.json.

Real method = deterministic candidate register first, BioMCP grounding second,
LLM scoring/deduping third. The LLM is not allowed to discover the candidate set.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
from typing import Any, Dict, List

import anthropic

from soc_candidate_register import build_soc_candidate_register

ROOT = pathlib.Path(__file__).parent
PATIENT_PATH = ROOT / 'jason-real.json'
REGISTER_PATH = ROOT / 'jason-real-soc-candidate-register.json'
OUT_PATH = ROOT / 'jason-real-action-layer-soc-realmethod.json'

MODEL = 'claude-opus-4-7'


def run_biomcp(query: str, max_results: int = 4) -> Dict[str, Any]:
    proc = subprocess.run(
        ['biomcp', 'search', 'article', '-q', query, '--limit', str(max_results), '--json'],
        capture_output=True, text=True, timeout=60
    )
    if proc.returncode != 0:
        return {'query': query, 'error': f'biomcp exit {proc.returncode}', 'stderr': proc.stderr[:1000]}
    out = proc.stdout.strip()
    start = out.find('{')
    if start > 0:
        out = out[start:]
    try:
        data = json.loads(out)
    except Exception as e:
        return {'query': query, 'error': f'json parse: {e}', 'raw': out[:3000], 'stderr': proc.stderr[:1000]}
    slim: List[Dict[str, str]] = []
    for r in (data.get('results') or [])[:max_results]:
        slim.append({
            'pmid': str(r.get('pmid') or ''),
            'doi': str(r.get('doi') or ''),
            'title': str(r.get('title') or ''),
            'journal': str(r.get('journal') or ''),
            'date': str(r.get('date') or ''),
            'abstract': str(r.get('abstract') or '')[:1400],
        })
    return {'query': query, 'count': len(slim), 'results': slim, 'stderr': proc.stderr[:1000]}


def ground_register(register: Dict[str, Any]) -> Dict[str, Any]:
    log = []
    for c in register['candidates']:
        q = c['expected_query']
        print(f"[biomcp] {c['id']}: {q}", file=sys.stderr)
        result = run_biomcp(q, 4)
        log.append({'candidate_id': c['id'], 'query': q, 'count': result.get('count', 0), 'error': result.get('error')})
        c['biomcp_query'] = q
        c['biomcp_results'] = result.get('results', [])
        c['evidence_status'] = 'biomcp_grounded' if result.get('count', 0) else 'biomcp_no_results'
        c['citations'] = [
            {'pmid': r.get('pmid', ''), 'doi': r.get('doi', ''), 'title': r.get('title', ''), 'supports': 'retrieved_for_guideline_or_rationale'}
            for r in result.get('results', [])[:3]
        ]
    register['biomcp_log'] = log
    return register


SYSTEM_PROMPT = """You are Meridian's Standard-of-Care scoring component.

You do NOT generate candidates from scratch. A deterministic pre-LLM candidate register has already enumerated eligible SoC candidates from age, sex, genotype, documented data gaps, and domain findings.

Your job:
1. Score and rank the provided candidates using SPAREQ.
2. Preserve every candidate unless it clearly fails the SoC bar based on its own trigger/guideline anchor.
3. Separate mandatory register pins from ranked candidates.
4. Do not invent new candidates. If you see a likely omission, put it in qa_omissions_for_register_update rather than adding it to the ranked list.
5. Do not upgrade ambiguous family history into confirmed PDAC. If source says only “GI cancer,” pancreatic surveillance is not pinned. Family-history clarification is the action.
6. Keep Lp(a) as 72 nmol/L. Never convert it to mg/dL.
7. Use citations only from the candidate's BioMCP results. If a cited result is secondary/review rather than a direct guideline, mark citation_quality accordingly.
8. JSON only. No markdown.

SPAREQ dimensions, 1-4:
S severity of outcome addressed.
P priority / likelihood that this patient actually triggers the action.
A actionability: outcome-redirect, stage-shift, or trajectory-anchor.
R readiness / feasibility.
E expected harm burden, where 4 is low harm and 1 is high harm.
Q quality of evidence / guideline anchor.

Output schema:
{
  "method": "deterministic_register_then_llm_scoring_v1",
  "model": "<model>",
  "temperature": 0,
  "patient_id": "...",
  "register_pinned_actions": [ candidate objects with spareq omitted and mandatory=true ],
  "soc_ranked_candidates": [
    {
      "id": "...",
      "action_name": "...",
      "type": "...",
      "domain": "...",
      "trigger": {"kind":"...", "summary":"..."},
      "guideline_anchor": "...",
      "intervention": "...",
      "tracking_metric": "...",
      "urgency": "...",
      "rationale": "...",
      "spareq": {"s":1, "s_reason":"...", "p":1, "p_reason":"...", "a":1, "a_reason":"...", "r":1, "r_reason":"...", "e":1, "e_reason":"...", "q":1, "q_reason":"..."},
      "score": 0.0,
      "citations": [{"pmid":"", "doi":"", "title":"", "supports":"", "citation_quality":"direct_guideline|secondary_guideline_summary|rationale_literature|weak"}],
      "classification": "standard_of_care"
    }
  ],
  "considered_and_excluded": [],
  "qa_omissions_for_register_update": [],
  "method_notes": []
}
"""


def score_with_llm(register: Dict[str, Any]) -> Dict[str, Any]:
    client = anthropic.Anthropic()
    user = {
        'patient_subset': {
            'age': 47,
            'sex': 'Male',
            'lp_a': {'value': 72, 'unit': 'nmol/L'},
            'atm': {'status': 'heterozygous', 'variant': 'c.8147T>C', 'classification': 'pathogenic'},
            'family_history': 'paternal grandfather: GI cancer, pancreatic primary not confirmed in source data',
            'cac': 0,
            'bp': '116/76',
            'a1c': 5.3,
            'egfrcr': 72,
            'creatinine': 1.25,
        },
        'candidate_register': register,
        'score_formula': 'weighted average: S*0.25 + P*0.20 + A*0.20 + R*0.15 + E*0.10 + Q*0.10'
    }
    resp = client.messages.create(
        model=MODEL,
        temperature=0,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': json.dumps(user, indent=2, ensure_ascii=False)}]
    )
    text = ''.join(block.text for block in resp.content if getattr(block, 'type', None) == 'text')
    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```\s*$', '', cleaned)
    try:
        parsed = json.loads(cleaned)
    except Exception as e:
        m = re.search(r'\{[\s\S]*\}', cleaned)
        if not m:
            raise
        parsed = json.loads(m.group(0))
    parsed['_raw_text'] = text
    return parsed


def main():
    import os

    patient = json.load(open(PATIENT_PATH))
    register = build_soc_candidate_register(patient)
    REGISTER_PATH.write_text(json.dumps(register, indent=2, ensure_ascii=False))
    print(f"[register] {len(register['candidates'])} candidates", file=sys.stderr)

    grounded = ground_register(register)
    grounded_path = ROOT / 'jason-real-soc-candidate-register-grounded.json'
    grounded_path.write_text(json.dumps(grounded, indent=2, ensure_ascii=False))
    print(f"[grounded] wrote {grounded_path.name}", file=sys.stderr)

    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('[skip] ANTHROPIC_API_KEY not set in shell env; grounded register is ready for Hermes/delegate scorer.', file=sys.stderr)
        return

    scored = score_with_llm(grounded)
    final = {
        'engine_artifact': 'standard_of_care_real_method',
        'candidate_register': grounded,
        'scored_output': scored,
    }
    OUT_PATH.write_text(json.dumps(final, indent=2, ensure_ascii=False))
    print(f"[done] wrote {OUT_PATH.name}", file=sys.stderr)


if __name__ == '__main__':
    main()
