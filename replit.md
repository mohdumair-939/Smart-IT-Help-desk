# Smart Help Desk

IT service teams use Smart Help Desk to manage support requests, track ticket resolution, and share troubleshooting knowledge.

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the FastAPI server (port 8080)
- `pnpm --filter @workspace/api-server run migrate` — apply Alembic migrations to the development database
- `pnpm --filter @workspace/api-server run create-staff-user -- --role admin` — interactively create a staff account
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- Required environment: `DATABASE_URL`, `SESSION_SECRET` (at least 32 characters), and `OPENAI_API_KEY` for AI answers
- App Storage uses Replit-managed private object storage. Source documents are uploaded directly to storage; PostgreSQL stores document metadata and extracted passages.
- The frontend runs as the `artifacts/smart-help-desk: web` workflow.

## Stack

- Frontend: React, TypeScript, Vite, Tailwind CSS
- API: Python 3.13, FastAPI, SQLAlchemy, Alembic
- Database: PostgreSQL
- Password hashing: Argon2; API sessions use signed JWT bearer tokens
- Retrieval: LangChain text splitting, local FastEmbed embeddings, and ChromaDB with PostgreSQL-backed passage reconstruction
- AI generation: OpenAI `gpt-5.4-mini` through the configured OpenAI API key
- API contract: OpenAPI source with Orval-generated TypeScript clients and Zod schemas
- Workspace/build tooling: pnpm, Node.js, TypeScript

## Where things live

- `artifacts/smart-help-desk/` — React dashboard, ticket queue, and ticket workflows
- `artifacts/api-server/python/app/` — FastAPI routes, SQLAlchemy models, validation, and authorization
- `artifacts/api-server/python/migrations/` — Alembic schema migrations
- `artifacts/api-server/python/tests/` — backend unit tests
- `artifacts/api-server/python/app/knowledge_base.py` — document parsing, semantic retrieval, and Chroma indexing
- `artifacts/api-server/python/app/object_storage.py` — signed App Storage operations
- `lib/api-spec/openapi.yaml` — versioned API contract (`/api/v1`)
- `lib/api-client-react/` and `lib/api-zod/` — generated API hooks and validation schemas

## Architecture decisions

- Public registration creates employee accounts only. Support and admin accounts are created through the interactive staff-account command.
- API users see only their own tickets; support engineers and admins can work across the queue.
- Only admins manage approved knowledge documents; user questions are sent to OpenAI only when explicitly submitted.

## Product

- Employees can register, sign in, create tickets, track status, and comment.
- Support staff can search and update tickets, assign engineers, and review live queue metrics.
- Admins can ingest private PDF, DOCX, TXT, and Markdown files; employees and support staff can query the indexed articles with citations.
- Ticket pages can request a citation-backed AI resolution draft; staff must review it before saving.

## User preferences

-

## Gotchas

- Update `lib/api-spec/openapi.yaml`, run codegen, then update the FastAPI implementation to match the generated contract.
- Apply local schema changes with Alembic before using the API.
- Store uploaded file bytes in App Storage and keep extracted passage text and searchable metadata in PostgreSQL.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
