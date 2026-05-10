#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

from soc_candidate_register import build_soc_candidate_register

ROOT = Path(__file__).parent


class SoCRegisterTests(unittest.TestCase):
    def setUp(self):
        with open(ROOT / 'jason-real.json') as f:
            self.patient = json.load(f)
        self.reg = build_soc_candidate_register(self.patient)
        self.ids = {c['id'] for c in self.reg['candidates']}

    def test_lpa_unit_is_nmol_l_and_not_blocked(self):
        self.assertEqual(self.patient['labs']['lp_a']['unit'], 'nmol/L')
        self.assertEqual(self.reg['data_quality_flags'], [])

    def test_universal_age_sex_services_are_seeded_before_llm(self):
        expected = {
            'SOC-PREV-CRC-45',
            'SOC-INF-HCV-ONE-TIME',
            'SOC-INF-HIV-ONE-TIME',
            'SOC-IMM-HBV',
            'SOC-IMM-TDAP',
            'SOC-IMM-FLU-COVID',
        }
        self.assertTrue(expected.issubset(self.ids), self.ids)

    def test_atm_seeds_psa_and_genetics_before_llm(self):
        self.assertIn('SOC-GEN-ATM-CASCADE', self.ids)
        self.assertIn('SOC-CANCER-PSA-ATM', self.ids)

    def test_unspecified_gi_history_does_not_pin_pancreatic_surveillance(self):
        self.assertIn('SOC-CANCER-FH-CLARIFY-PDAC', self.ids)
        self.assertNotIn('SOC-CANCER-PANCREAS-ATM-FH', self.ids)
        excluded = {x['source_rule'] for x in self.reg['considered_and_excluded']}
        self.assertIn('CAPS_PIN_BLOCKED_BY_UNSPECIFIED_GI_FH', excluded)

    def test_kidney_confirmation_includes_uacr_not_cystatin_only(self):
        c = next(c for c in self.reg['candidates'] if c['id'] == 'SOC-CKD-CYSTATIN-UACR')
        self.assertIn('cystatin C', c['intervention'])
        self.assertIn('urine albumin-creatinine ratio', c['intervention'])

    def test_hscrp_is_not_ranked_as_standalone_soc_candidate_for_current_state(self):
        names = [c['action_name'].lower() for c in self.reg['candidates']]
        self.assertFalse(any('hs-crp' in n for n in names))
        excluded = {x['source_rule'] for x in self.reg['considered_and_excluded']}
        self.assertIn('ACC_AHA_HSCRP_EVOI_FAIL_CURRENT_STATE', excluded)


if __name__ == '__main__':
    unittest.main()
