#!/usr/bin/env python3
"""Canonical Jim symptom-integration pipeline.

This replaces the prior symptom wrapper that used non-canonical bucket names.
All active lane labels are exact user-facing lane labels from generation through ranking artifacts.
"""
import json, os, re, sys, time, pathlib
from datetime import datetime
from openai import OpenAI

OUT_DIR = pathlib.Path('/tmp/jim_symptom_run_canonical'); OUT_DIR.mkdir(exist_ok=True)
LOG = OUT_DIR / 'pipeline.log'

FIX_PATH = pathlib.Path('/tmp/jim_1_1_current_filled.json')
PRIOR_SYSTEMIC = pathlib.Path('/tmp/jim_1_1_systemic_gpt55.json')
PRIOR_RANKING = pathlib.Path('/tmp/jim_1_1_candidate_ranking_v0_1_gpt55.json')
PROMPT_PATH = pathlib.Path('/tmp/meridian_risk_action_candidate_discovery_prompt_v1_1.md')
PROMPT_V10 = PROMPT_PATH.read_text()
NARRATIVE_PATH = pathlib.Path('/Users/jasonyim/Projects/MeridianPatient/data/jim-symptom-narrative.txt')
NARRATIVE = NARRATIVE_PATH.read_text()

MODEL = 'gpt-5.5'
client = OpenAI(timeout=240.0)

LANES = [
    ('SoC Monitoring', 15),
    ('SoC Risk Reduction', 15),
    ('Adjunct Options', 15),
    ('Excluded / Watchlist', 15),
]
ACTIVE_LANES = ['SoC Monitoring', 'SoC Risk Reduction', 'Adjunct Options']

SPAREQ_FORMULA = '(S*0.25)+(P*0.20)+(A*0.20)+(R*0.15)+(E*0.10)+(Q*0.10)'

EXTRACTION_PROMPT_PATH = OUT_DIR / 'symptom_extraction_prompt_v0_1.md'
SYSTEMIC_PROMPT_PATH = OUT_DIR / 'systemic_symptom_prompt_v0_1.md'
RANKING_PROMPT_PATH = OUT_DIR / 'ranking_prompt_v0_2_canonical.md'


def log(msg):
    line = f'[{datetime.now().isoformat(timespec="seconds")}] {msg}'
    print(line, flush=True)
    with LOG.open('a') as f:
        f.write(line + '\n')


def extract_json(text):
    t = text.strip()
    t = re.sub(r'^```(?:json)?\s*', '', t)
    t = re.sub(r'\s*```\s*$', '', t)
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r'\{[\s\S]*\}', t)
        if m:
            return json.loads(m.group(0))
        raise


def call_gpt(system, user, max_tokens=12000, tag=''):
    log(f'  -> GPT [{tag}] sys={len(system)}c usr={len(user)}c max={max_tokens}')
    t0 = time.time()
    resp = client.responses.create(
        model=MODEL,
        input=[{'role':'system','content':system},{'role':'user','content':user}],
        max_output_tokens=max_tokens,
    )
    dt = time.time() - t0
    text = resp.output_text
    usage = getattr(resp, 'usage', None)
    usage_dict = usage.model_dump() if hasattr(usage, 'model_dump') else (usage.__dict__ if usage else {})
    log(f'  <- [{tag}] {dt:.1f}s len={len(text)}c usage={usage_dict}')
    (OUT_DIR / f'{tag}_usage.json').write_text(json.dumps(usage_dict, indent=2, default=str))
    return text


def load_json_if_exists(path):
    path = pathlib.Path(path)
    if path.exists():
        return json.loads(path.read_text())
    return None


def assert_exact_lane(label):
    allowed = ACTIVE_LANES + ['Excluded / Watchlist']
    if label not in allowed:
        raise RuntimeError(f'non-canonical lane label: {label}')


