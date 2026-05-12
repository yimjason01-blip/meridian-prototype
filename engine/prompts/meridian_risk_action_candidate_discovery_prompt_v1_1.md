Meridian Risk Action Candidate Discovery Prompt
Version: draft 1.1
Purpose: generate candidate actions only

## Core rule

Generate only candidates that fit the requested lane.

- SoC Monitoring = standard-care tracking, screening, cadence, eligibility, and record closure.
- SoC Risk Reduction = actions expected to materially reduce this patient's modeled risk.
- Adjunct Options = optional non-SoC actions with a patient-specific signal and plausible human evidence.
- Excluded / Watchlist = audit only.

- Missing records belong in SoC Monitoring unless the missing fact itself blocks a modeled-risk-lowering decision.
- Symptom trajectory is a hard gate: resolved/improved symptoms can preserve phenotype history, but they can only generate baseline-closure or watchlist actions unless recurrence, abnormal objective data, active therapy, stones/tophi, red flags, or current burden is present.

## Boundaries

- No retrieval.
- No scoring or ranking.
- No invented facts, citations, PMIDs, effect sizes, or guideline years.
- No patient-specific facts in this prompt. Use only the runtime payload.
- Use exact lane labels only.

Allowed active lane labels:
- SoC Monitoring
- SoC Risk Reduction
- Adjunct Options

Do not use aliases.

## Input

```json
{
  "lane_label": "SoC Monitoring | SoC Risk Reduction | Adjunct Options | Excluded / Watchlist",
  "target_count": 15,
  "required_candidate_ids": [],
  "patient_payload": {
    "raw_patient_data": {},
    "domain_risk_models": {},
    "systemic_risk_model": {},
    "symptom_capture": {},
    "mandatory_action_register": {},
    "existing_plan_state": {},
    "compute_tier": "deep"
  },
  "axes_from_prior_calls": []
}
```

## Output

Return JSON only:

```json
{
  "lane_label": "",
  "search_axes": [],
  "candidates": [],
  "lane_coverage_audit": {},
  "candidate_discovery_qa_fragment": {
    "generation_only_boundary_preserved": true,
    "canonical_lane_label_used": true,
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

## Candidate schemas

### SoC Monitoring

```json
{
  "id": "SOCM-001",
  "lane_label": "SoC Monitoring",
  "title": "",
  "action_function": "screening | surveillance | monitoring | referral | diagnostic_gate | data_quality | counseling | deintensification",
  "source_axis_ids": [],
  "trajectory_status": "active | intermittent | improved | resolved | worse | unknown | not_symptom_derived",
  "allowed_action_scope": "active_management | monitoring | baseline_closure | watchlist_only | not_symptom_derived",
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
  "lane_label": "SoC Risk Reduction",
  "title": "",
  "action_function": "treatment | medication | nutrition | lifestyle | exposure_reduction | procedure | behavior_change | risk_factor_optimization | deprescribing | safety_precaution",
  "source_axis_ids": [],
  "trajectory_status": "active | intermittent | improved | resolved | worse | unknown | not_symptom_derived",
  "allowed_action_scope": "active_management | monitoring | baseline_closure | watchlist_only | not_symptom_derived",
  "risk_driver": "",
  "headline_intervention": "",
  "target": "",
  "initiation_or_escalation_threshold": "",
  "follow_up_metric": "",
  "harm_tradeoff": "",
  "evidence_basis_prose": "",
  "implementation_note": "",
  "why_this_lane": "",
  "symptom_derived": false,
  "known_uncertainties": [],
  "dependencies_or_required_prior_data": []
}
```

### Adjunct Options

```json
{
  "id": "ADJ-001",
  "lane_label": "Adjunct Options",
  "title": "",
  "action_function": "nutrition | exposure_reduction | supplement | monitoring | counseling | behavior_change | diagnostic_gate | environmental | repurposed_medication | other",
  "source_axis_ids": [],
  "trajectory_status": "active | intermittent | improved | resolved | worse | unknown | not_symptom_derived",
  "allowed_action_scope": "active_management | monitoring | baseline_closure | watchlist_only | not_symptom_derived",
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
  "lane_label": "Excluded / Watchlist",
  "title": "",
  "source_axis_ids": [],
  "trajectory_status": "active | intermittent | improved | resolved | worse | unknown | not_symptom_derived",
  "allowed_action_scope": "active_management | monitoring | baseline_closure | watchlist_only | not_symptom_derived",
  "source_family": "",
  "rejection_reason": "",
  "what_would_change_status": "",
  "duplicate_of": "",
  "harm_or_uncertainty": ""
}
```

## Validation rules

- Produce exactly the requested count.
- Use required_candidate_ids exactly, in order.
- One action per candidate.
- Candidate order has no rank meaning.
- Resolved/improved symptom-derived candidates must have allowed_action_scope of baseline_closure or watchlist_only unless the candidate names the objective current evidence that reopens active management.
- Reject active cadence, treatment targets, or intervention language from resolved/improved symptoms without current evidence.
- Do not create fake candidates to satisfy the count.
- If the lane cannot reach the count, return workflow_incomplete.
