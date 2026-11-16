# Roadmap: "Aurora Glass" — next-phase design & engineering plan

Light mode is the **primary** theme; dark is a first-class sibling. Every item below states *what*, *how*, the *exact parameters*,
and *how it is verified*. Items marked **[Phase A]** are built and tested in this repo now; the rest are sequenced with
acceptance criteria. Anything that cannot be done honestly in this stack is called out.

---------------------------------------------------------------------------------------------------------------------------------

## 0. Ground truth (so the plan is credible)

| Area | Reality in this stack (NiceGUI 2.9 = Python + Vue/Quasar + ECharts, local-first) |
|---|---|
| Haptics | Vibration API exists on Android/Chromium only. **iOS Safari has no haptics API.** Implemented as progressive enhancement. |
| Vector motion libraries | Lottie/Rive CDNs are outside the sandbox allow-list. Use the **Web Animations API + SVG** (zero dependency); vendored Lottie JSON is an optional later step. |
| "Real-time data" | All market data is **simulated** (seeded). "Real-time" = websocket push + optimistic UI, and a pluggable feed adapter. No live market feed is claimed. |
| Palette from media | Works on **user-supplied images** (logo/photo) via client-side canvas; there are no bundled media assets to extract from. |
| Native window | Verified in `--web` mode only (no display server for pywebview here). |
| Persistence | `/home/claude` was wiped once; **deliverables are zipped to `/mnt/user-data/outputs` after every step**. |

---------------------------------------------------------------------------------------------------------------------------------

## 1. Design system (tokens first, components second)

### 1.1 Token layers  **[Phase A]**
`ui/theme.py` is the single source of truth. Three layers, emitted as CSS custom properties:

1. **Primitives** (`Palette` dataclass, hex): `bg_app, bg_panel, bg_panel_raised, text_primary/secondary/muted, profit_green, loss_red, accent_blue/violet/amber`.
2. **Semantic/surface tokens** (`theme_extras(base)`): `--glass-bg, --glass-bg-strong, --glass-soft, --glass-border, --glass-blur, --glass-inset, --shadow-sm/md/lg, --ambient, --focus, --skeleton-a/b`.
3. **Scale tokens** (`TOKENS`): radii `8/12/18/999`, motion `120/220/420ms` + `cubic-bezier(.2,.8,.2,1)`, spacing `4·8·12·16·24·32` (4-pt grid), type `11/13/15/18/24`.

Switching theme = `document.documentElement.style.setProperty(...)` for ~40 variables; no re-render, no flash. Charts (canvas) receive the hex `Palette` explicitly.

### 1.2 Light-mode surface recipe (exact)
| Token | Light | Dark |
|---|---|---|
| App canvas | `#F3F5F9` + 3 radial "ambient light" blooms (blue `.22`, violet `.18`, mint `.13`) | `#010203` + 2 faint blooms (`.10`, `.08`) |
| Glass panel | `rgba(255,255,255,.68)`, `blur(18px) saturate(1.5)`, 1px `rgba(255,255,255,.9)` border, inset top highlight `rgba(255,255,255,.95)` | `rgba(18,21,28,.72)`, `blur(16px) saturate(1.3)`, border `rgba(255,255,255,.07)` |
| Elevation md | `0 1px 2px rgba(15,23,42,.05), 0 12px 32px -14px rgba(30,64,175,.22)` (blue-tinted shadow = ambient light, not grey mud) | `0 1px 2px #0008, 0 14px 34px -16px #000e` |
| Radius | cards 18, tiles 12, controls 8, pills 999 | same |
| Type | system UI stack, **tabular numerals** for every number, labels `11px / .06em / 600` | same |
| Focus ring | `2px #1B5FE2`, offset 2px (never removed) | `2px #7FB0FF` |