def required_ids_for(label, n):
    prefix = {'SoC Monitoring':'SOCM', 'SoC Risk Reduction':'SOCR', 'Adjunct Options':'ADJ', 'Excluded / Watchlist':'EXCL'}[label]
    return [f'{prefix}-{i:03d}' for i in range(1, n+1)]


def validate_generation_fragment(label, frag, expected_n):
    if frag.get('lane_label') != label:
        raise RuntimeError(f'{label}: returned lane_label {frag.get("lane_label")}')
    arr = frag.get('candidates') or []
    if len(arr) != expected_n:
        raise RuntimeError(f'{label}: candidate count {len(arr)} != {expected_n}')
    ids = []
    for item in arr:
        assert_exact_lane(item.get('lane_label'))
        if item.get('lane_label') != label:
            raise RuntimeError(f'{label}: item {item.get("id")} lane {item.get("lane_label")}')
        ids.append(item.get('id'))
    required = required_ids_for(label, expected_n)
    if ids != required:
        raise RuntimeError(f'{label}: ids must be exactly {required}, got {ids}')
    return arr


def score(it):
    return round(it.get('S',0)*0.25 + it.get('P',0)*0.20 + it.get('A',0)*0.20 + it.get('R',0)*0.15 + it.get('E',0)*0.10 + it.get('Q',0)*0.10, 3)

log('=== STEP 1: Symptom extraction ===')

EXTRACT_SYSTEM = 'You are the Meridian symptom-extraction engine.\n\nExtract patient-stated symptoms verbatim. Mark whether each symptom changes routing, risk interpretation, or action choice.\n\nReturn JSON only:\n{\n  "capture_id": "cap-jim-001",\n  "patient_id": "jim",\n  "captured_at": "2026-05-11T11:00:00-07:00",\n  "capture_mode": "narrative_text",\n  "extractor_model": "gpt-5.5",\n  "extractor_version": "symptom-spec-v0.1",\n  "raw_input_path": "/Users/jasonyim/Projects/MeridianPatient/data/jim-symptom-narrative.txt",\n  "symptoms": [SymptomEntry],\n  "narrative_themes": [string],\n  "expected_but_not_heard": [string]\n}\n\nSymptomEntry:\n{\n  "id": "sym-<n>",\n  "canonical_term": "snake_case",\n  "patient_quote": "verbatim quote",\n  "onset": "acute | subacute | chronic | lifelong | new_onset | resolved | unknown",\n  "duration_days": integer or null,\n  "severity_patient_reported": "mild | moderate | severe | n/a (positive finding) | unspecified",\n  "functional_impact": "none | minor | activity_limiting | disabling | psychosocial | unspecified",\n  "temporal_pattern": "constant | episodic | progressive | fluctuating | resolved | unspecified",\n  "associated_with": [string],\n  "red_flag": boolean,\n  "red_flag_reason": string or null,\n  "routing": {\n    "domain_models": ["cvd | metabolic | ckd | neuro | cancer"],\n    "systemic_clusters": [string],\n    "action_layer_flag": string or null\n  },\n  "extractor_confidence": "high | medium | low",\n  "needs_clarification": boolean\n}\n\nRules:\n- Every symptom needs a quote.\n- Positive findings are allowed.\n- Resolved symptoms stay resolved.\n- Psychosocial signals do not route to domain_models.\n- List 3 to 5 expected_but_not_heard probes.'
EXTRACTION_PROMPT_PATH.write_text(EXTRACT_SYSTEM)
symptoms = load_json_if_exists(OUT_DIR / 'jim_symptom_extraction.json')
if symptoms is None:
    extract_user = json.dumps({'narrative': NARRATIVE, 'patient_id': 'jim'}, ensure_ascii=False)
    text = call_gpt(EXTRACT_SYSTEM, extract_user, max_tokens=8000, tag='extract')
    (OUT_DIR / 'jim_symptom_extraction_raw.txt').write_text(text)
    symptoms = extract_json(text)
    (OUT_DIR / 'jim_symptom_extraction.json').write_text(json.dumps(symptoms, indent=2, ensure_ascii=False))
