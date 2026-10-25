import csv
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from plastprior import chemical_families as families


@unittest.skipUnless(families.RDKIT_AVAILABLE, "RDKit is required for structure classification tests")
class ChemicalFamilyClassificationTests(unittest.TestCase):
    def assert_categories(self, smiles, expected):
        result = families.classify_smiles(smiles)
        actual = {label.strip() for label in result["category_labels"].split(";") if label.strip()}
        self.assertEqual(set(expected), actual)

    def test_pbde_and_pbb_are_separated_by_ether_oxygen(self):
        deca_bde = "Brc1c(Br)c(Br)c(Oc2c(Br)c(Br)c(Br)c(Br)c2Br)c(Br)c1Br"
        deca_bb = "Brc1c(Br)c(Br)c(-c2c(Br)c(Br)c(Br)c(Br)c2Br)c(Br)c1Br"
        self.assert_categories(deca_bde, {"PBDE"})
        self.assert_categories(deca_bb, {"PBB"})

    def test_classic_pcb(self):
        self.assert_categories("Clc1ccccc1-c1ccccc1Cl", {"PCB"})

    def test_chlorinated_dioxin_and_furan_are_separate_families(self):
        tcdd = "Clc1cc2c(cc1Cl)Oc1cc(Cl)c(Cl)cc1O2"
        hcdf = "Clc1cc2c(oc3cc(Cl)c(Cl)c(Cl)c32)c(Cl)c1Cl"
        self.assert_categories(tcdd, {"PCDD"})
        self.assert_categories(hcdf, {"PCDF"})

    def test_brominated_dioxin_and_furan_are_separate_families(self):
        tbdd = "Brc1cc2c(cc1Br)Oc1cc(Br)c(Br)cc1O2"
        hbdf = "Brc1cc2c(oc3cc(Br)c(Br)c(Br)c32)c(Br)c1Br"
        self.assert_categories(tbdd, {"PBDD"})
        self.assert_categories(hbdf, {"PBDF"})

    def test_mixed_halogen_dioxin_is_audited_without_false_pure_family(self):
        result = families.classify_smiles(
            "Clc1cc2c(cc1Br)Oc1cc(Cl)c(Br)cc1O2"
        )
        self.assertEqual("", result["category_labels"])
        self.assertEqual("ok_with_warning", result["status"])
        self.assertIn("mixed_chlorinated_brominated_dibenzo-p-dioxin", result["warning"])

    def test_monohalogenated_dioxin_is_excluded_from_poly_family(self):
        result = families.classify_smiles("Clc1ccc2c(c1)Oc1ccccc1O2")
        self.assertEqual("", result["category_labels"])
        self.assertEqual("ok_with_warning", result["status"])
        self.assertIn(
            "monohalogenated_dibenzo-p-dioxin_excluded_from_poly_family",
            result["warning"],
        )

    def test_ope_excludes_phosphite_and_phosphonate(self):
        self.assert_categories("O=P(OCC)(OCC)OCC", {"OPE"})
        self.assert_categories("P(OCC)(OCC)OCC", set())
        self.assert_categories("O=P(C)(OCC)OCC", set())

    def test_oecd_pfas_rule_does_not_require_cf3_cf2_sequence(self):
        self.assert_categories("FC(F)(F)c1ccccc1", {"PFAS"})
        self.assert_categories("CC(F)C", set())

    def test_sodium_potassium_ammonium_and_acid_share_parent(self):
        structures = [
            "O=C([O-])C(F)(F)C(F)(F)F.[Na+]",
            "O=C([O-])C(F)(F)C(F)(F)F.[K+]",
            "O=C([O-])C(F)(F)C(F)(F)F.[NH4+]",
            "O=C(O)C(F)(F)C(F)(F)F",
        ]
        results = [families.classify_smiles(smiles) for smiles in structures]
        self.assertEqual(1, len({result["parent_smiles"] for result in results}))
        self.assertTrue(all(result["category_labels"] == "PFAS" for result in results))
        self.assertTrue(all(result["is_salt"] for result in results[:3]))
        self.assertFalse(results[3]["is_salt"])

    def test_structure_can_have_multiple_family_labels(self):
        fluorinated_phosphate = "O=P(O)(O)OCC(F)(F)C(F)(F)F"
        self.assert_categories(fluorinated_phosphate, {"OPE", "PFAS"})

    def test_neutral_mixture_is_not_reported_as_salt(self):
        result = families.classify_smiles("CCO.O")
        self.assertFalse(result["is_salt"])
        self.assertEqual("multicomponent_nonionic", result["warning"])

    def test_organic_counterion_salt_is_detected_from_fragment_charges(self):
        result = families.classify_smiles(
            "CC[N+](CC)(CC)CC.O=S(=O)([O-])C(F)(F)C(F)(F)C(F)(F)C(F)(F)C(F)(F)C(F)(F)C(F)(F)C(F)(F)F"
        )
        self.assertTrue(result["is_salt"])
        self.assertEqual("PFAS", result["category_labels"])

    def test_pfas_anion_is_not_lost_when_organic_cation_is_larger(self):
        result = families.classify_smiles(
            "CCCC[P+](CCCC)(CCCC)CCCC.O=S(=O)([O-])C(F)(F)C(F)(F)F"
        )
        self.assertTrue(result["is_salt"])
        self.assertEqual("PFAS", result["category_labels"])

    def test_csv_postprocessor_appends_one_main_column_and_preserves_input(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            source = tmp / "compound_priority_table.csv"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Inchikey_std", "Name_std", "CAS", "Smile_std", "Priority_score"])
                writer.writeheader()
                writer.writerow({
                    "Inchikey_std": "WHHGLZMJPXIBIX-UHFFFAOYSA-N",
                    "Name_std": "Decabromodiphenyl oxide",
                    "CAS": "1163-19-5",
                    "Smile_std": "Brc1c(Br)c(Br)c(Oc2c(Br)c(Br)c(Br)c(Br)c2Br)c(Br)c1Br",
                    "Priority_score": "24",
                })

            result = families.classify_priority_csv(source)
            self.assertTrue(source.exists())
            self.assertNotEqual(source, result["output_csv"])
            with result["output_csv"].open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(1, len(rows))
            self.assertEqual("PBDE", rows[0]["category_labels"])
            self.assertEqual("24", rows[0]["Priority_score"])
            self.assertEqual(1, result["summary"]["categorized_rows"])

    def test_dataframe_postprocessor_changes_only_category_labels(self):
        source = pd.DataFrame([
            {
                "Inchikey_std": "WHHGLZMJPXIBIX-UHFFFAOYSA-N",
                "Name_std": "Decabromodiphenyl oxide",
                "CAS": "1163-19-5",
                "Smile_std": "Brc1c(Br)c(Br)c(Oc2c(Br)c(Br)c(Br)c(Br)c2Br)c(Br)c1Br",
                "Priority_score": 24.0,
            },
            {
                "Inchikey_std": "MISSING",
                "Name_std": "Missing structure",
                "CAS": "",
                "Smile_std": float("nan"),
                "Priority_score": 3.0,
            },
        ])
        original = source.copy(deep=True)
        result = families.classify_priority_dataframe(source)
        output = result["agg_table"]
        pd.testing.assert_frame_equal(source, original)
        pd.testing.assert_frame_equal(output[original.columns], original)
        self.assertEqual(["PBDE", ""], output["category_labels"].tolist())
        self.assertEqual(2, len(result["audit_rows"]))
        self.assertEqual({"missing_smiles": 1, "ok": 1}, result["summary"]["classification_status_counts"])


if __name__ == "__main__":
    unittest.main()