### 1.3 Accessibility is a token property, not a polish step  **[Phase A]**
* WCAG 2.x **AA (4.5:1)** enforced by `tests/test_contrast.py` for *every* text/accent token × both themes × every color scheme × every surface (incl. the strongest light ambient tint).
* `ensure_contrast()` auto-corrects user-picked or image-extracted colors (keeps hue, shifts lightness).
* First audit found real failures (light profit-green `3.4:1`, muted `3.8:1`, amber `3.2:1`) → fixed at token level.
* Reduced motion (`prefers-reduced-motion`), high contrast (`prefers-contrast: more`), no-backdrop-filter fallback, skip link, `aria-label` auto-labelling of icon-only buttons, `aria-current` on nav, chart `aria-label` summaries, 40px minimum touch targets on coarse pointers (44px target for primary actions).

### 1.4 Component hierarchy (modular, each testable in isolation)
```
Shell (rail/bottom-nav, topbar, banners, dialogs)
 └─ Section (OCP | FCO | PM)          # owns its state object; implements on_show/on_prefs_changed/on_mode_changed/on_user_changed
     ├─ Controls panel (Glass)         # created once, never rebuilt (keeps drag/focus alive)
     ├─ Chart card (ECharts, compact on phones)
     ├─ Pair row  [Insight card | Positions]   [Greek table | Payoff metrics table]   # grid 3:2 / 1:1, stacks <768px
     └─ Tables (pure HTML builders: pm_tables, ocp_tables)  # unit-tested, escape all user text
Primitives: stat_tile, insight_list, leg_chip, kv_table, skeleton, toast, switcher
```

---------------------------------------------------------------------------------------------------------------------------------

## 2. Architecture decisions

### 2.1 Layers
`engine/` (pure math, no I/O) → `engine/store.py` (SQLite, per-user scoping) → `ui/` (presentation only). `ui` never computes finance; `engine` never imports `ui`.

### 2.2 State management
* One `AppState`/page object per section; `Prefs` (serialisable) for look & behaviour; **`refresh()` updates in place** — static controls are never destroyed (a rebuild mid-drag breaks sliders: learned, tested).
* Guard flag (`syncing`) so programmatic value changes never trigger user handlers.
* Section lifecycle hooks are duck-typed (`on_show`, `on_prefs_changed`, …) so new sections plug in without shell changes.

### 2.3 Optimistic UI pattern  **[Phase A]**
```
command(mutation, rollback, persist):
    mutation()            # 1. apply to in-memory state
    refresh()             # 2. UI reflects it immediately (< 1 frame)
    try: persist()        # 3. write (SQLite now; network later)
    except: rollback(); refresh(); toast("Couldn't save — restored")   # 4. reconcile
```
Used for add / remove / merge lots in Portfolio. Test injects a failing store and asserts rollback + toast.

### 2.4 Caching & prefetch  **[Phase A]**
* `lru_cache` for `MarketSimulator` per ticker; memoised `compute()` keyed by a frozen state tuple (skip recompute when only a label changes).
* **Idle prefetch:** after first paint, build the other sections hidden (`ui.timer(once)`), so switching is instant; charts `resize()` on show.
* Static assets are content-hashed and served with long-lived cache headers by NiceGUI; fonts = system stack (no blocking webfont).
* Later: service worker (cache-first shell, network-first data) + web app manifest ⇒ installable PWA, true offline shell.

### 2.5 Real-time (honest)
NiceGUI is already a persistent websocket. Add a `FeedAdapter` protocol (`subscribe(ticker) -> async iterator[Tick]`) with a **seeded random-walk simulator** implementation and a clearly-labelled place to plug a licensed feed later. Optimistic UI + ticks coalesced to 4 Hz to protect the main thread.

### 2.6 Loading, empty, offline  **[Phase A]**
* **Skeletons** (shimmer `1.4s`, `400%` gradient) while a section builds; layout reserved to avoid CLS.
* **Empty states** with a primary action ("Load sample").
* **Offline pill** (online/offline events) + auto-reconnect copy; local-first data means saved work survives.