else:
    log('  reusing existing symptom extraction artifact')
log(f'  extracted {len(symptoms.get("symptoms",[]))} symptoms')

log('=== STEP 2: Systemic risk model, symptom-aware ===')
SYSTEMIC_SYSTEM = 'You are the Meridian Systemic Risk Model.\n\nIdentify cross-domain patterns that change risk interpretation or action choice.\n\nUse raw data, domain context, prior systemic output, and symptom capture. Treat symptoms as first-class inputs.\n\nReturn JSON only:\n{\n  "patient_id": "jim",\n  "shared_drivers": [{"driver":"","domains":[],"mechanism":"","evidence":"raw|symptom|both"}],\n  "amplifier_combinations": [{"combination":"","domains":[],"rationale":""}],\n  "multi_domain_levers": [{"lever":"","domains_affected":[],"rationale":""}],\n  "trajectory_interactions": [{"interaction":"","rationale":""}],\n  "symptom_clusters_fired": [{"cluster_id":"","components_present":0,"components":[],"confidence":"high|medium|low","systemic_note":""}],\n  "symptom_clusters_near_fire": [{"cluster_id":"","components_present":0,"missing":[],"probe_suggested":""}],\n  "symptom_domain_confirmations": [{"domain":"","symptom_signal":"","effect":"confirms|contradicts|amplifies"}],\n  "patient_generated_knowledge": [{"observation":"","quote":"","engine_action":"document|verify|repeat_test|preserve_in_care_plan"}],\n  "psychosocial_signals": [{"signal":"","quote":"","handling":"handoff_acknowledgment_only|optional_referral|no_action"}],\n  "expected_but_not_heard": [string],\n  "systemic_summary_one_paragraph": ""\n}'
SYSTEMIC_PROMPT_PATH.write_text(SYSTEMIC_SYSTEM)
systemic = load_json_if_exists(OUT_DIR / 'jim_systemic_symptom_aware.json')
if systemic is None:
    prior_sys = json.load(PRIOR_SYSTEMIC.open())
    systemic_user = json.dumps({
        'patient_fixture': json.load(FIX_PATH.open()),
        'prior_systemic_output_for_reference': prior_sys.get('output') or prior_sys,
        'symptom_capture': symptoms,
        'instruction': 'Produce a fresh systemic synthesis that integrates symptom capture as a first-class input class. Reference the prior systemic output only as context for what was previously concluded from raw and domain data alone.'
    }, ensure_ascii=False)
    text = call_gpt(SYSTEMIC_SYSTEM, systemic_user, max_tokens=8000, tag='systemic')
    (OUT_DIR / 'jim_systemic_symptom_aware_raw.txt').write_text(text)
    systemic = extract_json(text)
    (OUT_DIR / 'jim_systemic_symptom_aware.json').write_text(json.dumps(systemic, indent=2, ensure_ascii=False))
else:
    log('  reusing existing systemic artifact')
log('  systemic done')

