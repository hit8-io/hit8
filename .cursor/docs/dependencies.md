# Dependencies

## Backend Dependencies

### Package Management

The backend uses **uv** for fast Python package management, configured via `pyproject.toml`.

**File**: [`backend/pyproject.toml`](backend/pyproject.toml)

**Installation:**
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
cd backend
uv pip install -e .
```

**Lock File**: `backend/uv.lock`
- Generated automatically by uv
- Ensures reproducible builds
- Should be committed to version control

### Key Dependencies

**Web Framework:**
- `fastapi>=0.127.0`: Modern, fast web framework
- `uvicorn[standard]>=0.40.0`: ASGI server with standard extras

**Configuration:**
- `pydantic>=2.12.5`: Data validation using Python type annotations
- `pydantic-settings>=2.12.0`: Settings management for Pydantic
- `pyyaml>=6.0.3`: YAML parser for configuration files
- `types-PyYAML>=6.0.12`: Type stubs for PyYAML

**AI/LLM:**
- `langchain-core>=1.2.5`: Core LangChain functionality
- `langgraph>=1.0.5`: State machine for AI agent orchestration
- `langchain-google-genai>=4.1.2`: Google Generative AI integration for Vertex AI

**Authentication:**
- `firebase-admin>=7.1.0`: Firebase Admin SDK for token verification
- `google-auth>=2.45.0`: Google authentication library

**Database:**
- `supabase>=2.27.0`: Supabase Python client

**Security:**
- `cryptography>=46.0.3`: Cryptographic primitives

**Testing:**
- `pytest>=8.0.0`: Testing framework
- `pytest-asyncio>=0.23.0`: Async test support
- `httpx>=0.27.0`: Async HTTP client for testing

### Dependency Categories

**Runtime Dependencies:**
- All dependencies listed in `[project.dependencies]`
- Required for application to run
- Installed in production

**Build Dependencies:**
- `hatchling`: Build backend (specified in `[build-system]`)
- Used only during package building

### Version Pinning Strategy

**Minimum Versions:**
- Dependencies use `>=` for minimum version
- Allows patch and minor version updates
- Prevents breaking changes from major updates

**Example:**
```toml
dependencies = [
    "fastapi>=0.127.0",  # Allows 0.127.0, 0.128.0, etc., but not 0.126.0
]
```

**Benefits:**
- Security updates automatically included
- Bug fixes available
- Maintains compatibility

## Frontend Dependencies

### Package Management

The frontend uses **npm** for package management, configured via `package.json`.

**File**: [`frontend/package.json`](frontend/package.json)

**Installation:**
```bash
cd frontend
npm install
```

**Lock File**: `frontend/package-lock.json`
- Generated automatically by npm
- Ensures reproducible builds
- Should be committed to version control

### Key Dependencies

**Core Framework:**
- `react>=18.2.0`: React library
- `react-dom>=18.2.0`: React DOM renderer

**Build Tool:**
- `vite>=5.0.11`: Fast build tool and dev server

**HTTP Client:**
- `axios>=1.6.5`: Promise-based HTTP client

**Authentication:**
- `firebase>=12.7.0`: Firebase SDK for authentication

**UI Libraries:**
- `lucide-react>=0.344.0`: Icon library
- `tailwind-merge>=2.2.0`: Utility for merging Tailwind classes
- `clsx>=2.1.0`: Utility for constructing className strings

### Dev Dependencies

**TypeScript:**
- `typescript>=5.3.3`: TypeScript compiler
- `@types/react>=18.2.48`: TypeScript types for React
- `@types/react-dom>=18.2.18`: TypeScript types for React DOM

**Linting:**
- `eslint>=8.56.0`: JavaScript/TypeScript linter
- `@typescript-eslint/eslint-plugin>=6.19.0`: TypeScript ESLint plugin
- `@typescript-eslint/parser>=6.19.0`: TypeScript parser for ESLint
- `eslint-plugin-react-hooks>=4.6.0`: React Hooks linting rules
- `eslint-plugin-react-refresh>=0.4.5`: React Fast Refresh linting

**Styling:**
- `tailwindcss>=3.4.1`: Utility-first CSS framework
- `tailwindcss-animate>=1.0.7`: Animation utilities for Tailwind
- `autoprefixer>=10.4.17`: CSS vendor prefixer
- `postcss>=8.4.33`: CSS post-processor

**Build:**
- `@vitejs/plugin-react>=4.2.1`: Vite plugin for React

### Dependency Categories

**Production Dependencies:**
- Listed in `dependencies`
- Required for application to run
- Bundled in production build

**Development Dependencies:**
- Listed in `devDependencies`
- Used only during development
- Not included in production build

### Version Pinning Strategy

**Caret Ranges:**
- Dependencies use `^` for version ranges
- Allows compatible version updates
- Example: `^1.6.5` allows `1.6.5` to `1.x.x` but not `2.0.0`

**Benefits:**
- Security updates automatically included
- Bug fixes available
- Maintains compatibility

## Dependency Updates

### Backend Updates

**Check for Updates:**
```bash
cd backend
uv pip list --outdated
```

**Update Dependencies:**
```bash
# Update specific package
uv pip install --upgrade fastapi

# Update all packages (use with caution)
uv pip install --upgrade -e .
```

**Update Lock File:**
```bash
# Regenerate lock file
uv lock
```

**Test After Updates:**
```bash
# Run tests to ensure compatibility
pytest
```

### Frontend Updates

**Check for Updates:**
```bash
cd frontend
npm outdated
```

**Update Dependencies:**
```bash
# Update specific package
npm install axios@latest

# Update all packages (use with caution)
npm update

# Update to latest versions (may include breaking changes)
npm install package@latest
```

**Update Lock File:**
```bash
# Lock file updated automatically on install
npm install
```

**Test After Updates:**
```bash
# Run linter
npm run lint

# Build to check for errors
npm run build
```

### Best Practices

1. **Update Regularly**: Keep dependencies up to date for security
2. **Test Thoroughly**: Run tests after updating dependencies
3. **Read Changelogs**: Check for breaking changes
4. **Update Incrementally**: Update one package at a time when possible
5. **Commit Lock Files**: Always commit updated lock files

## Security Considerations

### Vulnerability Scanning

**Backend:**
```bash
# Use safety or similar tool
pip install safety
safety check
```

**Frontend:**
```bash
# Use npm audit
npm audit

# Fix vulnerabilities
npm audit fix
```

### Dependency Pinning

**Backend:**
- Lock file (`uv.lock`) pins exact versions
- Ensures reproducible builds
- Prevents unexpected updates

**Frontend:**
- Lock file (`package-lock.json`) pins exact versions
- Ensures reproducible builds
- Prevents unexpected updates

## Build Configuration

### Backend Build

**Build System**: Hatchling (specified in `pyproject.toml`)

**Configuration:**
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

**Build Command:**
```bash
cd backend
uv pip install -e .
```

### Frontend Build

**Build Tool**: Vite

**Configuration**: `vite.config.ts`

**Build Commands:**
```bash
# Standard build
npm run build

# Cloudflare Pages build
npm run build:cloudflare
```

**Build Output:**
- Directory: `dist/`
- Contains: Optimized HTML, CSS, JavaScript bundles













