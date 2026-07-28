import asyncio
import json
import os
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

PACKAGE_BASE = os.environ["PACKAGE_BASE"].rstrip("/")
PAGE_COUNT = int(os.environ.get("PAGE_COUNT", "32"))
OUT = Path("output")
PAGES = OUT / "pages"
PAGES.mkdir(parents=True, exist_ok=True)


def page_url(index: int) -> str:
    name = "publication.html" if index == 0 else f"publication-{index}.html"
    return f"{PACKAGE_BASE}/{name}"


async def main() -> None:
    records = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=2)
        page = await context.new_page()

        for i in range(PAGE_COUNT):
            url = page_url(i)
            response = await page.goto(url, wait_until="networkidle", timeout=120_000)
            status = response.status if response else None
            await page.wait_for_timeout(1500)

            body = page.locator("body")
            body_box = await body.bounding_box()
            if not body_box:
                raise RuntimeError(f"Page {i + 1}: missing body box")

            text = (await body.inner_text()).strip()
            txt_path = PAGES / f"page-{i + 1:02d}.txt"
            txt_path.write_text(text, encoding="utf-8")

            png_path = PAGES / f"page-{i + 1:02d}.png"
            await page.screenshot(path=str(png_path), full_page=True)

            records.append({
                "page": i + 1,
                "url": url,
                "status": status,
                "title": await page.title(),
                "text_chars": len(text),
                "body_box": body_box,
                "screenshot_bytes": png_path.stat().st_size,
            })

        await browser.close()

    images = []
    for i in range(PAGE_COUNT):
        path = PAGES / f"page-{i + 1:02d}.png"
        img = Image.open(path).convert("RGB")
        images.append(img)

    pdf_path = OUT / "DCRO2026-complete.pdf"
    images[0].save(pdf_path, save_all=True, append_images=images[1:], resolution=144.0)
    for img in images:
        img.close()

    combined = []
    for i in range(PAGE_COUNT):
        text = (PAGES / f"page-{i + 1:02d}.txt").read_text(encoding="utf-8")
        combined.append(f"\n\n===== PAGE {i + 1} =====\n\n{text}")
    (OUT / "all-pages-text.txt").write_text("".join(combined).lstrip(), encoding="utf-8")

    verification = {
        "expected_pages": PAGE_COUNT,
        "captured_pages": len(records),
        "all_http_200": all(r["status"] == 200 for r in records),
        "all_nonempty_screenshots": all(r["screenshot_bytes"] > 10_000 for r in records),
        "pdf_bytes": pdf_path.stat().st_size,
        "records": records,
    }
    (OUT / "verification.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")

    if verification["captured_pages"] != PAGE_COUNT:
        raise RuntimeError("Did not capture expected page count")
    if not verification["all_http_200"]:
        raise RuntimeError("One or more page assets returned non-200")
    if not verification["all_nonempty_screenshots"]:
        raise RuntimeError("One or more screenshots appears empty")


if __name__ == "__main__":
    asyncio.run(main())
