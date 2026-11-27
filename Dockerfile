# Imagem oficial Playwright — todas as libs de sistema pré-instaladas.
# Noble = Ubuntu 24.04 com Python 3.12 (a jammy trazia o 3.10, que já não
# recebe as correções de segurança de soupsieve e Pillow).
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

WORKDIR /app

# Evita prompts interativos do apt (ex: tzdata)
ENV DEBIAN_FRONTEND=noninteractive

# Xvfb (display virtual) + x11vnc + noVNC + nginx (reverse proxy)
# tini como PID 1: recolhe os processos dos robôs que morrem (o sh não recolhe)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify nginx tini python3-venv && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Dependências Python num ambiente virtual: no Ubuntu 24.04 o Python do
# sistema é gerenciado pelo apt (PEP 668) e o pip não pode mexer nele
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
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

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/start.sh"]
