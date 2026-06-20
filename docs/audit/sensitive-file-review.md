# Sensitive File Review

## Scope

- Checked repository working tree under `/Users/charles/Documents/智能agent开发`
- Reviewed tracked files, ignored files, and common secret-bearing patterns
- Reviewed current `.gitignore` coverage before baseline push

## Excluded Files And Directories

The following local-only artifacts were intentionally excluded from Git:

- `.venv/`, `backend/.venv/`
- `.uv-cache/`
- `.pytest_cache/`, `backend/.pytest_cache/`
- `.mypy_cache/`, `backend/.mypy_cache/`
- `.ruff_cache/`, `backend/.ruff_cache/`
- `frontend/node_modules/`
- `frontend/dist/`
- `backend/cold_storage_dev.db`
- `backend/storage/`

## Manual Confirmation Targets

These were checked because they often carry secrets or local state:

- `.env`
- `.env.example`
- `docker-compose.yml`
- local SQLite database paths
- certificate/key extensions
- uploaded/generated/runtime directories
- office/PDF/Excel/Word assets inside the repository

## Findings

- No tracked `.env` file was present in the baseline commit.
- `.env.example` contains placeholders only:
  `APP_ENV`, `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, `STORAGE_DIR`.
- No real API key, GitHub token, private key, or password-bearing connection
  string was detected by pattern scan in tracked source files.
- `backend/cold_storage_dev.db` exists locally but is ignored and was not staged.
- No user-uploaded files, internal office documents, private PDFs, or real
  factory/customer spreadsheets were found in tracked repository files.

## Need Human Confirmation

- None found in the tracked baseline snapshot.
- If local `.env` files or customer documents are added later, they must remain
  untracked and be reviewed before any future push.

## Suitability For Push

- Suitable for baseline push after `.gitignore` hardening.
- Baseline push was allowed because no sensitive local artifacts were staged.

---

## Security Incident: GitHub Token Leak (2026-06-20)

### Discovery

- **Discovered**: 2026-06-20, during Task 5 PR review
- **Files involved**: `.config/gh/hosts.yml`, `.config/gh/config.yml`
- **Content**: Plaintext GitHub OAuth token (`ghp_*`) in `hosts.yml`
- **Cause**: Local GitHub CLI configuration directory was accidentally committed

### Remediation

1. **Token revocation**: User confirmed token was NOT revoked (remains active)
2. **PR #6 closed**: Prevented further reference to contaminated commits
3. **History rewrite**: `git-filter-repo` v2.38.0 used to remove `.config/gh/**`
   from all branches, tags, and reachable history
4. **Clean branch**: `codex/task-5-cooling-load-capability` rebuilt from filtered history
5. **`.gitignore` updated**: `.config/gh/` added to prevent re-commitment
6. **Old local repo deleted**: `/root/cold-storage-planning-agent` removed
7. **New Draft PR #7**: Created from clean branch

### Verification

- `.config/gh/` absent from all tracked files: ✅
- `.config/gh/` absent from all reachable history: ✅
- Token pattern scan across all commits: **zero hits**
- Working tree token scan: **zero hits**
- `.env`, private keys, DB files tracked: **none**
- CI: 8/8 jobs passing

### Note

The token was NOT revoked by the user. The user should rotate the token
at their earliest convenience since it was exposed in a public GitHub
repository history (now cleaned).
