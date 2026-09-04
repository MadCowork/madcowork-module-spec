from __future__ import annotations

import json
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

    def append_app(self, source: str) -> None:
        path = self.module / "ui" / "app.js"
        path.write_text(path.read_text(encoding="utf-8") + source, encoding="utf-8")

    def mutate_manifest(self, mutate) -> None:
        path = self.module / "plugin.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        mutate(manifest)
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def test_reference_template_has_no_contract_findings(self) -> None:
        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0 FAIL / 0 WARN", result.stdout)

    def test_ui_entry_point_must_match_current_host_discovery_suffix(self) -> None:
        self.mutate_manifest(
            lambda manifest: manifest["entryPoints"]["ui"].update(
                {"open": "example_panel_state"}
            )
        )
        result = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("discovers module screens only from a tool ending in `_open_ui`", result.stdout)

    def test_ui_requires_a_current_host_discovery_tool(self) -> None:
        self.mutate_manifest(lambda manifest: manifest.pop("entryPoints"))
        server = self.module / "server.py"
        source = server.read_text(encoding="utf-8")
        self.assertIn("example_open_ui", source)
        server.write_text(source.replace("example_open_ui", "example_show_screen"), encoding="utf-8")
        skill = self.module / "skills" / "example-notes.md"
        skill_source = skill.read_text(encoding="utf-8")
        self.assertIn("example_open_ui", skill_source)
        skill.write_text(
            skill_source.replace("example_open_ui", "example_show_screen"),
            encoding="utf-8",
        )
        result = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("no model-visible tool ends in `_open_ui`", result.stdout)

    def test_missing_ui_entry_point_metadata_warns_without_false_host_claim(self) -> None:
        self.mutate_manifest(lambda manifest: manifest["entryPoints"].pop("ui"))
        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("current host can still discover an `_open_ui` tool", result.stdout)
        self.assertNotIn("host cannot offer a button", result.stdout)

    def test_dispatch_dict_tool_style_is_used_for_entry_point_checks(self) -> None:
        server = self.module / "server.py"
        source = server.read_text(encoding="utf-8")
        self.assertIn('"name":', source)
        source = source.replace('"name":', "'name':")
        server.write_text(source, encoding="utf-8")
        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("which is not in your tools", result.stdout)
        self.assertNotIn("no model-visible tool ends in `_open_ui`", result.stdout)
        self.assertIn("cannot prove that those handlers are model-visible", result.stdout)

    def test_declared_panel_without_a_consumer_warns(self) -> None:
        self.mutate_app("call('panel_pull'", "call('panel_missing'")
        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no UI file calls `panel_pull`", result.stdout)

    def test_raw_model_card_interpolation_fails(self) -> None:
        self.append_app(
            "\nconst unsafeCard = `${card.title}`\n"
            "document.getElementById('agentCards').innerHTML = unsafeCard\n"
        )
        result = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("card fields reach the markup unescaped", result.stdout)

    def test_string_wrapper_does_not_count_as_html_escaping(self) -> None:
        self.append_app(
            "\nconst unsafeCard = `${String(card.title)}`\n"
            "document.getElementById('agentCards').innerHTML = unsafeCard\n"
        )
        result = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("card fields reach the markup unescaped", result.stdout)

    def test_renamed_card_and_multiline_interpolation_fail(self) -> None:
        self.append_app(
            "\nconst unsafeCards = cards.map(item => `<p>${\n  item.title\n}</p>`).join('')\n"
            "document.getElementById('agentCards').innerHTML = unsafeCards\n"
        )
        result = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("card fields reach the markup unescaped", result.stdout)

    def test_known_escape_wrapper_remains_accepted(self) -> None:
        self.append_app(
            "\nconst safeCards = cards.map(item => `<p>${esc(item.title)}</p>`).join('')\n"
            "document.getElementById('agentCards').innerHTML = safeCards\n"
        )
        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("card fields reach the markup unescaped", result.stdout)

    def test_escaped_line_map_remains_accepted(self) -> None:
        self.append_app(
            "\nconst safeCards = cards.map(item => `<div>${(item.lines || []).map(line => `<p>${esc(line)}</p>`).join('')}</div>`).join('')\n"
            "document.getElementById('agentCards').innerHTML = safeCards\n"
        )
        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("card fields reach the markup unescaped", result.stdout)

    def test_string_wrapped_line_map_fails(self) -> None:
        self.append_app(
            "\nconst unsafeCards = cards.map(item => `<div>${(item.lines || []).map(line => `<p>${String(line)}</p>`).join('')}</div>`).join('')\n"
            "document.getElementById('agentCards').innerHTML = unsafeCards\n"
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
