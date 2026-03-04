# Imagem oficial Playwright — todas as libs de sistema pré-instaladas
FROM mcr.microsoft.com/playwright/python:v1.46.0-jammy

WORKDIR /app

# Evita prompts interativos do apt (ex: tzdata)
ENV DEBIAN_FRONTEND=noninteractive

# Xvfb (display virtual) + x11vnc + noVNC + nginx (reverse proxy)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify nginx && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala browser
ENV PLAYWRIGHT_BROWSERS_PATH=/app/ms-playwright
RUN playwright install chromium

# Copia código da aplicação
COPY . .

# Modo headless antigo
ENV PLAYWRIGHT_CHROMIUM_USE_HEADLESS_NEW=0

# Display virtual para Xvfb
ENV DISPLAY=:99

RUN chmod +x /app/start.sh

EXPOSE 8080

CMD ["/app/start.sh"]
