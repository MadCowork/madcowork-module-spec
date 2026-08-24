from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_contract.py"
TEMPLATE = ROOT / "template"


class PanelConsumerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="module-contract-test-")
        self.module = Path(self.temp.name) / "module"
        shutil.copytree(TEMPLATE, self.module)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_checker(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECKER), str(self.module)],
            text=True,
            capture_output=True,
            check=False,
        )

    def mutate_app(self, old: str, new: str) -> None:
        path = self.module / "ui" / "app.js"
        source = path.read_text(encoding="utf-8")
        self.assertIn(old, source, f"mutation precondition missing: {old}")
        path.write_text(source.replace(old, new, 1), encoding="utf-8")

    def test_reference_template_has_no_contract_findings(self) -> None:
        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0 FAIL / 0 WARN", result.stdout)

    def test_declared_panel_without_a_consumer_warns(self) -> None:
        self.mutate_app("call('panel_pull'", "call('panel_missing'")
        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no UI file calls `panel_pull`", result.stdout)

    def test_raw_model_card_interpolation_fails(self) -> None:
        path = self.module / "ui" / "app.js"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\nconst unsafeCard = `${card.title}`\n"
            + "document.getElementById('agentCards').innerHTML = unsafeCard\n",
            encoding="utf-8",
        )
        result = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("card fields reach the markup unescaped", result.stdout)

    def test_unlabelled_model_cards_warn(self) -> None:
        self.mutate_app(
            "src.className = 'ac-src'; src.textContent = t('agentCard')",
            "src.className = 'source'; src.textContent = 'source'",
        )
        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("nothing marks where they came from", result.stdout)


class TemplatePanelI18nTests(unittest.TestCase):
    def test_panel_source_and_dismiss_labels_cover_all_nine_languages(self) -> None:
        source = (TEMPLATE / "ui" / "i18n.js").read_text(encoding="utf-8")
        for language in ("en", "zh", "ja", "ko", "fr", "es", "pt", "de", "it"):
            if language == "en":
                block = source.split("const en = {", 1)[1].split("}\nconst dict", 1)[0]
            else:
                marker = f"  {language}:{{"
                self.assertIn(marker, source)
                block = source.split(marker, 1)[1].split("},\n", 1)[0]
            self.assertIn("agentCard:", block, f"{language} missing agentCard")
            self.assertIn("agentDismiss:", block, f"{language} missing agentDismiss")


if __name__ == "__main__":
    unittest.main()
