#!/usr/bin/env python3
"""
Real BioMCP-grounded Standard of Care Action Layer run for jason-real.json.
Same harness pattern as the Vitality run (fence-stripping parser, biomcp CLI tool loop).
Replaces the v1.5 SoC head-to-head run that previously failed JSON parse.
"""
import json, os, subprocess, sys, re, pathlib
import anthropic

ROOT = pathlib.Path(__file__).parent
PATIENT = json.load(open(ROOT / "jason-real.json"))

# Extract the SoC system prompt block from the combined prompt file
COMBINED = pathlib.Path("/Users/jasonyim/Projects/MeridianPatient/prompts/action-layer-prompt.md").read_text()
# SoC starts at "# Standard of Care System Prompt" and ends just before "# Patient-Specific Adjuncts System Prompt"
m = re.search(r"# Standard of Care System Prompt[\s\S]*?(?=\n# Patient-Specific Adjuncts System Prompt)", COMBINED)
assert m, "Could not extract SoC system prompt"
SOC_PROMPT = m.group(0).strip()
print(f"[prompt] SoC system prompt length: {len(SOC_PROMPT)} chars", file=sys.stderr)

# --- Inputs the SoC prompt expects ---
# 1. Raw patient data — jason-real.json (already loaded)
# 2. Domain risk model outputs — synthesize from jason-real (we don't have a separate risk-model run file)
# 3. Systemic Risk Model output — synthesize summary from the locked profile
# 4. Mandatory-Action Register — ATM het + paternal-line GI cancer = two pinned actions (already in prototype)
# 5. Compute tier — deep

DOMAIN_RISK_SUMMARY = {
    "cvd": {
        "base_risk_10yr_pct": "~1.0–1.5",
        "model": "PREVENT (post-CAC=0)",
        "modifiers": {
            "lpa_nmol_l": 72, "ldl_c_mg_dl": 121, "apo_b_mg_dl": 96,
            "cac_agatston": 0, "vo2max_ml_kg_min": 54, "hrv_30d_avg_ms": 76,
            "bp_sbp_dbp": "116/76", "non_smoker": True, "no_dm": True
        },
        "categorical": "very_low_risk_band",
        "traceability": "CAC=0 + Lp(a) optimal + BP normotensive + A1c 5.3 + elite VO2max → PREVENT very-low band, statin appropriately deferred",
        "data_gaps": ["hs-CRP not measured", "APOE genotype unknown"]
    },
    "metabolic": {
        "base_risk": "low",
        "modifiers": {"a1c": 5.3, "fasting_glucose_mg_dl": 88, "bmi_kg_m2": "lean (~22-23 est)", "no_metabolic_syndrome": True},
        "categorical": "no_active_metabolic_disease",
        "traceability": "All metabolic markers in optimal range"
    },
    "cancer": {
        "base_risk": "elevated_via_genetic",
        "modifiers": {
            "atm_heterozygous": "c.8147T>C pathogenic",
            "family_history": "paternal grandfather GI cancer (PDAC suspected per CAPS criteria)",
            "atm_lifetime_pdac_or": "5-9x", "atm_breast_male_or": "~2x",
            "atm_prostate_or": "~2x", "atm_crc_or": "~1.5-2x"
        },
        "categorical": "high_risk_via_atm_het_plus_family_hx",
        "traceability": "ATM het (DDR-impaired) + paternal-line GI cancer = composite cancer-domain elevation; load-bearing domain"
    },
    "ckd": {
        "base_risk": "low",
        "modifiers": {"egfr_creatinine_based": 72, "creatinine_mg_dl": 1.25, "uacr": "not_drawn"},
        "categorical": "stage_2_borderline_likely_athletic_creatinine",
        "traceability": "eGFR 72 + Cr 1.25 in muscular phenotype suggests Cr-based eGFR underestimates true GFR; cystatin-C confirmation indicated per KDIGO 2024"
    },
    "neurodegen": {
        "base_risk": "uninformative",
        "modifiers": {"apoe_genotype": "unknown", "subjective_cognitive": "no_complaints", "sleep_arch": "above_floor"},
        "categorical": "data_insufficient",
        "traceability": "APOE genotype is the single highest-leverage missing input; would resolve domain"
    }
}

SYSTEMIC_PATTERN = {
    "patient_picture": "47M, elite-conditioning phenotype (VO2max 54, HRV 76, CAC=0, BP 116/76, A1c 5.3) carrying ATM heterozygous P/LP variant + paternal-line GI cancer family history. Cancer is the load-bearing domain; CV runs at population baseline or below. APOE unknown.",
    "patterns": [
        {"name": "Single-domain cancer load via DDR-impaired allele + family history",
         "domains": ["cancer"],
         "summary": "ATM het impairs DSB repair (~1.5-2x CRC OR, ~5-9x lifetime PDAC risk) compounded by paternal-line GI cancer; this is the dominant mortality lever in the profile.",
         "biomcp_anchors": ["CARRIERS PMID 35353815", "CAPS 2020 PMID 31672839"]},
        {"name": "Optimized-patient profile (Cond 95 / Lifestyle 90 / Managed Risks 97)",
         "domains": ["cvd","metabolic","ckd"],
         "summary": "Below-baseline patients recover most attributable risk via cheap basics; this patient is at population-floor on those, so the next layer is allele-conditioned literature search (handled in Adjuncts bucket).",
         "biomcp_anchors": []}
    ],
    "root_causes_hypothesis": "ATM-haploinsufficient DSB-repair pressure on epithelial tissue + family-history risk amplification.",
    "open_questions": [
        "APOE genotype unknown — single highest-leverage neurodegen-domain input",
        "hs-CRP not in panel — last enhancer gap for ASCVD",
        "Cystatin-C eGFR not run — Cr-based eGFR likely underestimates true GFR in muscular phenotype",
        "PSA baseline not on file — NCCN ATM/BRCA earlier-PSA discussion at age 40+ indicated"
    ],
    "absent_but_expected": ["hs-CRP", "APOE", "cystatin-C eGFR", "PSA baseline", "DEXA (debatable at 47)"],
    "noise_excluded": ["May 2026 HRV dip — autonomic perturbation, vitality-domain not risk-domain"]
}

