# Smart Help Desk

Smart Help Desk is an IT support portal for employee requests, service-team triage, approved knowledge articles, and cited AI troubleshooting suggestions.

## Current capabilities

- Employee self-registration and JWT sign-in with Argon2 password hashing.
- Role-aware employee, support-engineer, and administrator workflows.
- Ticket submission, search, filtering, assignment, status and resolution updates, comments, and an activity feed.
- Private ticket attachments with file-type and size limits, signed downloads, and activity history.
- PostgreSQL persistence with versioned Alembic migrations.
- Administrator-only knowledge document uploads for PDF, DOCX, TXT, and Markdown files. File bytes are stored privately in App Storage; extracted passages and metadata are stored in PostgreSQL.
- Local FastEmbed embeddings and a Chroma index support semantic retrieval. The index is rebuilt from PostgreSQL passages if its local cache is empty.
- Natural-language help and ticket-specific resolution drafts cite retrieved articles. Questions and ticket details are sent to OpenAI only when a user explicitly requests an answer; never submit passwords, tokens, or sensitive personal information.

## Run locally in Replit

The app uses the configured `artifacts/smart-help-desk: web` and `artifacts/api-server: API Server` workflows.

```bash
pnpm --filter @workspace/api-server run migrate
pnpm --filter @workspace/api-server run dev
pnpm --filter @workspace/smart-help-desk run dev
```

Required Replit secrets and managed environment:

- `DATABASE_URL` — PostgreSQL connection.
- `SESSION_SECRET` — signing key for JWTs; use the existing workspace secret.
- `OPENAI_API_KEY` — optional for the ticketing system, required for grounded AI answers.
- App Storage paths are provisioned through Replit's Object Storage setup.

There are no demo accounts. Employees can register from the sign-in page. Create the first administrator interactively from a trusted workspace terminal:

```bash
pnpm --filter @workspace/api-server run create-staff-user -- --role admin
```

Use the same command with `--role support_engineer` to create another staff account. Staff passwords are entered through a hidden terminal prompt and are not printed.

## Development checks

```bash
pnpm --filter @workspace/api-spec run codegen
pnpm typecheck
pnpm --filter @workspace/api-server run build
pnpm --filter @workspace/api-server run test
```

Edit `lib/api-spec/openapi.yaml` first when changing the API contract, then regenerate TypeScript clients before updating the frontend. Add database changes to `artifacts/api-server/python/migrations/versions/`.

## Access and data handling

- Public registration always creates an employee; it cannot select a staff role.
- Employees can read and comment on their own tickets. Support engineers and administrators can work across the queue.
- Only administrators can upload or delete knowledge-base source documents.
- Knowledge-base sources stay private. The browser uploads file bytes directly to App Storage using a short-lived signed URL.
- The AI helper uses retrieved articles as evidence and returns citations. If it finds no relevant article, it asks the user to contact support instead of inventing steps.
