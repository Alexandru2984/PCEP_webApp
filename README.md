# PCEP WebApp

Quiz web application for preparing the **PCEP** (Python Certified Entry-Level Programmer) certification. Each question has multiple-choice answers with immediate feedback and a detailed explanation for wrong answers.

## Stack
- **Backend**: Django + Django REST Framework (PostgreSQL, Gunicorn)
- **Frontend**: React + Vite + Tailwind CSS (Axios for API calls)
- **Deploy**: Docker Compose (db + backend) + system Nginx reverse proxy + Let's Encrypt

## Production
`https://pcep.micutu.com`

## Architecture
```
Internet → system nginx (80/443) ──┬── /admin/, /api/ → 127.0.0.1:8001 (Docker: gunicorn)
                                   └── /               → /var/www/pcep/frontend (React build)
```

## Layout
```
backend/        Django project + DRF app (created in Step 2)
frontend/       React + Vite app (created in Step 4)
nginx/          Template config for system nginx (sites-available)
docker-compose.yml
.env.example    Copy to .env and fill in real values
```

## Development
1. `cp .env.example .env` and set real secrets.
2. `docker compose up --build` to bring up db + backend.
3. `docker compose --profile build run --rm frontend-builder` to build the React app.

## Deploy
See deployment notes in Step 5 / Step 6 of the setup pipeline.
