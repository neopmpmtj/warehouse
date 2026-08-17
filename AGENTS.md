# CentCompras — Agent instructions

Django 6.1 + PostgreSQL MVP for a **central warehouse** with **satellite branches**. Branch staff browse a product catalogue from a phone browser; orders are the next business phase.

## Current state (what exists)

### Apps

- **`accounts`** — custom `User` (email login), login/logout views
- **`branches`** — `Branch`, `BranchMembership`, `permissions.py`, `ActiveBranchMiddleware`, branch picker
- **`products`** — catalogue model, service layer, API, CLI, offline-capable web UI

### Auth and tenancy

- `AUTH_USER_MODEL = "accounts.User"`
- Roles per branch via `BranchMembership`: admin, manager, user
- Active branch in session (`active_branch_id`); auto-set for single-branch users
- Catalogue and API require login; API returns 401 when unauthenticated
- Google OAuth planned for production — not implemented in dev

### Catalogue

- **Product fields:** `description`, `stock` (decimal), `price` (USD)
- **Product creation:** CLI only — `python manage.py add_product "..." stock price`
- **API:** `GET /api/products/` (authenticated)
- **Offline:** Service Worker + IndexedDB (read-only catalogue cache)

### Logging

- `logging_utils` package — `get_logger("centcompras.<app>")`
- Rotating log files under `logs/` (gitignored)
- Initial logging in `products`, `branches` middleware/views

PostgreSQL is the source of truth. IndexedDB is not an independent warehouse database.

## Not implemented yet

- `orders` app and order workflow
- Google OAuth, public signup, password reset
- Offline order queue and sync

See root `README.md` for the full list.

## Architecture conventions

```text
CLI / API / views  →  services.py  →  models.py  →  PostgreSQL
```

- Put reusable business/DB logic in `services.py`, not in views or management commands
- Tenant permission checks via `branches/permissions.py`
- Use `request.active_branch` (set by middleware) for branch-scoped features
- Plain Django + plain JavaScript — no React, Vue, or similar
- Minimize diff scope; match existing patterns in the file you edit

## Development pace

- One concept per phase; avoid large finished-app dumps
- See `products/products_docs/aux_instructions.md` for interaction style

## Commands

```bash
source .venv/bin/activate
cp config/settings.example.py config/settings.py   # first time only
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
python manage.py add_product "Description" 100 12.95
python manage.py test
```

## Security

- Do not commit `config/settings.py`, `.env`, or credentials
- Do not add product creation from the public web or phone UI unless explicitly requested

## Before large changes

1. Read root `README.md` for scope
2. Read `docs/warehouse-tenancy-setup.md` for order/tenancy design (orders section)