log('=== STEP 3: Candidate generation v1.0 canonical lanes ===')
lanes = {}
axes_hint = []
for label, target_n in LANES:
    safe = re.sub(r'[^A-Za-z0-9]+','_',label).strip('_').lower()
    log(f'  lane: {label} target={target_n}')
    parsed = load_json_if_exists(OUT_DIR / f'jim_gen_{safe}.json')
    if parsed is not None:
        try:
            validate_generation_fragment(label, parsed, target_n)
            log(f'  reusing existing valid lane artifact for {label}')
        except Exception as e:
            log(f'  existing lane artifact invalid for {label}: {e}; regenerating')
            parsed = None
    attempts = 0
    last_error = None
    while parsed is None and attempts < 3:
        attempts += 1
        repair_note = '' if last_error is None else f' Previous attempt was rejected by validation: {last_error}. Correct the structure; do not add extras.'
        ids_required = required_ids_for(label, target_n)
        user_obj = {
            'task': f'Generate only the {label} lane. Produce exactly {target_n} candidates, no more and no fewer. The candidates array must contain exactly these IDs in order: {ids_required}. Keep prose concise. Return JSON using the required schema for that exact lane label.' + repair_note,
            'lane_label': label,
            'target_count': target_n,
            'required_candidate_ids': ids_required,
            'patient_payload': {
                'raw_patient_data': json.load(FIX_PATH.open()),
                'symptom_capture': symptoms,
                'systemic_risk_model': systemic,
                'domain_risk_models': {'status':'partial_current_signals_only'},
                'mandatory_action_register': {'status':'not_supplied'},
                'existing_plan_state': {'completed_facts':['CAC=0', 'Lp(a)=72 nmol/L']},
                'compute_tier':'deep'
            },
            'axes_from_prior_calls': axes_hint,
        }
        text = call_gpt(PROMPT_V10, json.dumps(user_obj, ensure_ascii=False), max_tokens=14000, tag='gen_' + re.sub(r'[^A-Za-z0-9]+','_',label).strip('_') + f'_try{attempts}')
        (OUT_DIR / f'jim_gen_{safe}_raw_try{attempts}.txt').write_text(text)
        candidate = extract_json(text)
        try:
            validate_generation_fragment(label, candidate, target_n)
            parsed = candidate
        except Exception as e:
            last_error = str(e)
            log(f'  validation rejected {label} attempt {attempts}: {last_error}')
    if parsed is None:
        raise RuntimeError(f'{label}: failed validation after retries: {last_error}')
    lanes[label] = parsed
    (OUT_DIR / f'jim_gen_{safe}.json').write_text(json.dumps(parsed, indent=2, ensure_ascii=False))
    if not axes_hint:
        axes_hint = parsed.get('search_axes', [])
    log(f'  lane {label}: {len(parsed.get("candidates",[]))} candidates')

generation = {
    'patient_id': 'jim',
    'prompt_version': 'v1.1 compressed canonical lane labels, LLM-only, symptom-integrated',
    'prompt_path': str(PROMPT_PATH),
    'model': MODEL,
    'lanes': lanes,
    'candidate_counts': {label: len(frag.get('candidates', [])) for label, frag in lanes.items()},
    'completed_at': datetime.now().isoformat(),
}
(OUT_DIR / 'jim_candidates_v10_symptom_canonical.json').write_text(json.dumps(generation, indent=2, ensure_ascii=False))

log('=== STEP 4: Ranking v0.2 canonical lanes ===')
RANKING_SYSTEM = 'You are the Meridian Action Ranking pass v0.3.\n\nRank existing candidates only. Do not create, rename, omit, or move candidates.\n\nRules:\n- SoC Monitoring: order by care-maintenance logic. No SPAREQ.\n- SoC Risk Reduction: rank by expected modeled-risk reduction, then evidence, then urgency, then burden.\n- Adjunct Options: rank by patient-specific upside, evidence, reversibility, and burden.\n- Excluded / Watchlist: preserve as audit only.\n- Preserve symptom_derived.\n- Routine record closure must not outrank model-moving actions.\n\nFor ranked lanes, return S, P, A, R, E, Q as 1 to 5 integers:\nS = severity if untreated.\nP = relevance for this patient.\nA = modeled-risk impact.\nR = urgency or reversibility window.\nE = effort inverted.\nQ = evidence quality.\n\nReturn JSON only:\n{\n  "lanes": {\n    "SoC Monitoring": [{"id":"","title":"","ordering_rationale":"","symptom_derived":false}],\n    "SoC Risk Reduction": [{"id":"","title":"","S":0,"P":0,"A":0,"R":0,"E":0,"Q":0,"rationale":"","symptom_derived":false}],\n    "Adjunct Options": [{"id":"","title":"","S":0,"P":0,"A":0,"R":0,"E":0,"Q":0,"rationale":"","symptom_derived":false}]\n  },\n  "audit": {\n    "Excluded / Watchlist": [{"id":"","title":"","reason":""}]\n  },\n  "input_sufficiency": {"notes":""}\n}'
RANKING_PROMPT_PATH.write_text(RANKING_SYSTEM)
ranking_user = json.dumps({'generation_artifact': generation, 'patient_payload_summary': {'symptom_capture': symptoms, 'systemic': systemic}}, ensure_ascii=False)
text = call_gpt(RANKING_SYSTEM, ranking_user, max_tokens=16000, tag='ranking')
(OUT_DIR / 'jim_ranking_v02_raw.txt').write_text(text)
ranking = extract_json(text)
rank_lanes = ranking.get('lanes') or {}
for label in ACTIVE_LANES:
    if label not in rank_lanes:
        raise RuntimeError(f'ranking missing lane {label}')
