Meridian Risk Action Candidate Discovery Prompt
Version: draft 1.2
Purpose: broad candidate discovery, then strict lane classification

## Core rule

Generate broadly. Classify strictly.

Do not generate by lane quota. First create a broad candidate pool from the patient payload. Then assign each candidate to exactly one lane using the gates below.

Active lane labels:
- SoC Monitoring
- SoC Risk Reduction
- Adjunct Options

Audit label:
- Excluded / Watchlist

Do not use aliases.

Symptom trajectory is a hard gate: resolved/improved symptoms can preserve phenotype history, but they can only generate baseline-closure or watchlist actions unless recurrence, abnormal objective data, active therapy, stones/tophi, red flags, or current burden is present.

## Maintenance exclusion rule

Maintenance is not an action candidate.

Do not spend candidate slots on preserving, continuing, maintaining, reinforcing, or praising behaviors already present in the patient state.

Maintenance may appear only as:
- protected-state context
- rationale for why fewer action candidates exist
- monitoring metric
- stop/continue instruction inside an existing plan

Exception: a maintenance-themed idea can become an action candidate only if it introduces a new operational delta: new cadence, threshold, protocol, escalation rule, measurement loop, or treatment change.

## Boundaries

- No retrieval during generation.
- No scoring or ranking.
- No invented facts, citations, PMIDs, effect sizes, or guideline years.
- No patient-specific facts in this prompt. Use only the runtime payload.
- Candidate order has no rank meaning.
- Preserve useful candidates even when they do not qualify for SoC Risk Reduction.

## Input

```json
{
  "target_candidate_pool_count": 60,
  "target_minimums_after_classification": {
    "SoC Monitoring": 15,
    "SoC Risk Reduction": 0,
    "Adjunct Options": 15,
    "Excluded / Watchlist": 10
  },
  "patient_payload": {
    "raw_patient_data": {},
    "domain_risk_models": {},
    "systemic_risk_model": {},
    "symptom_capture": {},
    "mandatory_action_register": {},
    "existing_plan_state": {},
    "compute_tier": "deep"
  }
}
```

## Output

Return JSON only:

```json
{
  "prompt_version": "draft 1.2",
  "search_axes": [],
  "candidate_pool": [],
  "classified_lanes": {
    "SoC Monitoring": [],
    "SoC Risk Reduction": [],
    "Adjunct Options": [],
    "Excluded / Watchlist": []
  },
  "lane_purity_audit": {
    "soc_risk_reduction_rejected_candidates": [],
    "thin_lanes": [],
    "classification_uncertainties": []
  },
  "candidate_discovery_qa_fragment": {
    "generation_only_boundary_preserved": true,
    "canonical_lane_labels_used": true,
    "broad_generation_preserved": true,
    "strict_classification_applied": true,
    "prompt_used_patient_specific_hardcoding": false,
    "notes": []
  }
}
```

## Axis schema

```json
{
  "axis_id": "AX1",
  "axis_name": "",
  "source": "raw_data | domain_risk_model | systemic_pattern | symptom_capture | genetics | family_history | data_gap | exposure | existing_plan_state | patient_state",
  "patient_signal": "",
  "trajectory_status": "active | intermittent | improved | resolved | worse | unknown | not_symptom_derived",
  "allowed_action_scope": "active_management | monitoring | baseline_closure | watchlist_only | not_symptom_derived",
  "possible_action_jobs": ["SoC Monitoring", "SoC Risk Reduction", "Adjunct Options", "Excluded / Watchlist"],
  "why_this_axis_may_generate_actions": ""
}
```

## Candidate pool schema

Each broad candidate must use this schema before lane assignment:

```json
{
  "pool_id": "POOL-001",
  "title": "",
  "candidate_action": "",
  "source_axis_ids": [],
  "trajectory_status": "active | intermittent | improved | resolved | worse | unknown | not_symptom_derived",
  "allowed_action_scope": "active_management | monitoring | baseline_closure | watchlist_only | not_symptom_derived",
  "patient_signal_from_inputs": "",
  "candidate_job": "screen | monitor | verify | treat | reduce_exposure | change_behavior | preserve_state | optimize | symptom_support | exclude",
  "warrant_type": "standard_care | guideline_grade | standard_practice | human_outcome | human_biomarker | mechanism_plus_human_signal | close_analog | very_low_downside | harm_or_not_indicated",
  "current_eligibility_state": "eligible_now | eligible_if_confirmed | not_currently_eligible | unknown",
  "directness_to_modeled_risk": "direct | indirect | preservation | unclear",
  "standard_care_status": "standard_care | standard_practice | not_standard_care | unknown",
  "missing_data_dependency": "",
  "evidence_basis_prose": "",
  "known_uncertainties": [],
  "known_harms_or_tradeoffs": []
}
```

## Lane gates

### SoC Monitoring

Use for screening, surveillance, monitoring, referral, diagnostic gates, eligibility closure, record closure, counseling, or deintensification.

Missing data belongs here when it determines whether a standard pathway is active.

### SoC Risk Reduction

