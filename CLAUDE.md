# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AutoBangumi is an RSS-based automatic anime downloading and organization tool. It monitors RSS feeds from anime torrent sites (Mikan, DMHY, Nyaa), downloads episodes via qBittorrent, and organizes files into a Plex/Jellyfin-compatible directory structure with automatic renaming.

## Development Commands

### Backend (Python)

```bash
# Install dependencies
cd backend && uv sync

# Install with dev tools
cd backend && uv sync --group dev

# Run development server (port 7892, API docs at /docs)
cd backend/src && uv run python main.py

# Run all tests
cd backend && uv run pytest

# Run a single test file
cd backend && uv run pytest src/test/test_xxx.py -v

# Run a specific test function
cd backend && uv run pytest src/test/test_xxx.py::test_func_name -v

# E2E tests (require Docker, marked separately)
cd backend && uv run pytest -m e2e

# Linting and formatting
cd backend && uv run ruff check src
cd backend && uv run black src

# Add a dependency
cd backend && uv add <package>

# Add a dev dependency
cd backend && uv add --group dev <package>
```

### Frontend (Vue 3 + TypeScript)

```bash
cd webui

# Install dependencies (uses pnpm, NOT npm)
pnpm install

# Development server (port 5173, proxies /api to localhost:7892)
pnpm dev

# Build for production
pnpm build

# Type checking (vue-tsc --noEmit)
pnpm test:build

# Linting and formatting
pnpm lint
pnpm lint:fix
pnpm format
```

### Docker

```bash
docker build -t auto_bangumi:latest .
docker run -p 7892:7892 -v /path/to/config:/app/config -v /path/to/data:/app/data auto_bangumi:latest
```

## Architecture

### Backend Structure

```
backend/src/
├── main.py                 # FastAPI entry point (lifespan context manager)
├── module/
│   ├── api/               # REST API routes — all routers registered in __init__.py under /api/v1
│   ├── core/
│   │   ├── program.py     # Main controller — uses MULTIPLE INHERITANCE from thread classes
│   │   └── sub_thread.py  # Background async threads (RSS, Rename, OffsetScan, Calendar)
│   ├── models/            # SQLModel ORM models (Pydantic + SQLAlchemy hybrid)
│   ├── database/          # SQLite operations — uses composition pattern (see below)
│   ├── conf/              # Config management — singleton `settings`, JSON file + env vars
│   ├── rss/               # RSS feed parsing and analysis
│   ├── downloader/        # Download client abstraction (qb, aria2) with factory method
│   ├── parser/            # Torrent name parsing — regex + TMDB + OpenAI strategies
│   ├── manager/           # File organization and renaming into Plex/Jellyfin structure
│   ├── notification/      # Notification plugins (Telegram, Bark, etc.)
│   ├── security/          # JWT auth (HttpOnly cookies) + WebAuthn strategy pattern
│   ├── mcp/               # Model Context Protocol server mounted at /mcp
│   └── network/           # HTTP client utilities (httpx with SOCKS proxy)
```

### Frontend Structure

```
webui/src/
├── pages/                 # File-based routing (unplugin-vue-router) — just create .vue files
├── components/            # Auto-imported components (no manual imports needed)
│   ├── basic/             # Reusable primitives (ab-button, ab-switch, etc.)
│   ├── layout/            # Layout (sidebar, topbar, mobile-nav)
│   ├── setting/           # Config panels (config-*.vue)
│   └── setup/             # Setup wizard steps (wizard-step-*.vue)
├── api/                   # Axios API modules — auto-imported globally
├── store/                 # Pinia stores (composition API style)
├── hooks/                 # Custom composables — auto-imported globally
├── i18n/                  # Internationalization (zh-CN, en)
├── style/                 # CSS variables, mixins, UnoCSS
└── types/                 # TypeScript definitions + auto-generated .d.ts
```

## Key Architectural Patterns

### Backend: Program Controller (Multiple Inheritance)

`Program` in `core/program.py` inherits from four thread classes (`RenameThread`, `RSSThread`, `OffsetScanThread`, `CalendarRefreshThread`). Each thread runs an async loop with cooperative cancellation via `asyncio.Event`. The startup method uses a `_startup_done` guard to prevent duplicate initialization from nested lifespan events.

### Backend: Database Composition

Database access uses a composition pattern in `database/combine.py`:
```python
class Database(Session):
    def __init__(self):
        self.rss = RSSDatabase(self)
        self.torrent = TorrentDatabase(self)
        self.bangumi = BangumiDatabase(self)
        self.user = UserDatabase(self)
```
The main `Program` instance holds a `Database` that provides access to all sub-databases.

### Backend: Configuration Dual Loading

Config (`conf/config.py`) loads from two sources:
1. **JSON file** (`config/config.json`) — if it exists, load and auto-migrate from older versions
2. **Environment variables** (prefixed `AB_*`) — used when no config file exists, mapped via `ENV_TO_ATTR` in `conf/const.py`

Config is a module-level singleton accessed as `from module.conf import settings`.

