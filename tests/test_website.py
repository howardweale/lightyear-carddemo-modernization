import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "docs" / "index.html"


class WebsiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.page = WEBSITE.read_text(encoding="utf-8")

    def test_primary_logo_is_canonical_and_visible(self) -> None:
        canonical = ROOT / "brand" / "assets" / "lightyear-primary.svg"
        published = ROOT / "docs" / "assets" / "lightyear-primary.svg"
        self.assertEqual(canonical.read_bytes(), published.read_bytes())
        self.assertEqual(self.page.count('class="primary-logo'), 2)
        self.assertNotIn("data:image/svg+xml;base64,", self.page)
        self.assertEqual(self.page.count('aria-label="LIGHTYEAR primary logo"'), 2)
        self.assertEqual(self.page.count('viewBox="0 0 360 220"'), 2)
        self.assertEqual(self.page.count('>LIGHTYEAR</text>'), 2)

    def test_site_preserves_all_content_panes_and_milestone_library(self) -> None:
        for pane in ("how", "where", "proof", "trust", "docs", "engage"):
            self.assertIn(f'id="p-{pane}"', self.page)
        self.assertIn('href="milestones/"', self.page)
        self.assertIn('<div class="n">49</div>', self.page)
        self.assertIn('<div class="n">455</div>', self.page)
        self.assertIn("Forty-nine of them", self.page)
        self.assertIn("Anyone can rewrite it.", self.page)
        self.assertIn("We prove it behaves the same.", self.page)

    def test_docs_are_deep_linkable_searchable_and_scroll_aware(self) -> None:
        for anchor in (
            "d-start",
            "d-order",
            "d-verdicts",
            "d-norm",
            "d-evidence",
            "d-coverage",
            "d-cli",
            "d-integrate",
            "d-record",
        ):
            self.assertIn(f'id="{anchor}"', self.page)
            self.assertIn(f'href="#{anchor}"', self.page)
        self.assertIn('id="doc-search"', self.page)
        self.assertIn("IntersectionObserver", self.page)
        self.assertIn("start.startsWith('d-')", self.page)

    def test_inline_javascript_is_valid(self) -> None:
        scripts = re.findall(r"<script>(.*?)</script>", self.page, re.DOTALL)
        self.assertEqual(len(scripts), 1)
        result = subprocess.run(
            ["node", "--check", "-"],
            cwd=ROOT,
            input=scripts[0],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