A candidate qualifies only if all four are true:

1. It is an active intervention.
2. The patient is currently eligible, or eligibility is already established in the payload.
3. It is standard-care, guideline-grade, or standard-practice.
4. It directly lowers a modeled risk driver.

Default out of this lane if the candidate is mainly preservation, optimization, symptom support, maintenance, optional experimentation, or eligibility verification.

If eligibility is unknown, put the verification action in SoC Monitoring.

### Adjunct Options

Use for optional candidates with patient-specific signal but without the SoC Risk Reduction gate.

This lane should preserve mechanism-grounded, optimized-patient, symptom/function, preservation, low-downside, and human-signal candidates.

### Excluded / Watchlist

Use for candidates that are speculative, not indicated, contradicted, duplicate, unsafe, or only relevant if the patient state changes.

## Classified lane item schemas

### SoC Monitoring

```json
{
  "id": "SOCM-001",
  "source_pool_id": "POOL-001",
  "lane_label": "SoC Monitoring",
  "trajectory_status": "active | intermittent | improved | resolved | worse | unknown | not_symptom_derived",
  "allowed_action_scope": "active_management | monitoring | baseline_closure | watchlist_only | not_symptom_derived",
  "title": "",
  "action_function": "screening | surveillance | monitoring | referral | diagnostic_gate | data_quality | counseling | deintensification",
  "trigger": "",
  "modality": "",
  "due_status": "",
  "interval": "",
  "escalation_threshold": "",
  "de_intensification_or_stop_rule": "",
  "missing_data_dependency": "",
  "evidence_basis_prose": "",
  "why_this_lane": "",
  "symptom_derived": false,
  "known_uncertainties": [],
  "known_harms_or_tradeoffs": []
}
```

### SoC Risk Reduction

```json
{
  "id": "SOCR-001",
  "source_pool_id": "POOL-001",
  "lane_label": "SoC Risk Reduction",
  "trajectory_status": "active | intermittent | improved | resolved | worse | unknown | not_symptom_derived",
  "allowed_action_scope": "active_management | monitoring | baseline_closure | watchlist_only | not_symptom_derived",
  "title": "",
  "action_function": "treatment | medication | nutrition | lifestyle | exposure_reduction | procedure | behavior_change | deprescribing | safety_precaution",
  "risk_driver": "",
  "headline_intervention": "",
  "target": "",
  "initiation_or_escalation_threshold": "",
  "follow_up_metric": "",
  "harm_tradeoff": "",
  "evidence_basis_prose": "",
  "implementation_note": "",
  "why_this_lane": "Must satisfy active + eligible + standard-care/standard-practice + direct modeled-risk-driver gate.",
  "symptom_derived": false,
  "known_uncertainties": [],
  "dependencies_or_required_prior_data": []
}
```

### Adjunct Options

```json
{
  "id": "ADJ-001",
  "source_pool_id": "POOL-001",
  "lane_label": "Adjunct Options",
  "trajectory_status": "active | intermittent | improved | resolved | worse | unknown | not_symptom_derived",
  "allowed_action_scope": "active_management | monitoring | baseline_closure | watchlist_only | not_symptom_derived",
  "title": "",
  "action_function": "nutrition | exposure_reduction | supplement | monitoring | counseling | behavior_change | diagnostic_gate | environmental | repurposed_medication | preservation | symptom_support | other",
  "patient_signal_from_inputs": "",
  "mechanism_or_analog_rationale": "",
  "evidence_tier": "human_biomarker | close_analog_human | epidemiology_plus_mechanism | mechanism_plus_human_signal | very_low_downside",
  "implementation": "",
  "monitoring_signal": "",
  "stop_rule": "",
  "downside": "",
  "why_not_soc": "",
  "why_this_lane": "",
  "symptom_derived": false,
  "known_uncertainties": []
}
```

### Excluded / Watchlist

```json
{
  "id": "EXCL-001",
  "source_pool_id": "POOL-001",
  "lane_label": "Excluded / Watchlist",
  "trajectory_status": "active | intermittent | improved | resolved | worse | unknown | not_symptom_derived",
  "allowed_action_scope": "active_management | monitoring | baseline_closure | watchlist_only | not_symptom_derived",
  "title": "",
  "source_family": "",
  "rejection_reason": "",
  "what_would_change_status": "",
  "duplicate_of": "",
  "harm_or_uncertainty": ""
}
```

## Validation rules

- Generate the broad pool before classification.
- Assign every pool candidate to exactly one lane or audit label.
- Do not force a lane to reach a count by weakening its gate.
- If SoC Risk Reduction is thin, report it as thin.
- Do not move a candidate into SoC Risk Reduction unless it satisfies the four-part gate.
- Resolved/improved symptom-derived candidates must have allowed_action_scope of baseline_closure or watchlist_only unless the candidate names the objective current evidence that reopens active management.
- Reject active cadence, treatment targets, or intervention language from resolved/improved symptoms without current evidence.
- Keep SoC Monitoring and Adjunct Options broad enough to preserve useful candidates.
- Ranking happens downstream only after lane purity passes.
