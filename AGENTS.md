# CentCompras — Agent instructions

Django 6.1 + PostgreSQL MVP for a **central warehouse** with **satellite branches**. Branch staff browse a product catalogue from a phone browser; ordering and multi-tenancy are planned, not built yet.

## Current state (what exists)

- **App:** `products` only — catalogue model, service layer, API, CLI, offline-capable web UI
- **Database:** PostgreSQL (`centcompras_db`); `config/settings.py` is gitignored (local credentials)
- **Product fields:** `description`, `stock` (decimal), `price` (USD)
- **Product creation:** CLI only — `python manage.py add_product "..." stock price`
- **API:** `GET /api/products/` returns JSON catalogue
- **Web:** `/` product list; `/service-worker.js` at root for offline app shell
- **Offline:** Service Worker caches HTML/JS; IndexedDB caches catalogue from API (read-only local cache)

PostgreSQL is the source of truth. IndexedDB is not an independent warehouse database.

## Planned (not implemented)

Read before designing auth, branches, or orders:

- `docs/warehouse-tenancy-setup.md` — branches, email login, roles, tenant-scoped orders
- Root `README.md` — full list of what is not built yet

Do not assume `accounts`, `branches`, or `orders` apps exist.

## Architecture conventions

```text
CLI / API / views  →  services.py  →  models.py  →  PostgreSQL
```

- Put reusable business/DB logic in `services.py`, not in views or management commands
- Keep views thin (serialize, render, HTTP concerns only)
- Plain Django + plain JavaScript — no React, Vue, or similar
- Minimize diff scope; match existing patterns in the file you edit

## Development pace

The developer is learning the architecture incrementally.

- One concept per phase; avoid large finished-app dumps
- Prefer small, understandable changes with clear file paths
- Explain what each new file or function is responsible for
- Hybrid pace: not too slow, not a code dump

See `products/products_docs/aux_instructions.md` for detailed agent guidance from the original build.

## Commands

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py runserver
python manage.py add_product "Description" 100 12.95
python manage.py test
```

Use one hostname consistently when testing offline behaviour (`localhost` or `127.0.0.1`, not both).

## Security

- Do not commit `config/settings.py`, `.env`, or credentials
- Do not add product creation from the public web or phone UI unless explicitly requested

## Before large changes

1. Read root `README.md` for scope
2. Read `products/README.md` for catalogue/offline implementation detail
3. Read `docs/warehouse-tenancy-setup.md` if touching tenancy, auth, or orders
