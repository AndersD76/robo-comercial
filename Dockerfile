# Imagem oficial Playwright — todas as libs de sistema (libglib, libnss, etc.) pré-instaladas
FROM mcr.microsoft.com/playwright/python:v1.46.0-jammy

WORKDIR /app

# Instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala browser em /app/ms-playwright (fica na imagem final)
ENV PLAYWRIGHT_BROWSERS_PATH=/app/ms-playwright
RUN playwright install chromium

# Copia código da aplicação
COPY . .

# Modo headless antigo → compatível com launch_persistent_context (WhatsApp + LinkedIn)
ENV PLAYWRIGHT_CHROMIUM_USE_HEADLESS_NEW=0

EXPOSE 8080

CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 300"]
