# -*- coding: utf-8 -*-
"""
Robo Comercial — ponto de entrada unificado
Define BOT_NAME=prima ou BOT_NAME=pili no Railway
"""
import os
import sys

BOT_NAME = os.environ.get('BOT_NAME', 'pili').lower()

# Adiciona a pasta do bot ao path para que os imports internos funcionem
if BOT_NAME == 'prima':
    bot_dir = os.path.join(os.path.dirname(__file__), 'robo_prima')
elif BOT_NAME == 'pili':
    bot_dir = os.path.join(os.path.dirname(__file__), 'robo_pili')
else:
    raise ValueError(f"BOT_NAME inválido: '{BOT_NAME}'. Use 'prima' ou 'pili'.")

sys.path.insert(0, bot_dir)
os.chdir(bot_dir)  # garante que templates/ e static/ sejam encontrados

from app import app  # importa o Flask app da subpasta

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
