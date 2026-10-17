#!/bin/sh
PORT=${PORT:-8080}

# Inicia Xvfb (display virtual para browser visível)
Xvfb :99 -screen 0 1366x768x24 -nolisten tcp &
sleep 1

# Gera nginx.conf com a porta correta (Railway define PORT dinamicamente)
sed "s/listen 8080/listen $PORT/" /app/nginx.conf > /tmp/nginx.conf

# Inicia gunicorn na porta interna 5000. 1 processo com 8 threads: com o
# worker síncrono uma requisição lenta (ou o Googlebot pedindo o sitemap)
# segurava todas as outras na fila. 1 processo só mantém um cache e um
# controle de robôs, e cabe no limite de memória do Railway.
gunicorn app:app --bind 0.0.0.0:5000 --workers 1 --worker-class gthread \
    --threads 8 --timeout 300 &

# Inicia nginx como reverse proxy
nginx -g 'daemon off;' -c /tmp/nginx.conf
