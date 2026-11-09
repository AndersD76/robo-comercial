# Rotas do app (141), geradas de `app.py`

| Caminho | Métodos | Função | Proteção | Limite |
|---|---|---|---|---|
| `/` | GET | `landing` | **pública** |  |
| `/.well-known/security.txt` | GET | `security_txt` | **pública** |  |
| `/admin` | GET,POST | `admin_login` | admin (checado no corpo), assinatura/HMAC | 5 per minute |
| `/admin/api/payments` | GET | `admin_api_payments` | admin |  |
| `/admin/api/stats` | GET | `admin_api_stats` | admin |  |
| `/admin/api/users` | GET | `admin_api_users_list` | admin |  |
| `/admin/api/users/<int:uid>/impersonate` | POST | `admin_api_impersonate` | admin |  |
| `/admin/api/users/<int:uid>/plano` | POST | `admin_api_change_plan` | admin |  |
| `/admin/api/users/<int:uid>/toggle` | POST | `admin_api_toggle_user` | admin |  |
| `/admin/dashboard` | GET | `admin_dashboard` | admin |  |
| `/admin/indexnow` | POST | `admin_indexnow` | admin (checado no corpo) |  |
| `/admin/logout` | GET | `admin_logout` | **pública** |  |
| `/admin/organico` | GET | `admin_organico` | admin |  |
| `/admin/receita` | GET | `admin_receita` | admin |  |
| `/admin/trafego` | GET | `admin_trafego` | admin |  |
| `/admin/users` | GET | `admin_users` | admin (checado no corpo) |  |
| `/agendar/<token>` | GET | `pagina_agendar` | **pública** |  |
| `/alternativas` | GET | `alternativas_hub` | **pública** |  |
| `/alternativas/<slug>` | GET | `alternativa_page` | **pública** |  |
| `/api/<bot>/add-lead` | POST | `api_add_lead` | login |  |
| `/api/<bot>/agenda` | GET | `api_agenda` | login |  |
| `/api/<bot>/agenda` | POST | `api_add_evento` | login |  |
| `/api/<bot>/agenda/<int:evento_id>` | DELETE | `api_delete_evento` | login |  |
| `/api/<bot>/agenda/<int:evento_id>` | PUT | `api_update_evento` | login |  |
| `/api/<bot>/clear-all` | POST | `api_clear_all` | login |  |
| `/api/<bot>/config` | GET | `api_get_config` | login |  |
| `/api/<bot>/config` | POST | `api_save_config` | login |  |
| `/api/<bot>/config/dominio` | POST | `api_dominio_criar` | login | 5 per minute |
| `/api/<bot>/config/dominio/verificar` | POST | `api_dominio_verificar` | login | 10 per minute |
| `/api/<bot>/config/email/auto` | POST | `api_email_auto` | login | 10 per minute |
| `/api/<bot>/config/email/conectar` | POST | `api_unipile_conectar` | login | 10 per minute |
| `/api/<bot>/config/email/desconectar` | POST | `api_email_desconectar` | login |  |
| `/api/<bot>/config/generate-email` | POST | `api_generate_email` | login |  |
| `/api/<bot>/config/generate-msg` | POST | `api_generate_msg` | login |  |
| `/api/<bot>/config/generate-terms` | POST | `api_generate_terms` | login |  |
| `/api/<bot>/config/ia-status` | GET | `api_ia_status` | login | 6 per minute |
| `/api/<bot>/config/smtp-diag` | GET | `api_smtp_diag` | login | 4 per minute |
| `/api/<bot>/config/test-email` | POST | `api_test_email` | login | 3 per minute |
| `/api/<bot>/console` | GET | `api_bot_console` | login |  |
| `/api/<bot>/email/campanha` | POST | `api_email_campanha` | login |  |
| `/api/<bot>/lead/<int:lead_id>` | DELETE | `api_delete_lead` | login |  |
| `/api/<bot>/lead/<int:lead_id>` | PUT | `api_update_lead` | login |  |
| `/api/<bot>/lead/<int:lead_id>/atividade` | POST | `api_add_atividade` | login |  |
| `/api/<bot>/lead/<int:lead_id>/atividades` | GET | `api_lead_atividades` | login |  |
| `/api/<bot>/lead/<int:lead_id>/enriquecer` | POST | `api_enriquecer_lead` | login |  |
| `/api/<bot>/lead/<int:lead_id>/link-agenda` | GET | `api_lead_link_agenda` | login |  |
| `/api/<bot>/lead/<int:lead_id>/redes-decisor` | POST | `api_redes_decisor` | login |  |
| `/api/<bot>/lead/<int:lead_id>/requalificar` | POST | `api_requalificar_lead` | login |  |
| `/api/<bot>/lead/<int:lead_id>/tarefa` | POST | `api_add_tarefa` | login |  |
| `/api/<bot>/lead/<int:lead_id>/tarefas` | GET | `api_lead_tarefas` | login |  |
| `/api/<bot>/leads` | GET | `api_leads` | login |  |
| `/api/<bot>/leads/bulk` | POST | `api_bulk_action` | login |  |
| `/api/<bot>/leads/export` | GET | `api_export_leads` | login |  |
| `/api/<bot>/logs` | GET | `api_logs` | login |  |
| `/api/<bot>/qr` | GET | `api_bot_qr` | login |  |
| `/api/<bot>/relatorios` | GET | `api_relatorios` | login |  |
| `/api/<bot>/send-emails` | POST | `api_send_emails` | login |  |
| `/api/<bot>/sequencia/<int:seq_id>` | DELETE | `api_delete_sequencia` | login |  |
| `/api/<bot>/sequencia/<int:seq_id>` | PUT | `api_update_sequencia` | login |  |
| `/api/<bot>/sequencia/<int:seq_id>/enroll` | POST | `api_enroll_leads` | login |  |
| `/api/<bot>/sequencia/<int:seq_id>/leads` | GET | `api_sequencia_leads` | login |  |
| `/api/<bot>/sequencias` | GET | `api_list_sequencias` | login |  |
| `/api/<bot>/sequencias` | POST | `api_create_sequencia` | login |  |
| `/api/<bot>/sequencias/processar` | POST | `api_processar_sequencias` | login |  |
| `/api/<bot>/start` | POST | `api_bot_start` | login |  |
| `/api/<bot>/stats` | GET | `api_stats` | login |  |
| `/api/<bot>/status` | GET | `api_bot_status` | login |  |
| `/api/<bot>/stop` | POST | `api_bot_stop` | login |  |
| `/api/<bot>/tarefa/<int:tarefa_id>` | DELETE | `api_delete_tarefa` | login |  |
| `/api/<bot>/tarefa/<int:tarefa_id>` | PUT | `api_update_tarefa` | login |  |
| `/api/<bot>/tarefas/pendentes` | GET | `api_tarefas_pendentes` | login |  |
| `/api/<bot>/tokens` | GET | `api_list_tokens` | login |  |
| `/api/<bot>/tokens` | POST | `api_create_token` | login |  |
| `/api/<bot>/tokens/<int:token_id>` | DELETE | `api_revoke_token` | login |  |
| `/api/agendar/<token>/confirmar` | POST | `api_agenda_confirmar` | **pública** |  |
| `/api/agendar/<token>/slots` | GET | `api_agenda_slots` | **pública** |  |
| `/api/checkout` | POST | `api_checkout` | login |  |
| `/api/cron/trial-emails` | GET | `cron_trial_emails` | assinatura/HMAC | 6 per hour |
| `/api/meu-plano` | GET | `api_meu_plano` | login |  |
| `/api/meus-dados/excluir` | POST | `api_excluir_dados` | login | 3 per hour |
| `/api/meus-dados/exportar` | GET | `api_exportar_dados` | login |  |
| `/api/pagamento/cartao` | POST | `api_pagamento_cartao` | login | 5 per minute |
| `/api/pagamento/pix` | POST | `api_pagamento_pix` | login | 5 per minute |
| `/api/pagamento/status/<int:payment_id>` | GET | `api_pagamento_status` | login |  |
| `/api/pipeline` | GET | `api_pipeline` | login |  |
| `/api/planos` | GET | `api_planos` | **pública** |  |
| `/api/t/cta` | POST | `api_trafego_cta` | **pública** | 60 per minute |
| `/api/t/evento` | POST | `api_trafego_evento` | sessão (checada no corpo) | 30 per minute |
| `/api/t/pv` | POST | `api_trafego_pv` | **pública** | 60 per minute |
| `/api/v1/leads` | GET | `public_list_leads` | token |  |
| `/api/v1/leads` | POST | `public_create_lead` | token |  |
| `/api/v1/leads/<int:lead_id>` | PUT | `public_update_lead` | token |  |
| `/assinar` | GET | `assinar` | sessão (checada no corpo) |  |
| `/blog` | GET | `blog_index` | **pública** |  |
| `/blog/<slug>` | GET | `blog_post` | **pública** |  |
| `/cadastro` | GET,POST | `cadastro` | sessão (checada no corpo) | 5 per minute |
| `/configurar` | GET | `config_page` | login |  |
| `/dashboard` | GET | `dashboard` | login, admin (checado no corpo) |  |
| `/descadastrar/<token>` | GET | `descadastrar` | assinatura/HMAC |  |
| `/empresas` | GET | `pseo_hub` | **pública** |  |
| `/empresas/<cnae_slug>` | GET | `pseo_cnae` | **pública** |  |
| `/empresas/<cnae_slug>/<mun_slug>` | GET | `pseo_cidade` | **pública** |  |
| `/empresas/<cnae_slug>/estado/<uf>` | GET | `pseo_estado` | **pública** |  |
| `/empresas/busca` | GET | `pseo_busca` | **pública** |  |
| `/empresas/cidade/<mun_slug>` | GET | `pseo_cidade_hub` | **pública** |  |
| `/empresas/sobre-os-dados` | GET | `pseo_sobre_dados` | **pública** |  |
| `/favicon.ico` | GET | `favicon` | **pública** |  |
| `/ferramentas` | GET | `ferramentas_hub` | **pública** |  |
| `/ferramentas/calculadora-de-leads` | GET | `ferramenta_calculadora` | **pública** |  |
| `/ferramentas/gerador-de-mensagem-de-prospeccao` | GET,POST | `ferramenta_gerador` | **pública** | 8 per hour;25 per day |
| `/ferramentas/lista-de-empresas` | GET | `ferramenta_lista` | **pública** | 40 per hour |
| `/health` | GET | `health` | **pública** |  |
| `/imprensa` | GET | `imprensa` | **pública** |  |
| `/llms-full.txt` | GET | `llms_full_txt` | **pública** |  |
| `/llms.txt` | GET | `llms_txt` | **pública** |  |
| `/login` | GET,POST | `login` | sessão (checada no corpo) | 10 per minute |
| `/logout` | GET | `logout` | **pública** |  |
| `/manifest.json` | GET | `manifest_json` | **pública** |  |
| `/oauth/<provider>/callback` | GET | `oauth_callback` | login, assinatura/HMAC |  |
| `/oauth/<provider>/start` | GET | `oauth_start` | login |  |
| `/pagamento/<resultado>` | GET | `pagamento_resultado` | login |  |
| `/para/<slug>` | GET | `segmento_page` | **pública** |  |
| `/precos` | GET | `precos` | **pública** |  |
| `/privacidade` | GET | `privacidade` | **pública** |  |
| `/robots.txt` | GET | `robots_txt` | **pública** |  |
| `/sitemap-empresas-<int:n>.xml` | GET | `sitemap_empresas_xml` | **pública** |  |
| `/sitemap-pages.xml` | GET | `sitemap_pages_xml` | **pública** |  |
| `/sitemap.xml` | GET | `sitemap_xml` | **pública** |  |
| `/t/<token>/click` | GET | `email_track_click` | **pública** |  |
| `/t/<token>/open.png` | GET | `email_track_open` | **pública** |  |
| `/t/test` | GET | `email_track_test` | login |  |
| `/termos` | GET | `termos` | **pública** |  |
| `/trial-expirado` | GET | `trial_expirado` | login |  |
| `/videos` | GET | `videos_hub` | **pública** |  |
| `/videos/<slug>` | GET | `video_pagina` | **pública** |  |
| `/webhook/email` | POST | `webhook_email` | assinatura/HMAC |  |
| `/webhook/mercadopago` | POST | `webhook_mercadopago` | assinatura/HMAC | 30 per minute |
| `/webhook/unipile` | POST | `webhook_unipile` | **pública** | 60 per minute |
| `?` | GET | `indexnow_key` | **pública** |  |
| `?` | GET | `relatorio_dados_embed` | **pública** |  |
| `?` | GET | `relatorio_dados_pagina` | **pública** |  |
