# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Die JOSHI-Oberfläche zeigt den gestuften Lauf getrennt vom globalen Ablauf."""
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class JoshiStageUiTests(unittest.TestCase):
    def test_stream_events_are_handled_as_stages(self):
        javascript = (ROOT / "static" / "joshi.js").read_text(encoding="utf-8")
        self.assertIn('} else if (art === "stufen")', javascript)
        self.assertIn('} else if (art === "stufe")', javascript)
        self.assertIn("uebernehmeStufenplan(live, ereignis)", javascript)
        self.assertIn("uebernehmeStufe(live, ereignis)", javascript)
        self.assertIn("stufenZusammenfassung(live)", javascript)
        self.assertIn("Usage je Stage", javascript)
        self.assertIn("output_tokens_estimated", javascript)

    def test_stage_states_have_distinct_visual_mappings(self):
        javascript = (ROOT / "static" / "joshi.js").read_text(encoding="utf-8")
        styles = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
        for zustand in ("planned", "generating", "connecting", "validating", "passed", "failed", "not_proven", "repairing"):
            self.assertIn(f"{zustand}:", javascript)
        self.assertIn(".joshi-stage-summary", styles)
        self.assertIn(".joshi-progress-text", styles)
        self.assertIn(".joshi-steps li.is-unbewiesen", styles)

    @unittest.skipUnless(shutil.which("node"), "Node für die JavaScript-Verhaltenstests erforderlich")
    def test_stage_progress_handles_completed_and_active_stages_together(self):
        result = subprocess.run(["node", str(ROOT / "tests" / "joshi_stage_progress.cjs")],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