### Backend: API Route Registration

All API routers are registered in `module/api/__init__.py` under the `/api/v1` prefix. To add a new endpoint:
1. Create a router in `module/api/new_feature.py`
2. Import and include it in `module/api/__init__.py`

Auth is handled via FastAPI's `Depends()` injection using JWT tokens stored in HttpOnly cookies.

### Backend: Downloader Factory

`DownloadClient` uses a factory method pattern — `__getClient()` returns the appropriate client based on config. Supported: qBittorrent (primary), Aria2, MockDownloader (tests). All clients follow async context manager protocol. Torrent tracking uses tags (`ab:<bangumi_id>`) for episode offset lookup.

### Frontend: Zero-Import Development

The frontend uses three unplugin tools for automatic imports — no manual import statements needed for:
- **Vue APIs** (`ref`, `computed`, `watch`), **VueUse**, **Pinia**, **Vue Router**
- **All components** in `src/components/` (use `<AbButton />` directly)
- **All composables** in `src/hooks/` (use `useApi()` directly)
- **All API modules** in `src/api/` (use `apiBangumi.getAll()` directly)

### Frontend: File-Based Routing

Routes are generated from `src/pages/**/*.vue`. To add a page:
1. Create `src/pages/my-page.vue`
2. Optionally add `definePage({ name: 'My Page' })`
3. Route is auto-generated as `/my-page`

Navigation guards handle auth checks and setup redirects.

### Frontend: API Wrapper Pattern

All store actions use the `useApi()` composable for consistent error handling, loading states, and success/error messages:
```typescript
const { execute, isLoading } = useApi(apiBangumi.updateRule, {
  showMessage: true,
  onSuccess() { /* refresh */ },
});
```

Axios response interceptor auto-handles 401 (logout) and 500 (error message) responses.

### Frontend: Path Aliases

- `@/` → `src/`
- `~/` → project root
- `#/` → `types/`

## Key Data Flow

1. RSS feeds parsed by `module/rss/` → extract torrent info
2. Torrent names analyzed by `module/parser/` → extract anime metadata (regex + TMDB + optional OpenAI)
3. Downloads managed via `module/downloader/` → qBittorrent API integration
4. Files organized by `module/manager/` → rename to Plex/Jellyfin-compatible structure
5. Background threads run in `module/core/sub_thread.py` — four threads with configurable intervals

## Database Migrations

Schema migrations tracked via `schema_version` table in SQLite (`data/data.db`). To add a migration:

1. Increment `CURRENT_SCHEMA_VERSION` in `backend/src/module/database/combine.py`
2. Append to `MIGRATIONS` list: `(version, "description", ["SQL statements"])`
3. Migrations run automatically on startup via `run_migrations()`

Each migration should be idempotent (check if column exists before altering).

## Testing

### Backend Tests
- **Location**: `backend/src/test/`
- **Framework**: pytest + pytest-asyncio (auto mode) + pytest-mock
- **Fixtures** (`conftest.py`): In-memory SQLite database, async mock downloader, auth bypass client
- **E2E tests**: Marked with `@pytest.mark.e2e`, require Docker

### Frontend Tests
- **Type check**: `pnpm test:build` (runs `vue-tsc --noEmit`)
- **Unit tests**: Vitest + Vue Test Utils + Happy DOM

## Code Style

- **Python**: Black (88 char), Ruff (E, F, I rules; ignores E501, F401), target Python 3.13
- **TypeScript**: ESLint + Prettier, strict mode
- **CSS**: UnoCSS with Tailwind preset + scoped component styles with CSS variables
- **Run formatters before committing**

## Git Branching

- `main`: Stable releases only
- `X.Y-dev` branches: Active development (e.g., `3.2-dev`)
- Bug fixes → PR to current released version's `-dev` branch
- New features → PR to next version's `-dev` branch

## Releasing

### Beta/Alpha Release
1. Update version in `backend/pyproject.toml`
2. Update `CHANGELOG.md`
3. Commit and push to dev branch
4. Create and push tag: `git tag 3.2.0-beta.4 && git push origin 3.2.0-beta.4`
5. CI detects "beta"/"alpha" in tag → builds Docker image → pushes to Docker Hub + GHCR → creates GitHub pre-release

### Stable Release
1. Create PR from dev branch to `main` with version in title
2. Merge PR → CI auto-runs tests, builds multi-arch Docker images, creates GitHub release, sends Telegram notification

VERSION is injected at build time — `module/__version__.py` does NOT exist in the repo. At runtime, `conf/config.py` imports it or falls back to `"DEV_VERSION"`.

## Notes

- Documentation and comments are in Chinese
- Uses SQLModel (hybrid Pydantic + SQLAlchemy ORM)
- External integrations: qBittorrent API, TMDB API, OpenAI API, WebAuthn
- Version tracked in `/config/version.info` (for cross-version upgrade detection)
- Docker runs as non-root user (UID 911) with `tini` init system
- MCP server available at `/mcp` for LLM tool integration
