import tempfile
import unittest
from pathlib import Path

from pipeline.cell import doi_slug, run_cell
from pipeline.config import Config
from pipeline.sample import JournalCell
from pipeline.screen import classify_caption


CELL = JournalCell("J. Org. Chem.", "1970s", 1970, 1979, "S205050996", "核心")


def _pdf(pdf_dir: Path, doi: str) -> None:
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / f"{doi_slug(doi)}.pdf").write_bytes(b"%PDF-fake")


def _result(doi: str, **overrides) -> dict:
    base = {
        "doi": doi,
        "verify_status": "verified",
        "has_figures": True,
        "captionless": False,
        "structure": True,
        "status": "structure",
        "mineru_used": False,
        "needs_mineru": False,
        "figure_pages": [1],
    }
    base.update(overrides)
    return base


class TestCaption(unittest.TestCase):
    def test_scheme_is_structure(self):
        self.assertEqual(classify_caption("SCHEME Reagents: i, NaBH4"), "structure")

    def test_plot_is_not_structure(self):
        self.assertEqual(classify_caption("Figure 1. Plot of rate versus pH"), "non_structure")

    def test_plain_figure_is_ambiguous(self):
        self.assertEqual(classify_caption("Figure 1."), "ambiguous")


class TestCellLoop(unittest.TestCase):
    def test_stops_at_five_accepted_in_first_round(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir = Path(tmp) / "pdfs"
            rows = []
            for index in range(20):
                doi = f"10.1000/test{index}"
                _pdf(pdf_dir, doi)
                rows.append({"doi": doi})

            calls = []

            def sample_fn(cell, year, limit, config):
                calls.append(1)
                return rows

            def screen_fn(pdf, doi, out, config):
                return _result(doi)

            summary = run_cell(
                CELL, 1970, pdf_dir, Path(tmp) / "out", Config(),
                sample_fn=sample_fn, screen_fn=screen_fn,
            )
            self.assertEqual(summary["accepted"], 5)
            self.assertEqual(summary["rounds"], 1)
            self.assertEqual(len(calls), 1)

    def test_five_rounds_then_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir = Path(tmp) / "pdfs"
            counter = {"round": 0}

            def sample_fn(cell, year, limit, config):
                counter["round"] += 1
                rows = []
                for index in range(20):
                    doi = f"10.2000/r{counter['round']}_{index}"
                    _pdf(pdf_dir, doi)
                    rows.append({"doi": doi})
                return rows

            def screen_fn(pdf, doi, out, config):
                return _result(doi, has_figures=False, structure=False, status="no_figures")

            out = Path(tmp) / "out"
            summary = run_cell(
                CELL, 1970, pdf_dir, out, Config(),
                sample_fn=sample_fn, screen_fn=screen_fn,
            )
            self.assertEqual(summary["accepted"], 0)
            self.assertEqual(summary["rounds"], 5)
            self.assertTrue((out / "gaps.csv").exists())

    def test_captionless_at_threshold_stops_and_alarms(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir = Path(tmp) / "pdfs"
            rows = []
            for index in range(20):
                doi = f"10.3000/c{index}"
                _pdf(pdf_dir, doi)
                rows.append({"doi": doi})

            def sample_fn(cell, year, limit, config):
                return rows

            def screen_fn(pdf, doi, out, config):
                if int(doi.rsplit("c", 1)[1]) < 5:
                    return _result(doi, structure=None, captionless=True, status="captionless")
                return _result(doi, has_figures=False, structure=False, status="no_figures")

            out = Path(tmp) / "out"
            summary = run_cell(
                CELL, 1970, pdf_dir, out, Config(),
                sample_fn=sample_fn, screen_fn=screen_fn,
            )
            outcomes = [r["outcome"] for r in summary["records"]]
            self.assertTrue(summary["alarm"])
            self.assertIn("pending_human", outcomes)
            self.assertNotIn("skipped_captionless", outcomes)
            self.assertEqual(summary["accepted"], 0)
            self.assertTrue((out / f"1970_{CELL.source_id}.alarm.md").exists())

    def test_captionless_under_threshold_stays_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir = Path(tmp) / "pdfs"
            rows = []
            for index in range(20):
                doi = f"10.4000/c{index}"
                _pdf(pdf_dir, doi)
                rows.append({"doi": doi})

            def sample_fn(cell, year, limit, config):
                return rows

            def screen_fn(pdf, doi, out, config):
                if int(doi.rsplit("c", 1)[1]) < 3:
                    return _result(doi, structure=None, captionless=True, status="captionless")
                return _result(doi, structure=False, status="non_structure")

            summary = run_cell(
                CELL, 1970, pdf_dir, Path(tmp) / "out", Config(),
                sample_fn=sample_fn, screen_fn=screen_fn,
            )
            outcomes = [r["outcome"] for r in summary["records"]]
            self.assertIn("skipped_captionless", outcomes)
            self.assertFalse(summary["alarm"])


if __name__ == "__main__":
    unittest.main()
