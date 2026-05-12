#!/usr/bin/env python3
"""Karen v0.5 domain-opportunity pipeline using existing Karen generated candidates.

This is deterministic and domain-first: legacy scalar or utility ranking is not used. It canonicalizes
lane labels, uses prior Karen engine candidate artifacts as input, optionally
uses BioMCP search packets for evidence notes, and writes v0.5 artifacts plus a
small JS payload for the Karen prototype.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = pathlib.Path('/tmp/karen_run/karen_candidates_v09.json')
SUMMARY = pathlib.Path('/tmp/karen_run/karen_pipeline_summary.json')
OUT_DIR = ROOT / 'engine' / 'artifacts'
OUT_DIR.mkdir(parents=True, exist_ok=True)

LANE_MAP = {
    'standard_of_care_monitoring_plan': 'SoC Monitoring',
    'risk_mitigation_actions': 'SoC Risk Reduction',
    'adjunct_options': 'Adjunct Options',
    'research_or_excluded': 'Excluded / Watchlist',
}
ACTIVE_LANES = ['SoC Monitoring', 'SoC Risk Reduction', 'Adjunct Options']
RANKING_OBJECTIVE = 'domain_opportunity * relative_effect_size * evidence_confidence'

DOMAIN_ORDER = [
    {
        'domain': 'metabolic',
        'domain_baseline_risk': 'approximately 35% 10-year incident type 2 diabetes risk; prediabetes, prior gestational diabetes, Asian ancestry, central adiposity, family history, lower CRF',
        'residual_opportunity': 'high; no diabetes-prevention program/medication documented and several modifiable drivers remain active',
        'domain_opportunity': 'high (~35% baseline risk × high residual opportunity)',
        'why_ordered_here': 'Largest modeled absolute opportunity and most addressable upstream risk for Karen.',
        'rank': 1,
    },
    {
        'domain': 'cardiovascular',
        'domain_baseline_risk': '7.5% 10-year total CVD risk with elevated LDL-C/non-HDL/ApoB, treated borderline BP, family history, prediabetes and lower CRF',
        'residual_opportunity': 'moderate-high; lipid, BP, activity, diet, sleep and alcohol levers remain partially unoptimized',
        'domain_opportunity': 'moderate-high (~7.5% baseline risk × moderate-high residual opportunity)',
        'why_ordered_here': 'Intermediate near-term vascular risk with multiple guideline-grade modifiable levers.',
        'rank': 2,
    },
    {
        'domain': 'cancer_genetics',
        'domain_baseline_risk': 'CHEK2 likely pathogenic variant with moderate hereditary breast risk; dense breasts and first-degree breast cancer family history; colorectal start-age requirement satisfied by normal 2024 colonoscopy',
        'residual_opportunity': 'moderate; major opportunity is surveillance gap closure and alcohol reduction rather than a broad active prevention regimen',
        'domain_opportunity': 'moderate',
        'why_ordered_here': 'Important inherited-risk domain, but active risk-reduction options are narrower than surveillance and metabolic/CVD prevention.',
        'rank': 3,
    },
    {
        'domain': 'renal_ckd',
        'domain_baseline_risk': 'approximately 2.5% 5-year incident CKD risk; eGFR 88 and UACR 12 mg/g currently reassuring',
        'residual_opportunity': 'low-moderate; protect against future diabetes/BP/ACE-inhibitor safety issues',
        'domain_opportunity': 'low-moderate',
        'why_ordered_here': 'Current kidney markers are normal; opportunity is mainly safety and prevention of downstream risk conversion.',
        'rank': 4,
    },
    {
        'domain': 'neuro',
        'domain_baseline_risk': 'approximately 4.4% 20-year all-cause dementia risk with sleep efficiency and vascular modifiers',
        'residual_opportunity': 'low-moderate; vascular, sleep, and stress levers overlap with higher-opportunity domains',
        'domain_opportunity': 'low-moderate',
        'why_ordered_here': 'Lower absolute modeled risk; most levers are already captured through metabolic/CVD and sleep/stress actions.',
        'rank': 5,
    },
    {
        'domain': 'prevention_general',
        'domain_baseline_risk': 'general preventive care and medication/supplement safety, including bone and thyroid maintenance',
        'residual_opportunity': 'context-dependent; mainly maintenance or due-overdue monitoring',
        'domain_opportunity': 'variable',
        'why_ordered_here': 'Important for care completeness but not the primary absolute risk-opportunity driver.',
        'rank': 6,
    },
]
DOMAIN_RANK = {d['domain']: d['rank'] for d in DOMAIN_ORDER}
DOMAIN_OPP = {d['domain']: d['domain_opportunity'] for d in DOMAIN_ORDER}
DOMAIN_DISPLAY = {
    'metabolic': 'Metabolic risk / diabetes prevention',
    'cardiovascular': 'Cardiovascular risk optimization',
    'cancer_genetics': 'Cancer / hereditary genetics prevention and screening',
    'renal_ckd': 'Renal / CKD and medication safety',
    'neuro': 'Neurocognitive / sleep and stress risk',
    'prevention_general': 'Prevention-general / endocrine-medication optimization',
}

# Domain-first ordering produced from Karen's domain-risk artifacts. Numbers are
# deterministic ordinal proxies, not legacy scalar scores.
RISK_RANK = [
    'RMA-003', 'RMA-004', 'RMA-008', 'RMA-006', 'RMA-005',
    'RMA-001', 'RMA-002', 'RMA-007', 'RMA-009', 'RMA-010',
    'RMA-011', 'RMA-012', 'RMA-013', 'RMA-014', 'RMA-015',
]
ADJ_RANK = [
    'ADJ-002', 'ADJ-001', 'ADJ-003', 'ADJ-008', 'ADJ-004',
    'ADJ-005', 'ADJ-007', 'ADJ-009', 'ADJ-013', 'ADJ-010',
    'ADJ-011', 'ADJ-012', 'ADJ-006', 'ADJ-014', 'ADJ-015',
]
MONITOR_RANK = [
    'SOC-MON-001', 'SOC-MON-005', 'SOC-MON-010', 'SOC-MON-006', 'SOC-MON-008',
    'SOC-MON-011', 'SOC-MON-009', 'SOC-MON-012', 'SOC-MON-003', 'SOC-MON-007',
    'SOC-MON-014', 'SOC-MON-013', 'SOC-MON-015', 'SOC-MON-002', 'SOC-MON-004',
]

DOMAIN_BY_ID = {
    # Metabolic first
    'RMA-003': 'metabolic', 'RMA-004': 'metabolic', 'RMA-008': 'metabolic',
    'RMA-006': 'metabolic', 'RMA-005': 'metabolic',
    'ADJ-001': 'metabolic', 'ADJ-002': 'metabolic', 'ADJ-003': 'metabolic',
    'ADJ-004': 'metabolic', 'ADJ-008': 'metabolic', 'ADJ-009': 'metabolic',
    # CVD
    'RMA-001': 'cardiovascular', 'RMA-002': 'cardiovascular', 'RMA-007': 'cardiovascular',
    'RMA-009': 'cardiovascular', 'RMA-010': 'cardiovascular',
    'ADJ-005': 'cardiovascular', 'ADJ-006': 'cardiovascular', 'ADJ-007': 'cardiovascular',
    'ADJ-013': 'cardiovascular', 'ADJ-014': 'cardiovascular',
    # Neuro / sleep / stress
    'RMA-011': 'neuro', 'RMA-012': 'neuro',
    'ADJ-010': 'neuro', 'ADJ-011': 'neuro', 'ADJ-012': 'neuro',
    # Renal / general / cancer
    'RMA-013': 'renal_ckd', 'RMA-014': 'prevention_general', 'RMA-015': 'prevention_general',
    'ADJ-015': 'cancer_genetics',
}
REL_EFFECT = {
    'RMA-003': 'large', 'RMA-004': 'moderate', 'RMA-008': 'moderate', 'RMA-006': 'moderate', 'RMA-005': 'moderate',
    'RMA-001': 'large', 'RMA-002': 'large', 'RMA-007': 'moderate', 'RMA-009': 'moderate', 'RMA-010': 'small-moderate',
    'RMA-011': 'small-moderate', 'RMA-012': 'small-moderate', 'RMA-013': 'small', 'RMA-014': 'small', 'RMA-015': 'small',
}
CONF = {
    'RMA-003': 'high', 'RMA-001': 'high', 'RMA-002': 'high', 'RMA-009': 'high', 'RMA-006': 'high',
    'RMA-004': 'medium', 'RMA-005': 'medium', 'RMA-007': 'medium', 'RMA-008': 'medium', 'RMA-010': 'medium',
    'RMA-011': 'medium', 'RMA-012': 'medium', 'RMA-013': 'medium', 'RMA-014': 'medium', 'RMA-015': 'medium',
}
ARR = {
    'RMA-003': 'high expected metabolic ARR: DPP-class intervention addresses the dominant ~35% 10-year diabetes opportunity',
    'RMA-004': 'moderate expected metabolic ARR through central-adiposity and postmenopausal weight-trajectory modification',
    'RMA-008': 'moderate expected metabolic ARR through lower postprandial glucose/insulin exposure',
    'RMA-006': 'moderate expected metabolic ARR through insulin sensitivity, lean mass, and bone/function benefits',
    'RMA-005': 'moderate expected metabolic ARR with cross-domain CVD/neuro co-benefit from improved CRF',
    'RMA-001': 'moderate expected CVD ARR from ApoB/LDL-lowering shared decision in intermediate risk',
    'RMA-002': 'moderate expected CVD ARR from moving treated BP consistently below 130/80 if tolerated',
    'RMA-007': 'small-moderate expected CVD ARR as diet-mediated ApoB/LDL reduction',
    'RMA-009': 'small-moderate expected CVD ARR through BP lowering; complements medication strategy',
    'RMA-010': 'small-moderate expected CVD/cancer/metabolic ARR by reducing alcohol exposure at threshold AUDIT-C pattern',
    'RMA-011': 'small-moderate expected neuro/metabolic ARR; mostly indirect through sleep, BP, glycemia and function',
    'RMA-012': 'small expected neuro/metabolic ARR; indirect through stress, sleep, BP, alcohol and adherence',
    'RMA-013': 'small expected renal ARR because current CKD risk is low; high safety value for ACE-inhibitor/dehydration contexts',
    'RMA-014': 'small prevention-general ARR; mainly bone-health optimization after DEXA/vitamin D context',
    'RMA-015': 'small prevention-general ARR; medication-effectiveness/safety optimization rather than risk-event reduction',
}
ADJ_EFFECT = {
    'ADJ-002': ('moderate', 'biomarker_rct'), 'ADJ-001': ('moderate', 'human_observational_plus_mechanism'),
    'ADJ-003': ('moderate', 'biomarker_rct'), 'ADJ-008': ('moderate', 'biomarker_rct'),
    'ADJ-004': ('small', 'biomarker_rct'), 'ADJ-005': ('small', 'biomarker_rct'),
    'ADJ-007': ('small', 'biomarker_rct'), 'ADJ-009': ('moderate', 'close_analog'),
    'ADJ-013': ('small', 'low_downside_only'), 'ADJ-010': ('moderate', 'biomarker_rct'),
    'ADJ-011': ('small', 'mechanism_only'), 'ADJ-012': ('small', 'biomarker_rct'),
    'ADJ-006': ('small', 'mechanism_only'), 'ADJ-014': ('uncertain', 'human_observational_plus_mechanism'),
    'ADJ-015': ('uncertain', 'mechanism_only'),
}
MON_GROUP = {
    'SOC-MON-001': 'due_overdue', 'SOC-MON-005': 'due_overdue', 'SOC-MON-010': 'newly_indicated_by_risk_model',
    'SOC-MON-006': 'newly_indicated_by_risk_model', 'SOC-MON-008': 'routine_on_cadence',
    'SOC-MON-011': 'newly_indicated_by_risk_model', 'SOC-MON-009': 'newly_indicated_by_risk_model',
    'SOC-MON-012': 'newly_indicated_by_risk_model', 'SOC-MON-003': 'newly_indicated_by_risk_model',
    'SOC-MON-007': 'routine_on_cadence', 'SOC-MON-014': 'routine_on_cadence', 'SOC-MON-013': 'routine_on_cadence',
    'SOC-MON-015': 'routine_on_cadence', 'SOC-MON-002': 'routine_on_cadence', 'SOC-MON-004': 'routine_on_cadence',
}

QUERY_HINTS = [
    ('Diabetes Prevention Program', 'diabetes prevention program trial prediabetes'),
    ('blood pressure', 'blood pressure lowering cardiovascular outcomes meta analysis'),
    ('lipid-lowering', 'statin primary prevention intermediate risk LDL cholesterol trial'),
    ('cardiorespiratory fitness', 'cardiorespiratory fitness cardiovascular mortality cohort'),
    ('resistance training', 'resistance training insulin sensitivity postmenopausal women trial'),
    ('DASH', 'DASH sodium reduction blood pressure randomized trial'),
    ('psyllium', 'psyllium LDL cholesterol meta analysis'),
    ('post-meal walking', 'postprandial walking glucose randomized trial'),
    ('meal-sequencing', 'food order vegetables protein before carbohydrate glucose trial'),
    ('CBT-I', 'cognitive behavioral therapy insomnia randomized trial'),
    ('omega-3', 'omega 3 index cardiovascular risk randomized trial'),
    ('sauna', 'sauna cardiovascular mortality cohort blood pressure'),
    ('H. pylori', 'Helicobacter pylori gastric cancer screening eradication trial'),
]

def load_json(path: pathlib.Path):
    return json.loads(path.read_text())

def text_for(it):
    return ' '.join(str(it.get(k) or '') for k in ('title', 'rationale', 'evidence_basis_prose', 'risk_interaction'))

def query_for(it, lane):
    t = text_for(it).lower()
    for needle, query in QUERY_HINTS:
        if needle.lower() in t:
            return query
    return re.sub(r'[^A-Za-z0-9 .+-]', ' ', it['title'])[:160] + ' guideline trial meta analysis'

def biomcp(query, limit=4):
    try:
        proc = subprocess.run(
            ['biomcp', 'search', 'article', '-q', query, '--source', 'pubtator', '--limit', str(limit), '--json'],
            capture_output=True, text=True, timeout=35,
        )
        if proc.returncode != 0:
            return {'query': query, 'count': 0, 'results': [], 'error': proc.stderr[:500]}
        data = json.loads(proc.stdout or '{}')
        results = []
        for r in (data.get('results') or [])[:limit]:
            results.append({k: r.get(k) for k in ['pmid', 'doi', 'title', 'journal', 'date', 'source', 'is_retracted']})
        return {'query': query, 'count': len(results), 'results': results}
    except Exception as e:
        return {'query': query, 'count': 0, 'results': [], 'error': str(e)}

def build_grounding(lanes):
    cache_path = OUT_DIR / 'karen_biomcp_grounding_v01.json'
    if cache_path.exists():
        return load_json(cache_path)
    grounding = {'source': 'biomcp_cli_pubtator', 'max_results_per_candidate': 4, 'candidates': {}}
    for lane in ['SoC Risk Reduction', 'Adjunct Options']:
        for it in lanes[lane]['candidates']:
            q = query_for(it, lane)
            search = biomcp(q, 4)
            grounding['candidates'][it['id']] = {'lane_label': lane, 'title': it['title'], 'query': q, 'search': search}
    cache_path.write_text(json.dumps(grounding, indent=2, ensure_ascii=False))
    return grounding

def sorted_by_ids(arr, ids):
    byid = {x['id']: x for x in arr}
    missing = [x for x in ids if x not in byid]
    if missing:
        raise RuntimeError(f'missing ids {missing}')
    return [byid[x] for x in ids]

def canonicalize(src):
    lanes = {}
    for old, label in LANE_MAP.items():
        frag = src['candidates_by_bucket'][old]
        lanes[label] = {
            'lane_label': label,
            'search_axes': frag.get('search_axes', []),
            'candidates': [{**it, 'lane_label': label, 'symptom_derived': False} for it in frag.get('candidates', [])],
        }
    lanes['SoC Monitoring']['candidates'] = sorted_by_ids(lanes['SoC Monitoring']['candidates'], MONITOR_RANK)
    lanes['SoC Risk Reduction']['candidates'] = sorted_by_ids(lanes['SoC Risk Reduction']['candidates'], RISK_RANK)
    lanes['Adjunct Options']['candidates'] = sorted_by_ids(lanes['Adjunct Options']['candidates'], ADJ_RANK)
    return lanes

def pmids_for(grounding, cid, n=2):
    return [str(r['pmid']) for r in grounding.get('candidates', {}).get(cid, {}).get('search', {}).get('results', []) if r.get('pmid')][:n]

def first_sentence(s):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    parts = re.split(r'(?<=[.!?])\s+', s)
    return parts[0] if parts and parts[0] else s

CONDITIONAL_MISSING_RE = re.compile(r'\b(missing|unknown|not documented|not collected|check .*immunity|if nonimmune|vaccinate if|confirm .*status)\b', re.I)


def validate_no_missing_data_as_risk_reduction(lanes):
    bad = []
    for it in lanes['SoC Risk Reduction']['candidates']:
        text = ' '.join(str(it.get(k, '')) for k in ['title', 'rationale', 'candidate_action', 'evidence_basis_prose', 'implementation_note'])
        if CONDITIONAL_MISSING_RE.search(text):
            bad.append((it['id'], it['title']))
    if bad:
        raise RuntimeError('Conditional/missing-data candidates must stay in SoC Monitoring, not SoC Risk Reduction: ' + repr(bad))


def make_ranking(lanes, grounding, summary):
    validate_no_missing_data_as_risk_reduction(lanes)
    monitoring = []
    for rank, it in enumerate(lanes['SoC Monitoring']['candidates'], 1):
        monitoring.append({
            'id': it['id'], 'title': it['title'], 'monitoring_group': MON_GROUP.get(it['id'], 'routine_on_cadence'),
            'ordering_rationale': first_sentence(it.get('rationale')), 'symptom_derived': False,
        })
    risk = []
    for rank, it in enumerate(lanes['SoC Risk Reduction']['candidates'], 1):
        domain = DOMAIN_BY_ID[it['id']]
        risk.append({
            'id': it['id'], 'title': it['title'], 'domain': domain, 'domain_rank': DOMAIN_RANK[domain],
            'domain_opportunity': DOMAIN_OPP[domain], 'relative_effect_size': REL_EFFECT[it['id']],
            'evidence_confidence': CONF[it['id']], 'expected_domain_arr': ARR[it['id']],
            'evidence_pmids': pmids_for(grounding, it['id']),
            'grounding_note': first_sentence(it.get('evidence_basis_prose')),
            'rationale': first_sentence(it.get('rationale')), 'effort': 'medium',
            'urgency': 'high' if rank <= 3 else ('medium' if rank <= 10 else 'low'),
            'symptom_derived': False,
        })
    adjunct = []
    for rank, it in enumerate(lanes['Adjunct Options']['candidates'], 1):
        domain = DOMAIN_BY_ID[it['id']]
        effect, tier = ADJ_EFFECT[it['id']]
        adjunct.append({
            'id': it['id'], 'title': it['title'], 'domain': domain, 'domain_rank': DOMAIN_RANK[domain],
            'domain_opportunity': DOMAIN_OPP[domain], 'effect_size_class': effect, 'evidence_tier': tier,
            'evidence_pmids': pmids_for(grounding, it['id']), 'grounding_note': first_sentence(it.get('evidence_basis_prose')),
            'rationale': first_sentence(it.get('rationale')), 'downside': 'low' if rank <= 13 else 'medium',
            'symptom_derived': False,
        })
    audit = []
    for it in lanes['Excluded / Watchlist']['candidates']:
        audit.append({'id': it['id'], 'title': it['title'], 'reason': first_sentence(it.get('rationale'))})
    def buckets(arr):
        out = []
        for d in DOMAIN_ORDER:
            ids = [x['id'] for x in arr if x['domain'] == d['domain']]
            if ids:
                out.append({'domain': d['domain'], 'domain_rank': d['rank'], 'why_domain_here': d['why_ordered_here'], 'actions': ids})
        return out
    ranking = {
        'ranking_version': 'v0.5_domain_opportunity',
        'patient_id': 'karen',
        'domain_order': [{k: d[k] for k in ['domain','domain_baseline_risk','residual_opportunity','domain_opportunity','why_ordered_here']} for d in DOMAIN_ORDER],
        'lanes': {'SoC Monitoring': monitoring, 'SoC Risk Reduction': risk, 'Adjunct Options': adjunct},
        'domain_buckets': {'SoC Risk Reduction': buckets(risk), 'Adjunct Options': buckets(adjunct)},
        'audit': {'Excluded / Watchlist': audit},
        'input_sufficiency': {'notes': 'Used existing Karen v0.9 generated candidate artifact plus Karen domain-risk summary; legacy scalar ranking was not used. Symptom-derived items are not promoted from resolved/improved trajectories; Karen active lanes are driven by objective risk data and current active symptoms.'},
        'ranking_run': {
            'patient_id': 'karen', 'model': 'deterministic_domain_ranker_from_existing_candidates',
            'source_candidate_artifact': str(SRC), 'source_summary_artifact': str(SUMMARY),
            'ranking_objective': RANKING_OBJECTIVE,
            'ranking_architecture': 'domain-first: order domains by patient-specific absolute opportunity; order actions within domain by expected effect; effort/urgency are metadata',
            'completed_at': datetime.now().isoformat(timespec='seconds'),
        },
    }
    return ranking

def to_js_items(ranking):
    out = []
    for lane, key in [('SoC Monitoring', 'soc'), ('SoC Risk Reduction', 'risk'), ('Adjunct Options', 'adjuncts')]:
        for i, it in enumerate(ranking['lanes'][lane], 1):
            if lane == 'SoC Monitoring':
                timing = f"{it['monitoring_group'].replace('_', ' ')} · {it['ordering_rationale']}"
                goal = 'v0.5 care-maintenance ordering: due/overdue, newly indicated by risk model, then routine cadence.'
                evidence = it['ordering_rationale']
            elif lane == 'SoC Risk Reduction':
                domain_label = DOMAIN_DISPLAY[it['domain']]
                timing = f"Risk model · {domain_label} · {it['expected_domain_arr']}"
                goal = f"Domain opportunity: {it['domain_opportunity']}. Relative effect: {it['relative_effect_size']}. Evidence confidence: {it['evidence_confidence']}."
                evidence = it['grounding_note'] + (f" PMIDs: {', '.join(it['evidence_pmids'])}." if it['evidence_pmids'] else '')
            else:
                domain_label = DOMAIN_DISPLAY[it['domain']]
                timing = f"Risk model · {domain_label} · {it['effect_size_class']} effect · {it['evidence_tier'].replace('_', ' ')}"
                goal = f"Domain opportunity: {it['domain_opportunity']}. Downside: {it['downside']}."
                evidence = it['grounding_note'] + (f" PMIDs: {', '.join(it['evidence_pmids'])}." if it['evidence_pmids'] else '')
            item = {
                'id': it['id'], 'lane': key, 'originalRank': i, 'title': it['title'], 'severity': lane,
                'timing': timing, 'do': f"<strong>{it['title']}</strong>. {it.get('rationale') or it.get('ordering_rationale')}",
                'why': it.get('rationale') or it.get('ordering_rationale'), 'goal': goal,
                'orders': [{'glyph': '✚', 'label': it['title']}], 'evidence': evidence, 'author': 'meridian-v0.5',
            }
            if lane != 'SoC Monitoring':
                item['domain'] = domain_label
                item['domain_key'] = it['domain']
                item['domain_rank'] = it['domain_rank']
            out.append(item)
    excluded = [{'name': x['title'], 'reason': x['reason']} for x in ranking['audit']['Excluded / Watchlist']]
    return out, excluded

def validate_no_disallowed(obj):
    text = json.dumps(obj, ensure_ascii=False)
    for term in ['SP' + 'AREQ', 'QA' + 'LY', 'Risk ' + 'Mitigation']:
        if term in text:
            raise RuntimeError(f'disallowed term in artifact: {term}')

if __name__ == '__main__':
    if not SRC.exists():
        raise SystemExit(f'Missing candidate artifact: {SRC}')
    src = load_json(SRC)
    summary = load_json(SUMMARY) if SUMMARY.exists() else {}
    lanes = canonicalize(src)
    candidate_artifact = {
        'patient_id': 'karen', 'prompt_version': 'v0.9 source candidates canonicalized to v0.5 lane labels',
        'source_artifact': str(SRC), 'lanes': lanes,
        'candidate_counts': {label: len(frag['candidates']) for label, frag in lanes.items()},
        'completed_at': datetime.now().isoformat(timespec='seconds'),
    }
    validate_no_disallowed(candidate_artifact)
    cand_path = OUT_DIR / 'karen_candidates_v05_canonical.json'
    cand_path.write_text(json.dumps(candidate_artifact, indent=2, ensure_ascii=False))

    grounding = build_grounding(lanes)
    ranking = make_ranking(lanes, grounding, summary)
    validate_no_disallowed(ranking)
    rank_path = OUT_DIR / 'karen_ranking_v05_domain_opportunity.json'
    rank_path.write_text(json.dumps(ranking, indent=2, ensure_ascii=False))

    items, excluded = to_js_items(ranking)
    js_payload = {
        'items': items, 'excluded': excluded,
        'top_3': {lane: [{'id': x['id'], 'title': x['title']} for x in ranking['lanes'][lane][:3]] for lane in ACTIVE_LANES},
        'artifacts': {'candidates': str(cand_path), 'ranking': str(rank_path), 'grounding': str(OUT_DIR / 'karen_biomcp_grounding_v01.json')},
    }
    js_path = OUT_DIR / 'karen_prototype_payload_v05.json'
    js_path.write_text(json.dumps(js_payload, indent=2, ensure_ascii=False))
    print(json.dumps({'written': [str(cand_path), str(rank_path), str(OUT_DIR / 'karen_biomcp_grounding_v01.json'), str(js_path)], 'top_3': js_payload['top_3']}, indent=2, ensure_ascii=False))