for item in rank_lanes['SoC Risk Reduction'] + rank_lanes['Adjunct Options']:
    item['spareq_score'] = score(item)
rank_lanes['SoC Risk Reduction'] = sorted(rank_lanes['SoC Risk Reduction'], key=lambda x: x.get('spareq_score', 0), reverse=True)
rank_lanes['Adjunct Options'] = sorted(rank_lanes['Adjunct Options'], key=lambda x: x.get('spareq_score', 0), reverse=True)
ranking['lanes'] = rank_lanes
ranking['ranking_run'] = {
    'patient_id':'jim',
    'model':MODEL,
    'source_candidate_artifact': str(OUT_DIR / 'jim_candidates_v10_symptom_canonical.json'),
    'spareq_formula': SPAREQ_FORMULA,
    'spareq_definitions': {
        'S':'severity of outcome if untreated',
        'P':'probability/relevance of that outcome for this patient',
        'A':'action impact / outcome-redirect / stage-shift / trajectory-anchor',
        'R':'reversibility / urgency window',
        'E':'effort inverted, easier/lower burden = higher',
        'Q':'evidence quality'
    },
    'completed_at': datetime.now().isoformat(),
}
(OUT_DIR / 'jim_ranking_v02_symptom_canonical.json').write_text(json.dumps(ranking, indent=2, ensure_ascii=False))

log('=== STEP 5: Summary ===')
prior_rank = json.load(PRIOR_RANKING.open()).get('output', {})
def short(arr):
    return [{'id':x.get('id'), 'title':x.get('title'), 'score':x.get('spareq_score'), 'symptom_derived':x.get('symptom_derived')} for x in (arr or [])[:3]]
diff = {
    'patient_id':'jim',
    'symptom_count': len(symptoms.get('symptoms', [])),
    'clusters_fired': [c.get('cluster_id') for c in systemic.get('symptom_clusters_fired', [])],
    'candidate_counts': generation['candidate_counts'],
    'top_3_new': {
        'SoC Monitoring': short(rank_lanes['SoC Monitoring']),
        'SoC Risk Reduction': short(rank_lanes['SoC Risk Reduction']),
        'Adjunct Options': short(rank_lanes['Adjunct Options']),
    },
    'prior_top_3_reference': {
        'SoC Monitoring': [{'id':x.get('id'), 'title':x.get('title')} for x in (prior_rank.get('ordered_soc_screening_surveillance') or [])[:3]],
        'SoC Risk Reduction': [{'id':x.get('id'), 'title':x.get('title')} for x in (prior_rank.get('ranked_soc_risk_reduction') or [])[:3]],
        'Adjunct Options': [{'id':x.get('id'), 'title':x.get('title')} for x in (prior_rank.get('ranked_adjunct_options') or [])[:3]],
    },
    'completed_at': datetime.now().isoformat(),
}
(OUT_DIR / 'jim_symptom_run_diff_canonical.json').write_text(json.dumps(diff, indent=2, ensure_ascii=False))
log('PIPELINE COMPLETE')
print(json.dumps(diff, indent=2, ensure_ascii=False))
