# Meridian Action Layer Failure Notes

Date: 2026-05-10
Context: SoC / Patient-Specific Adjuncts repair attempt around commits `a389829` and `7a146e2`.

## Bottom line

The current live artifact after `7a146e2` must not be treated as a valid SPAREQ-ranked care plan. It contains useful evidence about missing candidate categories, but the ranking method is contaminated.

## What went wrong

1. **Unauthorized SPAREQ substitution**
   - The scorer kept the SPAREQ acronym and weights but changed the meaning of dimensions.
   - Correct protocol definitions:
     - S = severity of the adverse outcome.
     - P = probability of that adverse outcome for THIS patient.
     - A = action impact, scored as max(outcome-redirect, stage-shift, trajectory-anchor).
     - R = reversibility / urgency window.
     - E = effort, inverted, where easier scores higher.
     - Q = evidence quality.
   - Bad `7a146e2` scorer changed these to:
     - P = whether the patient triggers the rule.
     - R = readiness / feasibility.
     - E = harm / burden.
   - This is a different scoring instrument wearing the SPAREQ label.

2. **Candidate-generation / classification bug**
   - The deterministic SoC candidate register added universal checklist items directly into the ranked SoC stack.
   - HCV, HIV, HepB, Tdap, flu/COVID are real SoC maintenance items, but they should not compete against patient-specific leverage actions unless elevated by a patient-specific risk signal.
   - The ranked stack mixed different object types:
     - register pins
     - patient-specific SoC priorities
     - routine preventive maintenance
     - data-quality gates
     - adjuncts / research-adjacent items

3. **Why HCV/HIV floated to the top**
   - They were universal, guideline-backed, cheap, low-burden, and missing from source data.
   - Under the altered scorer, those properties produced near-perfect scores.
   - Under true SPAREQ, they are maintenance checklist items unless there is a patient-specific infectious-risk signal.

4. **CAPS / family-history correction exposed downstream contamination**
   - Current real source says paternal grandfather “GI cancer,” not confirmed pancreatic cancer.
   - Therefore pancreatic surveillance should not be pinned as CAPS-eligible from current source data.
   - Correct action is family-history primary-site clarification.
   - Existing Patient-Specific Adjuncts artifact still assumes pancreatic surveillance is `covered_by_soc_bucket` and uses unspecified GI family history too strongly.

5. **Adjunct lane is stale / provisional**
   - `jason-real-action-layer-v15.json` predates the corrected SoC method.
   - It should not be accepted as final because it depends on stale SoC coverage assumptions and ambiguous GI-family-history interpretation.

## Commits involved

- `45346bf`: Adjuncts + Vitality lane added. Adjuncts from real BioMCP-grounded run but now stale because SoC/CAPS assumptions changed.
- `a389829`: SoC rerun surfaced PSA but used a prompt-patch/harness, not full method.
- `7a146e2`: deterministic SoC register added, but introduced bad ranking semantics and flattened checklist items into ranked SoC.

## What should be preserved

Useful from `7a146e2`:
- Deterministic enumeration catches under-recall.
- Lp(a) guard: Jason's Lp(a) is 72 nmol/L, never mg/dL.
- PSA must be seeded by age + sex + ATM carrier status.
- Ambiguous paternal GI cancer must not be converted to PDAC / CAPS eligibility.
- Cystatin C should be paired with UACR for kidney confirmation.

Invalid from `7a146e2`:
- SPAREQ scores.
- Ranked order.
- Any claim that HCV/HIV are top patient-specific priorities.
- Any artifact that says “real-method ranked” without restoring SPAREQ definitions.

## Correct next architecture

Do not simply reshuffle the list. First type candidates, then score only rankable candidates.

Candidate types:
1. `register_pin`: mandatory, non-rankable.
2. `patient_specific_soc`: guideline-backed and specifically triggered by this patient's risk state.
3. `routine_preventive_maintenance`: universal adult checklist items, visible but not top-priority ranked unless elevated by patient-specific signal.
4. `data_quality_gate`: ambiguity/missing data that must be resolved before acting.
5. `patient_specific_adjunct`: profile-conditioned, outside standard guidelines, must pass human-evidence floor.
6. `research_gap`: plausible but not actionable.

For Jason right now:
- Register pin: ATM genetics/cascade.
- Patient-specific SoC / data-quality priorities: CRC screening, baseline PSA, clarify paternal GI cancer primary before CAPS decision, cystatin C + UACR.
- Routine preventive maintenance: HCV, HIV, HepB, Tdap, flu/COVID.
- Adjuncts: rerun after trigger validation; do not assume GI cancer = gastric/CRC/PDAC.

## Safety rule for next session

If a future artifact uses SPAREQ, verify the dimension definitions before scoring. Do not accept any scorer that changes P/R/E semantics while preserving the acronym.
