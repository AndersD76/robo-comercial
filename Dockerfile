# Imagem oficial Playwright — todas as libs de sistema (libglib, libnss, etc.) pré-instaladas
FROM mcr.microsoft.com/playwright/python:v1.46.0-jammy

WORKDIR /app

# noVNC: display virtual + VNC + websocket proxy
RUN apt-get update && \
    apt-get install -y --no-install-recommends xvfb x11vnc novnc websockify && \
    rm -rf /var/lib/apt/lists/*

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

# Display virtual (Xvfb) fica sempre rodando
ENV DISPLAY=:99

EXPOSE 8080 6080

CMD ["sh", "-c", "Xvfb :99 -screen 0 1366x768x24 -ac & gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 300"]
