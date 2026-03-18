# i18n Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 3-language (zh-CN/en-US/es-ES) internationalization to CPS Admin Dashboard with user-bound locale preference.

**Architecture:** react-i18next for frontend i18n, LocaleProvider context + useLocale hook for atomic locale switching (i18n + Ant Design), localStorage + DB dual storage with local-first sync, PATCH /auth/locale backend endpoint.

**Key architectural note:** `useLocale` state is shared via React Context (LocaleProvider wraps App). All components consume locale via `useContext`, NOT by calling `useLocale()` independently — this prevents multi-instance state desync between ConfigProvider and LangSwitcher.

**Tech Stack:** react-i18next, i18next, Ant Design ConfigProvider locale, Intl.DateTimeFormat, Intl.NumberFormat, FastAPI, Alembic, PostgreSQL

**Spec:** `docs/superpowers/specs/2026-03-18-i18n-design.md`

---

## Chunk 1: Backend — DB + API (Tasks 1-3)

### Task 1: Alembic Migration — add locale column

**Files:**
- Create: `alembic/versions/005_add_admin_locale.py`
- Modify: `src/cps/db/models.py` (AdminUser class, ~line 408-422)

- [ ] **Step 1: Write migration file**

```python
# alembic/versions/005_add_admin_locale.py
"""Add locale column to admin_users."""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("admin_users", sa.Column("locale", sa.String(10), nullable=False, server_default="zh-CN"))
    op.create_check_constraint("ck_admin_users_locale", "admin_users",
        "locale IN ('zh-CN', 'en-US', 'es-ES')")

def downgrade() -> None:
    op.drop_constraint("ck_admin_users_locale", "admin_users", type_="check")
    op.drop_column("admin_users", "locale")
```

- [ ] **Step 2: Add locale field to AdminUser model**

In `src/cps/db/models.py`, add to AdminUser class (after `role` field ~line 418):

```python
locale: Mapped[str] = mapped_column(String(10), nullable=False, server_default="zh-CN")
```

- [ ] **Step 3: Run migration**

```bash
source .venv/bin/activate && alembic upgrade head
```
Expected: `005 (head)` with no errors.

- [ ] **Step 4: Verify column exists**

