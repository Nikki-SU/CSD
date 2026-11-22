import os
import unittest

from pipeline.config import Config
from pipeline.figures import figure_records, judge_caption
from pipeline.llm import SemanticJudge
from pipeline.sample import parse_journals
from pipeline.verify import verify_title


class TestJournals(unittest.TestCase):
    def test_parse_contains_expected_sources(self):
        cells = parse_journals()
        sources = {c.source_id for c in cells}
        self.assertIn("S111155417", sources)  # JACS
        self.assertIn("S205050996", sources)  # JOC
        self.assertIn("S4210199992", sources)  # JCS C: Organic
        self.assertNotIn("S4210172504", sources)  # Phys. Org. 被排除

    def test_era_and_year_range(self):
        cells = [c for c in parse_journals() if c.source_id == "S205050996"]
        self.assertTrue(any(c.era == "1950s" for c in cells))
        liebigs = [c for c in parse_journals() if c.source_id == "S4210225590"]
        self.assertTrue(any(c.year_start == 1970 and c.year_end == 1978 for c in liebigs))


class TestFigures(unittest.TestCase):
    def test_only_image_type_gets_record(self):
        content = [
            {"type": "image", "img_path": "images/a.jpg", "image_caption": ["SCHEME 1"],
             "page_idx": 0},
            {"type": "chart", "img_path": "images/b.jpg", "image_caption": None, "page_idx": 0},
        ]
        records = figure_records(content, page_offset=1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["figure_id"], "p002_f01")

    def test_scheme_caption_is_structure_without_model(self):
        judge = SemanticJudge(Config())
        verdict = judge_caption("SCHEME Reagents: i, NaBH4; ii, NaIO4", judge)
        self.assertTrue(verdict["has_structure"])
        self.assertEqual(verdict["method"], "keyword_fallback")

    def test_plot_caption_is_not_structure(self):
        judge = SemanticJudge(Config())
        verdict = judge_caption("Figure 1.-Plot of rate versus pH", judge)
        self.assertFalse(verdict["has_structure"])

    def test_empty_caption_is_unknown(self):
        judge = SemanticJudge(Config())
        self.assertIsNone(judge_caption("", judge)["has_structure"])


class TestVerify(unittest.TestCase):
    def test_same_title_verified(self):
        claim = ("Polar effects on the formation of imines from isobutyraldehyde "
                 "and primary aliphatic amines")
        page_text = ("POLAR EFFECTS ON THE FORMATION OF IMINES FROM ISOBUTYRALDEHYDE "
                     "AND PRIMARY ALIPHATIC AMINES ") * 5
        verdict = verify_title(claim, page_text, SemanticJudge(Config()))
        self.assertEqual(verdict["status"], "verified")
        self.assertEqual(verdict["similarity"], 1.0)

    def test_different_title_mismatch(self):
        claim = "A totally different paper about inorganic crystallography"
        page_text = "Polar effects on the formation of imines from isobutyraldehyde " * 5
        verdict = verify_title(claim, page_text, SemanticJudge(Config()))
        self.assertEqual(verdict["status"], "mismatch")

    def test_empty_text_unreadable(self):
        verdict = verify_title("Some title", "", SemanticJudge(Config()))
        self.assertEqual(verdict["status"], "unreadable")


@unittest.skipUnless(os.environ.get("CSD_NET"), "需要网络：CSD_NET=1")
class TestSamplingNetwork(unittest.TestCase):
    def test_openalex_returns_rows(self):
        from pipeline.sample import JournalCell, sample_cell

        cell = JournalCell("J. Org. Chem.", "1970s", 1970, 1979, "S205050996", "核心")
        rows = sample_cell(cell, 1970, limit=3)
        self.assertGreater(len(rows), 0)
        self.assertTrue(all(row["doi"] for row in rows))


if __name__ == "__main__":
    unittest.main()
