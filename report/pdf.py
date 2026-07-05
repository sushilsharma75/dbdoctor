"""HTML → paginated A4 PDF via headless Chromium (Playwright)."""

from __future__ import annotations

import glob
import os
from pathlib import Path

FOOTER_TEMPLATE = """
<div style="width:100%; font-size:8px; font-family:Georgia,serif; color:#777;
            display:flex; justify-content:space-between; padding:0 16mm;">
  <span>dbdoctor · confidential — prepared for the named client only</span>
  <span>page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
</div>
"""

HEADER_TEMPLATE = '<div style="font-size:1px;"></div>'  # header space kept empty


def _find_system_chromium() -> str | None:
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""), "/opt/pw-browsers"]
    for root in filter(None, roots):
        for pattern in ("chromium-*/chrome-linux/chrome", "chromium"):
            for candidate in sorted(glob.glob(str(Path(root) / pattern)), reverse=True):
                if os.access(candidate, os.X_OK) and not Path(candidate).is_dir():
                    return candidate
    return None


def html_to_pdf(html: str, out_path: str | Path) -> Path:
    """Render *html* to an A4 PDF with page numbers + confidentiality footer."""
    from playwright.sync_api import sync_playwright

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            # version-pinned browsers missing: fall back to any chromium found
            # under PLAYWRIGHT_BROWSERS_PATH (e.g. preinstalled CI images)
            executable = _find_system_chromium()
            if executable is None:
                raise
            browser = p.chromium.launch(executable_path=executable)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.emulate_media(media="print")
            page.pdf(
                path=str(out_path),
                format="A4",
                margin={"top": "14mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
                display_header_footer=True,
                header_template=HEADER_TEMPLATE,
                footer_template=FOOTER_TEMPLATE,
                print_background=True,
            )
        finally:
            browser.close()
    return out_path