```bash
source .venv/bin/activate && python -c "
import asyncio
from cps.config import get_settings
from cps.db.session import create_session_factory
from sqlalchemy import text
async def check():
    factory = create_session_factory(get_settings().database_url)
    async with factory() as s:
        r = await s.execute(text(\"SELECT column_name, column_default FROM information_schema.columns WHERE table_name='admin_users' AND column_name='locale'\"))
        print(r.fetchone())
asyncio.run(check())
"
```
Expected: `('locale', "'zh-CN'::character varying")`

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/005_add_admin_locale.py src/cps/db/models.py
git commit -m "feat(i18n): add locale column to admin_users table"
```

---

### Task 2: PATCH /auth/locale endpoint

**Files:**
- Create: `src/cps/api/schemas/locale.py`
- Modify: `src/cps/api/schemas/auth.py` (~17 lines)
- Modify: `src/cps/api/routes/auth.py` (~65 lines)
- Test: `tests/unit/api/test_auth_routes.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/api/test_auth_routes.py` (using existing `auth_client`/`anon_client`/`mock_user` fixtures from conftest.py):

```python
class TestUpdateLocale:
    async def test_update_locale_success(self, auth_client, mock_user):
        """PATCH /auth/locale updates user locale and returns new value."""
        mock_user.locale = "zh-CN"
        async with await auth_client() as client:
            response = await client.patch(
                "/api/v1/auth/locale",
                json={"locale": "en-US"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert response.status_code == 200
        assert response.json()["locale"] == "en-US"
        assert mock_user.locale == "en-US"

    async def test_update_locale_invalid_value(self, auth_client, mock_user):
        """PATCH /auth/locale rejects invalid locale."""
        mock_user.locale = "zh-CN"
        async with await auth_client() as client:
            response = await client.patch(
                "/api/v1/auth/locale",
                json={"locale": "invalid"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert response.status_code == 422

    async def test_update_locale_requires_auth(self, anon_client):
        """PATCH /auth/locale returns 401 without session."""
        async with await anon_client() as client:
            response = await client.patch(
                "/api/v1/auth/locale",
                json={"locale": "en-US"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate && python -m pytest tests/unit/api/test_auth_routes.py::TestUpdateLocale -v
```
Expected: FAIL (endpoint not implemented)

- [ ] **Step 3: Create LocaleUpdateRequest schema (separate file)**

Create `src/cps/api/schemas/locale.py`:

```python
from typing import Literal
from pydantic import BaseModel

class LocaleUpdateRequest(BaseModel):
    locale: Literal["zh-CN", "en-US", "es-ES"]
```

- [ ] **Step 4: Add locale to UserResponse**

In `src/cps/api/schemas/auth.py`, add `locale: str` to `UserResponse`.

- [ ] **Step 5: Implement PATCH endpoint**

In `src/cps/api/routes/auth.py`, add:

```python
from starlette.requests import Request
from cps.api.schemas.locale import LocaleUpdateRequest

@router.patch("/locale")
async def update_locale(
    body: LocaleUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[AdminUser, Depends(get_current_user)],
):
    current_user.locale = body.locale
    await db.commit()
    client_ip = request.client.host if request.client else "unknown"
    # log_audit signature: (db, user_id, action, resource_type, ip_address, resource_id, details)
    await log_audit(db, current_user.id, "update_locale", "user", client_ip, str(current_user.id))
    return {"locale": current_user.locale}
```

- [ ] **Step 6: Update /auth/me to include locale**

In the existing `me()` endpoint in `auth.py`, ensure the response includes `locale` field. The `UserResponse` schema already has it from Step 4.

- [ ] **Step 7: Run tests**

```bash
source .venv/bin/activate && python -m pytest tests/unit/api/test_auth_routes.py -v
```
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add src/cps/api/schemas/auth.py src/cps/api/routes/auth.py tests/unit/api/test_auth_routes.py
git commit -m "feat(i18n): add PATCH /auth/locale endpoint with validation and audit"
```

---

### Task 3: Backend verification

- [ ] **Step 1: Run full backend test suite**

```bash
source .venv/bin/activate && python -m pytest tests/ -x -q
```
Expected: All tests pass (387+ tests)

- [ ] **Step 2: Verify no regressions**

```bash
source .venv/bin/activate && python -m pytest tests/ --tb=short 2>&1 | tail -5
```
Expected: 0 failures

---

## Chunk 2: Frontend Foundation — i18n setup (Tasks 4-8)

**IMPORTANT task ordering:** Task 4 installs deps + creates translations. Task 5 adds `updateLocale` to endpoints.ts (must come BEFORE Task 6 since useLocale.ts imports it). Task 6 creates the i18n core files. Task 7 wires App.tsx. Task 8 creates LangSwitcher.

### Task 4: Install dependencies + create translation files

**Files:**
- Modify: `web/package.json`
- Create: `web/src/i18n/locales/zh-CN.json`
- Create: `web/src/i18n/locales/en-US.json`
- Create: `web/src/i18n/locales/es-ES.json`

- [ ] **Step 1: Install i18next + react-i18next**

```bash
cd /Users/victor/claudecode/cps/web && npm install i18next react-i18next
```

- [ ] **Step 2: Create zh-CN.json**

Create `web/src/i18n/locales/zh-CN.json` with the full key list from spec (section "Translation Key Structure"). This is the reference file for TypeScript types.

- [ ] **Step 3: Create en-US.json**

Create `web/src/i18n/locales/en-US.json` with English translations for all keys. Use the original English strings from the source code as reference.

- [ ] **Step 4: Create es-ES.json**

Create `web/src/i18n/locales/es-ES.json` with Spanish translations for all keys.

- [ ] **Step 5: Commit**

```bash
git add web/package.json web/package-lock.json web/src/i18n/locales/
git commit -m "feat(i18n): add i18next deps and 3 translation files (zh-CN, en-US, es-ES)"
```

---

### Task 5: Add updateLocale to API client + User type

**Must run BEFORE Task 6** — useLocale.ts imports `updateLocale` from endpoints.ts.

**Files:**
- Modify: `web/src/api/endpoints.ts` (~line 88, end of file)
- Modify: `web/src/types/index.ts` (User interface, ~line 1-7)

- [ ] **Step 1: Add updateLocale to endpoints.ts**

At end of `web/src/api/endpoints.ts`:

```typescript
export const updateLocale = (locale: string) =>
  api.patch(`${BASE}/auth/locale`, { locale })
```

- [ ] **Step 2: Add locale to User type**

In `web/src/types/index.ts`, add `locale: string` to the `User` interface.

- [ ] **Step 3: Commit**

```bash
git add web/src/api/endpoints.ts web/src/types/index.ts
git commit -m "feat(i18n): add updateLocale API endpoint and locale to User type"
```

---

### Task 6: i18n initialization + useLocale Context + TypeScript types

**Files:**
- Create: `web/src/i18n/index.ts`
- Create: `web/src/i18n/i18n.d.ts`
- Create: `web/src/i18n/useLocale.ts` (exports getSafeLocale + LocaleProvider + useLocaleContext)
- Modify: `web/src/main.tsx` (line 1-10)

**IMPORTANT:** `useLocale` state is shared via React Context (LocaleProvider). All components use `useLocaleContext()` to get the SAME state instance. This prevents multi-instance desync between ConfigProvider's antdLocale and LangSwitcher's locale state.

- [ ] **Step 1: Create useLocale.ts with Context Provider**

Create `web/src/i18n/useLocale.ts`:

```typescript
import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import zhCN from 'antd/locale/zh_CN'
import enUS from 'antd/locale/en_US'
import esES from 'antd/locale/es_ES'  // verified: antd/locale/es_ES.js exists
import type { Locale } from 'antd/es/locale'
import { updateLocale as apiUpdateLocale } from '../api/endpoints'

export const SUPPORTED_LOCALES = ['zh-CN', 'en-US', 'es-ES'] as const
export type SupportedLocale = typeof SUPPORTED_LOCALES[number]

const LOCALE_KEY = 'locale'

export function getSafeLocale(raw: string | null): SupportedLocale {
  return SUPPORTED_LOCALES.includes(raw as SupportedLocale)
    ? (raw as SupportedLocale)
    : 'zh-CN'
}

const antdLocaleMap: Record<SupportedLocale, Locale> = {
  'zh-CN': zhCN,
  'en-US': enUS,
  'es-ES': esES,
}

interface LocaleContextValue {
  locale: SupportedLocale
  antdLocale: Locale
  changeLocale: (l: SupportedLocale) => Promise<void>
  syncAfterLogin: (serverLocale: string) => Promise<void>
}

const LocaleContext = createContext<LocaleContextValue | null>(null)

export function LocaleProvider({ children, isLoggedIn = false }: { children: ReactNode; isLoggedIn?: boolean }) {
  const { i18n } = useTranslation()
  const [locale, setLocale] = useState<SupportedLocale>(
    getSafeLocale(typeof localStorage !== 'undefined' ? localStorage.getItem(LOCALE_KEY) : null)
  )

  const antdLocale = antdLocaleMap[locale]

  const changeLocale = useCallback(async (newLocale: SupportedLocale) => {
    await i18n.changeLanguage(newLocale)
    setLocale(newLocale)
    localStorage.setItem(LOCALE_KEY, newLocale)
    if (isLoggedIn) {
      apiUpdateLocale(newLocale).catch(() => {})  // fire-and-forget
    }
  }, [i18n, isLoggedIn])

  const syncAfterLogin = useCallback(async (serverLocale: string) => {
    const raw = localStorage.getItem(LOCALE_KEY)
    if (raw !== null) {
      apiUpdateLocale(getSafeLocale(raw)).catch(() => {})  // local wins
    } else {
      const safe = getSafeLocale(serverLocale)
      await i18n.changeLanguage(safe)
      setLocale(safe)
      localStorage.setItem(LOCALE_KEY, safe)  // server wins
    }
  }, [i18n])

  return (
    <LocaleContext value={{ locale, antdLocale, changeLocale, syncAfterLogin }}>
      {children}
    </LocaleContext>
  )
}

export function useLocaleContext() {
  const ctx = useContext(LocaleContext)
  if (!ctx) throw new Error('useLocaleContext must be used within LocaleProvider')
  return ctx
}
```

- [ ] **Step 2: Create i18n/index.ts**

```typescript
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import zhCN from './locales/zh-CN.json'
import enUS from './locales/en-US.json'
import esES from './locales/es-ES.json'
import { getSafeLocale } from './useLocale'

const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('locale') : null

i18n.use(initReactI18next).init({
  resources: {
    'zh-CN': { translation: zhCN },
    'en-US': { translation: enUS },
    'es-ES': { translation: esES },
  },
  lng: getSafeLocale(stored),
  fallbackLng: 'zh-CN',
  interpolation: { escapeValue: true },
  returnNull: false,
})

export default i18n
```

- [ ] **Step 3: Create i18n.d.ts**

```typescript
import 'i18next'
import type zhCN from './locales/zh-CN.json'

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation'
    resources: { translation: typeof zhCN }
  }
}
```

- [ ] **Step 4: Import i18n in main.tsx**

Add `import './i18n'` as the first import in `web/src/main.tsx` (before React imports).

- [ ] **Step 5: Verify build compiles**

```bash
cd /Users/victor/claudecode/cps/web && npx tsc --noEmit
```
Expected: No type errors

- [ ] **Step 6: Commit**

```bash
git add web/src/i18n/ web/src/main.tsx
git commit -m "feat(i18n): add i18n initialization, useLocale hook, and TypeScript types"
```

---

### Task 7: Wire LocaleProvider into App.tsx + useAuth sync

**Files:**
- Modify: `web/src/App.tsx` (~59 lines)
- Modify: `web/src/hooks/useAuth.ts` (~32 lines)

- [ ] **Step 1: Update App.tsx**

In `web/src/App.tsx`:
- Import `LocaleProvider` and `useLocaleContext` from `./i18n/useLocale`
- Wrap the entire app in `<LocaleProvider>`
- Create an inner component that reads `useLocaleContext()` and passes `antdLocale` to `<ConfigProvider>`
- Pass `isLoggedIn` prop to LocaleProvider based on auth state

- [ ] **Step 2: Sync locale after login**

In Login.tsx (where login is called), after successful login, call `syncAfterLogin(res.data.locale)` from `useLocaleContext()`. This keeps the sync logic in the component that knows about both auth and locale.

- [ ] **Step 3: Verify build compiles**

```bash
cd /Users/victor/claudecode/cps/web && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add web/src/App.tsx web/src/hooks/useAuth.ts
git commit -m "feat(i18n): wire useLocale into App + sync locale after login"
```

---

## Chunk 3: Shared Components + Utilities (Tasks 8-10)

### Task 8: LangSwitcher component

**Files:**
- Create: `web/src/components/LangSwitcher.tsx`

- [ ] **Step 1: Create LangSwitcher**

```typescript
import { Select } from 'antd'
import { useTranslation } from 'react-i18next'
import { useLocaleContext, SUPPORTED_LOCALES, type SupportedLocale } from '../i18n/useLocale'

export default function LangSwitcher() {
  const { t } = useTranslation()
  const { locale, changeLocale } = useLocaleContext()  // shared context, NOT independent hook

  const labelMap: Record<SupportedLocale, string> = {
    'zh-CN': t('lang.zhCN'),
    'en-US': t('lang.enUS'),
    'es-ES': t('lang.esES'),
  }

  return (
    <Select
      value={locale}
      onChange={changeLocale}
      options={SUPPORTED_LOCALES.map(l => ({ value: l, label: labelMap[l] }))}
      variant="borderless"
      style={{ width: 100 }}
      popupMatchSelectWidth={false}
    />
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/components/LangSwitcher.tsx
git commit -m "feat(i18n): add LangSwitcher dropdown component"
```

---

### Task 9: format.ts utilities

**Files:**
- Create: `web/src/utils/format.ts`

- [ ] **Step 1: Create format utilities**

```typescript
export function formatDateTime(date: string | Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(date))
}

export function formatPrice(cents: number | null, locale: string): string {
  if (cents == null) return '-'
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'USD',
  }).format(cents / 100)
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/utils/format.ts
git commit -m "feat(i18n): add locale-aware formatDateTime and formatPrice utilities"
```

---

### Task 10: Update shared components (StatusBadge, EmptyState, StatsCard)

**Files:**
- Modify: `web/src/components/StatusBadge.tsx` (19 lines)
- Modify: `web/src/components/EmptyState.tsx` (16 lines)
- Modify: `web/src/components/StatsCard.tsx` (20 lines)

- [ ] **Step 1: Update StatusBadge**

Add `useTranslation` and translate the displayed status text:

```typescript
import { useTranslation } from 'react-i18next'
// In component body:
const { t } = useTranslation()
// Change: <Tag ...>{status}</Tag>
// To:     <Tag ...>{t(`status.${status}`, status)}</Tag>
```

- [ ] **Step 2: Update EmptyState**

Remove hardcoded default, use `t()`:

```typescript
import { useTranslation } from 'react-i18next'
export default function EmptyState({ description }: { description?: string }) {
  const { t } = useTranslation()
  return <Empty description={description ?? t('common.noData')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
}
```

- [ ] **Step 3: Update StatsCard**

Replace `+{today} today` with `t('stats.today', { count: today })`.

- [ ] **Step 4: Verify build**

```bash
cd /Users/victor/claudecode/cps/web && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add web/src/components/StatusBadge.tsx web/src/components/EmptyState.tsx web/src/components/StatsCard.tsx
git commit -m "feat(i18n): translate StatusBadge, EmptyState, StatsCard components"
```

---

## Chunk 4: Page-by-page i18n (Tasks 11-18)

For each page: add `const { t } = useTranslation()` at component top, replace ALL hardcoded strings with `t('key')` calls. Use `formatDateTime` and `formatPrice` where applicable.

### Task 11: Login page + LangSwitcher

**Files:**
- Modify: `web/src/pages/Login.tsx` (90 lines)

- [ ] **Step 1: Add imports and useTranslation**
- [ ] **Step 2: Add LangSwitcher at top-right (absolute positioned)**
- [ ] **Step 3: Replace translatable strings** (6 strings at lines 24, 56, 60, 66, 70, 82 — note: "CPS Admin" at line 43 is a brand name and is NOT translated per spec)
- [ ] **Step 4: Add syncAfterLogin call after successful login**
- [ ] **Step 5: Verify build + commit**

```bash
git commit -m "feat(i18n): translate Login page + add language switcher"
```

---

### Task 12: AdminLayout + LangSwitcher in topbar

**Files:**
- Modify: `web/src/layouts/AdminLayout.tsx` (76 lines)

- [ ] **Step 1: Move menuItems inside component, use t() for labels** (lines 20-24)
- [ ] **Step 2: Add LangSwitcher to header right section** (next to username/logout)
- [ ] **Step 3: Replace "CPS Admin" brand — keep as-is (non-translated)**
- [ ] **Step 4: Verify build + commit**

```bash
git commit -m "feat(i18n): translate AdminLayout menu items + add topbar language switcher"
```

---

### Task 13: Dashboard page

**Files:**
- Modify: `web/src/pages/Dashboard.tsx` (154 lines)

- [ ] **Step 1: Add useTranslation + import formatDateTime**
- [ ] **Step 2: Replace all strings** (~18 strings at lines 45, 55, 60, 67, 74, 82, 88, 93, 98, 114, 123, 129, 136-145)
- [ ] **Step 3: Update ECharts series name** (line 45: `'Completed'` → `t('dashboard.seriesCompleted')`)
- [ ] **Step 4: Replace toLocaleString calls with formatDateTime**
- [ ] **Step 5: Verify build + commit**

```bash
git commit -m "feat(i18n): translate Dashboard page"
```

---

### Task 14: Products page

**Files:**
- Modify: `web/src/pages/Products.tsx` (295 lines)

- [ ] **Step 1: Add useTranslation + import formatPrice, formatDateTime**
- [ ] **Step 2: Replace all strings** (~45 strings across page title, search, filters, buttons, messages, table columns, modal)
- [ ] **Step 3: Update formatPrice calls** (replace inline `$${(cents/100).toFixed(2)}` with `formatPrice(cents, i18n.language)`)
- [ ] **Step 4: Use status.* keys for filter options** (lines 129-130)
- [ ] **Step 5: Use products.category.* keys for category filter** (lines 144-150)
- [ ] **Step 6: Verify build + commit**

```bash
git commit -m "feat(i18n): translate Products page + locale-aware price formatting"
```

---

### Task 15: Crawler page

**Files:**
- Modify: `web/src/pages/Crawler.tsx` (261 lines)

- [ ] **Step 1: Add useTranslation + import formatDateTime**
- [ ] **Step 2: Replace all strings** (~35 strings)
- [ ] **Step 3: Replace `Task #${id}` with `t('crawler.currentTask', { id })`**
- [ ] **Step 4: Translate tab labels** (lines 176-179)
- [ ] **Step 5: Replace toLocaleString/toLocaleTimeString with formatDateTime**
- [ ] **Step 6: Verify build + commit**

```bash
git commit -m "feat(i18n): translate Crawler page"
```

---

### Task 16: Imports page

**Files:**
- Modify: `web/src/pages/Imports.tsx` (64 lines)

- [ ] **Step 1: Add useTranslation + import formatDateTime**
- [ ] **Step 2: Replace all strings** (~8 strings at lines 21, 29, 31, 44-48, 54)
- [ ] **Step 3: Replace toLocaleString with formatDateTime**
- [ ] **Step 4: Verify build + commit**

```bash
git commit -m "feat(i18n): translate Imports page"
```

---

### Task 17: Audit page

**Files:**
- Modify: `web/src/pages/Audit.tsx` (121 lines)

- [ ] **Step 1: Add useTranslation + import formatDateTime**
- [ ] **Step 2: Replace all strings** (~28 strings)
- [ ] **Step 3: Use audit.action_* keys for action filter options** (lines 50-57, add update_locale)
- [ ] **Step 4: Use audit.resource_* keys for resource type filter** (lines 71-74)
- [ ] **Step 5: Replace toLocaleString with formatDateTime**
- [ ] **Step 6: Verify build + commit**

```bash
git commit -m "feat(i18n): translate Audit page + add update_locale to action filter"
```

---

### Task 18: ProductDrawer + PriceChart

**Files:**
- Modify: `web/src/components/ProductDrawer.tsx` (116 lines)
- Modify: `web/src/components/PriceChart.tsx` (54 lines)

- [ ] **Step 1: Update ProductDrawer** — replace ~18 strings (tabs, table columns, description labels, status text), use `formatPrice` and `formatDateTime`
- [ ] **Step 2: Update PriceChart** — translate legend labels using `t('chart.*')`, replace `'No price data'` with `t('chart.noData')`, replace yAxis formatter with `formatPrice`
- [ ] **Step 3: Verify build + commit**

```bash
git commit -m "feat(i18n): translate ProductDrawer and PriceChart components"
```

---

## Chunk 5: Verification (Tasks 19-20)

### Task 19: Build + test

- [ ] **Step 1: Run frontend build**

```bash
cd /Users/victor/claudecode/cps/web && npm run build
```
Expected: Build succeeds, no errors

- [ ] **Step 2: Run backend tests**

```bash
source .venv/bin/activate && python -m pytest tests/ -x -q
```
Expected: All tests pass

- [ ] **Step 3: Start API and smoke test**

```bash
source .venv/bin/activate && cps api run
```

Open http://localhost:8000/ — verify:
1. Login page shows in Chinese (default)
2. Language switcher in top-right works
3. Switch to English → all text changes
4. Switch to Spanish → all text changes
5. Login → language persists
6. Dashboard, Products, Crawler, Imports, Audit — all translated
7. Table pagination shows in current language (Ant Design locale)
8. Dates and prices format correctly per locale

- [ ] **Step 4: Verify build output exists**

Note: `web/dist/` is in `.gitignore` — do NOT commit build output. The build artifacts are served directly from disk by the API server.

---

### Task 20: Final commit + cleanup

- [ ] **Step 1: Run full test suite one more time**

```bash
source .venv/bin/activate && python -m pytest tests/ -q
```

- [ ] **Step 2: Verify coverage**

```bash
source .venv/bin/activate && python -m pytest tests/ --cov=cps --cov-report=term-missing -q 2>&1 | tail -5
```
Expected: >= 80% coverage

- [ ] **Step 3: Final commit if any remaining changes**

```bash
git status
```
