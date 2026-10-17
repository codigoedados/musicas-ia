# Mundo Novo da IA — catálogo de músicas (Flask + SQLite)

## Subir na nuvem
```bash
cp .env.example .env      # edite ADMIN_PASSWORD e SECRET_KEY
docker compose --env-file .env up -d --build
```
Acesse `http://SEU-IP:8000` · Admin: `/admin/login`

- Dados (SQLite, MP3 e capas) ficam no volume `dados` (`/data`). Faça backup desse volume.
- Atrás de Nginx/Caddy/Traefik com HTTPS: repasse `X-Forwarded-Proto/Host` e aumente `client_max_body_size` (Nginx) para o limite de upload (`MAX_UPLOAD_MB`).
- Teste local sem Docker: `pip install -r requirements.txt && ADMIN_PASSWORD=admin python -m flask --app app run`
