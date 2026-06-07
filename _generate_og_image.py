"""
Gera og-image.png (1200x630) para o TurboVenda.
Roda uma vez: python _generate_og_image.py
Requer: playwright (ja no requirements.txt)
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

HTML = """<!DOCTYPE html>
<html>
<head>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{width:1200px;height:630px;display:flex;align-items:center;justify-content:center;
     background:#060b18;font-family:system-ui,-apple-system,sans-serif;overflow:hidden;position:relative}
.glow{position:absolute;top:-200px;left:50%;transform:translateX(-50%);width:900px;height:900px;
      border-radius:50%;background:radial-gradient(circle,rgba(99,102,241,.2) 0%,transparent 60%);pointer-events:none}
.glow2{position:absolute;bottom:-300px;right:-100px;width:600px;height:600px;border-radius:50%;
       background:radial-gradient(circle,rgba(139,92,246,.15) 0%,transparent 60%);pointer-events:none}
.card{text-align:center;position:relative;z-index:1}
.logo{display:flex;align-items:center;justify-content:center;gap:16px;margin-bottom:32px}
.logo-mark{width:64px;height:64px;border-radius:18px;background:linear-gradient(135deg,#6366f1,#8b5cf6);
           display:flex;align-items:center;justify-content:center;font-size:32px}
.logo-text{font-size:42px;font-weight:900;color:#fff;letter-spacing:-1px}
.logo-text span{color:#6366f1}
h1{font-size:52px;font-weight:900;color:#f1f5f9;letter-spacing:-2px;margin-bottom:16px;line-height:1.1}
h1 .grad{background:linear-gradient(135deg,#6366f1,#8b5cf6,#ec4899);-webkit-background-clip:text;
         -webkit-text-fill-color:transparent;background-clip:text}
p{font-size:22px;color:#94a3b8;max-width:700px;margin:0 auto}
.badges{display:flex;gap:12px;justify-content:center;margin-top:28px}
.badge{background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.3);color:#34d399;
       padding:8px 20px;border-radius:100px;font-size:15px;font-weight:600}
</style>
</head>
<body>
<div class="glow"></div>
<div class="glow2"></div>
<div class="card">
  <div class="logo">
    <div class="logo-mark">⚡</div>
    <div class="logo-text">Turbo<span>Venda</span></div>
  </div>
  <h1>Prospecção B2B <span class="grad">Automática com IA</span></h1>
  <p>Encontre leads, envie mensagens personalizadas e feche mais negócios no piloto automático.</p>
  <div class="badges">
    <span class="badge">CRM + Kanban</span>
    <span class="badge">E-mail com IA</span>
    <span class="badge">WhatsApp</span>
  </div>
</div>
</body>
</html>"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 630})
        await page.set_content(HTML)
        out = Path(__file__).parent / "static" / "og-image.png"
        out.parent.mkdir(exist_ok=True)
        await page.screenshot(path=str(out), type="png")
        await browser.close()
        print(f"[OK] Gerado: {out} (1200x630)")


if __name__ == "__main__":
    asyncio.run(main())
