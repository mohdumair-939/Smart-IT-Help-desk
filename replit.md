# Smart Help Desk

IT service teams use Smart Help Desk to manage support requests, track ticket resolution, and share troubleshooting knowledge.

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the FastAPI server (port 8080)
- `pnpm --filter @workspace/api-server run migrate` — apply Alembic migrations to the development database
- `pnpm --filter @workspace/api-server run create-staff-user -- --role admin` — interactively create a staff account
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- Required environment: `DATABASE_URL` and `SESSION_SECRET` (at least 32 characters)
- The frontend runs as the `artifacts/smart-help-desk: web` workflow.

## Stack

- Frontend: React, TypeScript, Vite, Tailwind CSS
- API: Python 3.13, FastAPI, SQLAlchemy, Alembic
- Database: PostgreSQL
- Password hashing: Argon2; API sessions use signed JWT bearer tokens
- API contract: OpenAPI source with Orval-generated TypeScript clients and Zod schemas
- Workspace/build tooling: pnpm, Node.js, TypeScript

## Where things live

- `artifacts/smart-help-desk/` — React dashboard, ticket queue, and ticket workflows
- `artifacts/api-server/python/app/` — FastAPI routes, SQLAlchemy models, validation, and authorization
- `artifacts/api-server/python/migrations/` — Alembic schema migrations
- `lib/api-spec/openapi.yaml` — versioned API contract (`/api/v1`)
- `lib/api-client-react/` and `lib/api-zod/` — generated API hooks and validation schemas

## Architecture decisions

- Public registration creates employee accounts only. Support and admin accounts are created through the interactive staff-account command.
- API users see only their own tickets; support engineers and admins can work across the queue.

## Product

- Employees can register, sign in, create tickets, track status, and comment.
- Support staff can search and update tickets, assign engineers, and review live queue metrics.
- Knowledge-base ingestion and grounded AI assistance are planned as later milestones; they are not implemented yet.

## User preferences

-

## Gotchas

- Update `lib/api-spec/openapi.yaml`, run codegen, then update the FastAPI implementation to match the generated contract.
- Apply local schema changes with Alembic before using the API.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
