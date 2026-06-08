# cinema-event-system

Production-ready FastAPI skeleton for a cinema event platform.

## What is included

- FastAPI application factory in `app/main.py`
- Environment-based configuration in `app/config.py`
- Shared dependencies in `app/dependencies.py`
- MongoDB wiring with Motor and Beanie in `app/db/mongodb.py`
- Structured JSON logging in `app/core/logging.py`
- Global error-handling middleware in `app/middleware/error_handler.py`
- Health-check endpoint at `GET /health`

## Prerequisites

- Python 3.11 or newer
- MongoDB running locally or remotely

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:
   - `pip install -r requirements-dev.txt`
3. Copy the environment template:
   - `.env.example` → `.env`
4. Update `.env` with your MongoDB and JWT values.

## Run the app

```bash
uvicorn app.main:app --reload
```

## Health check

```bash
GET /health
```

Example response:

```json
{
  "status": "ok",
  "db": "connected"
}
```

## Tooling

- Black
- isort
- mypy (strict)
- pytest