---------------------------------------------------------------------------------------------------------------------------------

## 3. Motion & feel

| Moment | Technique | Parameters |
|---|---|---|
| Section change | Web Animations (`secEnter`) | `opacity 0→1`, `translateY 10→0`, `420ms`, ease-out-expo |
| Page swipe (Stocks↔Options) | touch gesture + `pmSlide` | threshold `70px`, `|dx| > 1.6|dy|`, `260ms` |
| Payoff preview | client-side sweep driving 3 hidden ECharts series | `2.2–2.4s`, cubic-out; green/red glow trail by sign; skipped when reduced-motion |
| Press / hover | CSS transform | press `scale(.96)` in `120ms`; tiles lift `-2px` + elevation md |
| Numbers | tabular-nums (no layout jitter on update) | — |
| Haptics | `navigator.vibrate(8)` on touch press (nav/toggle/buttons) | user toggle; Android/Chromium only |
| Later | FLIP layout transitions for list reorder; `document.startViewTransition` for section swaps; SVG path-draw for the logo/empty states | each behind `prefers-reduced-motion` |

---------------------------------------------------------------------------------------------------------------------------------

## 4. Dynamic palette from media  **[Phase A]**
1. User picks an image → draw to a **64×64 canvas** (client side; the image never leaves the device).
2. **Median-cut** quantisation → 8 candidates; score `= chroma × √population`, reject near-grey and extreme lightness.
3. Pick the best as `accent`; derive tonal steps by lightness (`±12%`) for hover/active/container tokens.
4. Run `ensure_contrast(accent, [panel, canvas, ambient-worst], 4.5)` (Python, unit-tested) — a pastel photo can never yield unreadable text.
5. Save as a *Custom* scheme in the user's **named UI template**.

---------------------------------------------------------------------------------------------------------------------------------

## 5. Step-by-step plan

**Phase A — foundation + light-mode polish (this repo, tested)**
1. Tokens + `theme_extras` + contrast tests (AA) ✔ design
2. Aurora CSS: glass, ambient light, layered shadows, micro-interactions, focus, reduced-motion/contrast, skeleton, offline pill
3. Haptics, section transition, aria auto-labelling, skip link
4. Idle prefetch + memoised compute; optimistic Portfolio writes
5. Palette-from-image (JS extractor + Python contrast fixer)
6. Light-mode screenshots **phone → tablet → laptop**; Playwright matrix (overflow, touch targets, dialogs); axe-core audit

**Phase B — product depth**
7. Inline sparkline + delta micro-charts in Portfolio rows; FLIP reorder on sort.
8. Strategy "compare" overlay (two payoff curves, shared hover).
9. Scenario cards (saved what-ifs) and shareable read-only links (signed, local).

**Phase C — platform**
10. PWA (manifest, icons, service worker, offline shell) → installable on iOS/Android home screen.
11. `FeedAdapter` + simulator ticks (4 Hz coalesced) with optimistic reconciliation.
12. Background sync queue for writes when the server is unreachable.

**Phase D — hardening**
13. Visual-regression suite (per device × theme), Lighthouse budgets (LCP < 2.0 s, TBT < 150 ms, CLS < 0.05), axe in CI, i18n/RTL pass, number/date locale formatting.

### Definition of done for every item
Unit tests for logic · Playwright check for behaviour · screenshot reviewed in **light and dark** at **phone, tablet, laptop** · AA contrast test green · no console errors.

---------------------------------------------------------------------------------------------------------------------------------

## 6. Quality gates (automated)
| Gate | Tool | Threshold |
|---|---|---|
| Contrast | `tests/test_contrast.py` | ≥ 4.5:1 all tokens/schemes |
| Overflow / layout | `scripts/check_responsive.py` | no horizontal overflow, 7 device profiles |
| Touch targets | same | ≥ 36px (coarse pointers) |
| Behaviour | `scripts/check_*.py` | real mouse/touch events |
| Logic | `pytest` | all green |
