"""docs/SCREENSHOTS.md: every image it links must exist, and the README must link it."""

import os
import re

from conftest import ROOT

DOCS = os.path.join(ROOT, "docs")
PAGE = os.path.join(DOCS, "SCREENSHOTS.md")


def test_screenshot_links_resolve_and_readme_links_the_page():
    """GEAR-17: given docs/SCREENSHOTS.md, when its image links and the README are
    read, then every image link resolves to a file under docs/, and the README
    links docs/SCREENSHOTS.md."""
    text = open(PAGE, encoding="utf-8").read()
    links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    assert links
    missing = [link for link in links if not os.path.isfile(os.path.join(DOCS, link))]
    assert not missing, missing
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    assert "docs/SCREENSHOTS.md" in readme
