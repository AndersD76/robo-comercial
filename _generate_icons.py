"""Gera icon-192.png e icon-512.png para PWA manifest."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

TEMPLATE = """<!DOCTYPE html>
<html><head><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:{size}px;height:{size}px;display:flex;align-items:center;justify-content:center;
     background:linear-gradient(135deg,#6366f1,#8b5cf6);overflow:hidden}}
.icon{{font-size:{font}px;text-align:center}}
</style></head>
<body><div class="icon">⚡</div></body></html>"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for size, font in [(192, 96), (512, 256)]:
            page = await browser.new_page(viewport={"width": size, "height": size})
            await page.set_content(TEMPLATE.format(size=size, font=font))
            out = Path(__file__).parent / "static" / f"icon-{size}.png"
            await page.screenshot(path=str(out), type="png")
            print(f"[OK] {out}")
            await page.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
