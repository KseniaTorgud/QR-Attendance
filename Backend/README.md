# Student Events QR Backend

Backend API for student registration to events by QR token with selfie-based attendance confirmation.

## Stack

- Python 3.12
- Django 5.2
- Django REST Framework 3.16
- drf-spectacular (OpenAPI/Swagger/ReDoc)
- Simple JWT
- SQLite (MVP)
- Pillow
- pytest + pytest-django

## Features

- Custom user model with roles: `admin`, `teacher`, `student`
- Student self-registration
- JWT auth (`access` + `refresh`)
- Events CRUD with owner-based permissions for teachers
- QR token generation and regeneration
- Registration to event only via `register-by-qr` endpoint
- Selfie upload (`multipart/form-data`) with size/type validation
- Teacher/Admin attendance confirmation (`confirmed` / `rejected`)
- Rating stats (confirmed visits only)
- CSV export for rating and event registrations
- OpenAPI docs and Swagger/ReDoc UI

## Project structure

```text
backend/
  manage.py
  config/
  apps/
    users/
    events/
    registrations/
    common/
  media/
```

## Setup

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Seed demo users

```bash
python manage.py seed_data
```

Created/updated users:

- `admin / admin12345`
- `teacher / teacher12345`
- `student / student12345`

## API docs

- OpenAPI schema: `GET /api/schema/`
- Swagger UI: `GET /api/docs/`
- ReDoc: `GET /api/redoc/`

## Main API prefix

- `/api/v1/`

## Key endpoints

### Auth

- `POST /api/v1/auth/register/`
- `POST /api/v1/auth/token/`
- `POST /api/v1/auth/token/refresh/`
- `GET /api/v1/auth/me/`

### Users

- `GET /api/v1/users/`
- `GET /api/v1/users/{id}/`
- `PATCH /api/v1/users/{id}/`
- `POST /api/v1/users/teachers/`

### Events

- `GET /api/v1/events/`
- `POST /api/v1/events/`
- `GET /api/v1/events/{id}/`
- `PATCH /api/v1/events/{id}/`
- `DELETE /api/v1/events/{id}/`
- `POST /api/v1/events/{id}/regenerate-qr/`
- `POST /api/v1/events/{id}/register-by-qr/`

### Registrations

- `GET /api/v1/registrations/`
- `GET /api/v1/registrations/{id}/`
- `PATCH /api/v1/registrations/{id}/mark-attendance/`
- `PATCH /api/v1/registrations/{id}/upload-selfie/`
- `PATCH /api/v1/registrations/{id}/confirm/`

### Stats and export

- `GET /api/v1/stats/rating/`
- `GET /api/v1/stats/events/{id}/`
- `GET /api/v1/exports/rating.csv`
- `GET /api/v1/exports/event/{id}/registrations.csv`

## Selfie upload example

```bash
curl -X PATCH \
  "http://127.0.0.1:8000/api/v1/registrations/1/upload-selfie/" \
  -H "Authorization: Bearer <access_token>" \
  -F "selfie=@/path/to/selfie.jpg"
```

## Tests

```bash
pytest
```

or

```bash
python manage.py test
```
