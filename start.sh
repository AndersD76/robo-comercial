#!/bin/sh
# Inicia Xvfb (display virtual para browser visível)
Xvfb :99 -screen 0 1366x768x24 -nolisten tcp &
sleep 1

# Inicia gunicorn na porta interna 5000
gunicorn app:app --bind 0.0.0.0:5000 --workers 1 --timeout 300 &

# Inicia nginx como reverse proxy na porta 8080 (exposta pelo Railway)
nginx -g 'daemon off;' -c /app/nginx.conf