REGISTER_PINS = [
    {
        "register_trigger_id": "ACMG-SF-ATM",
        "action_name": "Genetic counseling + cascade testing for ATM heterozygous P/LP variant",
        "guideline_basis": "ACMG SF v3.2 (Miller 2022) · NCCN Genetic/Familial High-Risk v2.2024",
        "intervention": "Refer to clinical geneticist for ATM c.8147T>C heterozygous P/LP confirmation, counseling, and cascade testing of first-degree relatives.",
        "mechanism": "P/LP variant on ACMG Secondary Findings list. Counseling + gene-specific surveillance + cascade testing are guideline-mandated.",
        "tracking_metric": "Geneticist visit completed; cascade offer documented for 1° relatives",
        "urgency": "this visit",
        "citations": [{"pmid": "35802134", "doi": "", "supports": "ACMG SF v3.2"},
                      {"pmid": "35353815", "doi": "", "supports": "CARRIERS — ATM cancer ORs"}],
        "evidence_status": "biomcp_grounded"
    },
    {
        "register_trigger_id": "ATM-CAPS-pancreas",
        "action_name": "Annual pancreatic surveillance per CAPS 2020 — start age 50",
        "guideline_basis": "International CAPS Consortium 2020 (Goggins et al.) · NCCN pancreas v1.2024",
        "intervention": "Document plan for annual MRI/MRCP + EUS starting age 50.",
        "mechanism": "ATM het + 2° relative with PDAC meets CAPS criteria. ATM ~5-9x lifetime PDAC risk; stage-shift detection is the dominant lever.",
        "tracking_metric": "Plan in chart; first imaging scheduled at age 50",
        "urgency": "document this visit",
        "citations": [{"pmid": "31672839", "doi": "", "supports": "CAPS 2020"}],
        "evidence_status": "biomcp_grounded"
    }
]

PAYLOAD = {
    "raw_patient_data": PATIENT,
    "domain_risk_outputs": DOMAIN_RISK_SUMMARY,
    "systemic_risk_model_output": SYSTEMIC_PATTERN,
    "mandatory_action_register": REGISTER_PINS,
    "compute_tier": "deep"
}

USER_MSG = f"""Run the Standard of Care Action Layer for this patient. Follow the system prompt exactly.

Use BioMCP to ground every candidate. Cite real PMIDs. Return JSON only.

Patient + risk + register payload:
```json
{json.dumps(PAYLOAD, indent=2)}
```
"""

# --- BioMCP tool wiring ---
BIOMCP_TOOL = {
    "name": "biomcp_search",
    "description": "Search biomedical literature via BioMCP CLI (PubTator3 + Europe PMC). Returns PMIDs + titles + abstracts. Use for grounding every claim.",
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

# --- Run Claude with BioMCP tool loop ---
client = anthropic.Anthropic()
MODEL = "claude-opus-4-7"
print(f"[start] SoC run, model={MODEL}", file=sys.stderr)

messages = [{"role": "user", "content": USER_MSG}]
biomcp_calls = 0
biomcp_log = []
MAX_BIOMCP = 20  # SoC budget per spec
MAX_TURNS = 50

for turn in range(MAX_TURNS):
    resp = client.messages.create(
        model=MODEL,
        max_tokens=12000,
        system=SOC_PROMPT,
        tools=[BIOMCP_TOOL],
        messages=messages
    )
    print(f"[turn {turn}] stop_reason={resp.stop_reason} biomcp_calls={biomcp_calls}", file=sys.stderr)
    messages.append({"role": "assistant", "content": resp.content})

    if resp.stop_reason == "end_turn":
        final_text = ""
        for block in resp.content:
            if block.type == "text":
                final_text += block.text
        cleaned = final_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
        try:
            parsed = json.loads(cleaned)
        except Exception as e:
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
        json.dump(result, open(ROOT / "jason-real-action-layer-soc.json", "w"), indent=2, ensure_ascii=False)
        print(f"[done] wrote jason-real-action-layer-soc.json (biomcp_calls={biomcp_calls})", file=sys.stderr)
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

    print(f"[bail] unexpected stop_reason {resp.stop_reason}", file=sys.stderr)
    break
else:
    print("[bail] exceeded MAX_TURNS", file=sys.stderr)
