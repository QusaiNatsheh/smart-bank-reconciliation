"""Take README screenshots and a demo GIF from the running Docker demo (`make demo` first).

Needs Playwright with a Chrome/Chromium install:  pip install playwright pillow
Usage: python scripts/screenshots.py [--url http://localhost:8069] [--line-id 320] [--out docs/screenshots]
"""

import argparse
import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

VIEWPORT = {"width": 1440, "height": 900}


def login(page, url: str, db: str) -> None:
    page.goto(f"{url}/web/login?db={db}")
    page.fill("input[name=login]", "admin")
    page.fill("input[name=password]", "admin")
    page.click("button[type=submit]")
    page.wait_for_url("**/odoo**")
    page.wait_for_selector(".o_main_navbar", timeout=30000)


def settle(page) -> None:
    """Odoo keeps a live connection open (bus), so wait for the rendered view instead of network idle."""
    page.wait_for_selector(".o_action_manager .o_view_controller", timeout=30000)
    page.wait_for_timeout(1500)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8069")
    parser.add_argument("--db", default="demo")
    parser.add_argument("--line-id", type=int, default=320, help="bank statement line used for the walkthrough")
    parser.add_argument("--out", type=Path, default=Path("docs/screenshots"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    frames = []

    def shot(page, name: str, frame: bool = True) -> None:
        png = page.screenshot()
        (args.out / f"{name}.png").write_bytes(png)
        if frame:
            frames.append(Image.open(io.BytesIO(png)).convert("RGB"))

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        # Hide Odoo's onboarding tour pointers: they are not part of the module.
        page.add_init_script(
            "document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');"
            " s.textContent = '.o_tour_pointer { display: none !important; }'; document.head.appendChild(s); });"
        )
        login(page, args.url, args.db)

        page.goto(f"{args.url}/odoo/action-smart_reconcile.action_bank_statement_line_smart")
        settle(page)
        shot(page, "01_bank_lines")

        # Narrow the list to the walkthrough line, then open its suggestions
        ref = page.evaluate(
            """async (id) => {
                const r = await fetch('/web/dataset/call_kw', {method: 'POST', headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: {model: 'account.bank.statement.line',
                  method: 'read', args: [[id], ['payment_ref']], kwargs: {}}})});
                return (await r.json()).result[0].payment_ref;
            }""",
            args.line_id,
        )
        search = page.locator(".o_searchview_input")
        search.fill(ref.split()[1] if len(ref.split()) > 1 else ref)
        search.press("Enter")
        settle(page)
        row = page.locator(".o_data_row").first
        row.hover()
        shot(page, "02_line_selected")
        row.locator("button[name=action_smart_suggest]").click()
        page.wait_for_selector(".modal .o_list_renderer")
        settle(page)
        shot(page, "03_suggestions")

        page.locator(".modal .o_data_row").first.locator("button[name=action_accept]").click()
        page.wait_for_selector(".modal", state="detached")
        settle(page)
        page.locator(".o_searchview_facet .o_facet_remove").last.click()  # drop "Not Reconciled" to see the result
        settle(page)
        shot(page, "04_after_accept")

        page.goto(f"{args.url}/odoo/action-smart_reconcile.action_smart_reconcile_feedback")
        settle(page)
        shot(page, "05_feedback_log", frame=False)
        browser.close()

    gif = args.out / "demo.gif"
    small = [f.resize((960, 600), Image.Resampling.LANCZOS) for f in frames]
    small[0].save(gif, save_all=True, append_images=small[1:], duration=[2200, 1500, 4000, 3000], loop=0, optimize=True)
    print(f"{len(frames)} frames -> {gif}; screenshots in {args.out}")


if __name__ == "__main__":
    main()
