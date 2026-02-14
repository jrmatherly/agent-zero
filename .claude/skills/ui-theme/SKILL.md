---
name: ui-theme
description: >-
  This skill should be used when the user asks to "modify the UI theme",
  "change colors or typography", "add a new theme variant", "fix a styling issue",
  "update the welcome screen", "modify the sidebar", "add a CSS variable",
  "adjust glass effects", "work on the executive theme", "debug a visual bug",
  "update the preferences panel", or mentions design tokens, CSS custom properties, Alpine.js stores,
  component styling, dark/light mode, or the classic theme.
  Provides comprehensive knowledge of the Apollos AI executive theme system,
  component architecture, and UI conventions.
---

# UI Theme Expert — Apollos AI Executive Theme System

Comprehensive guide to the Apollos AI frontend UI and its dual-theme system (Executive gold/charcoal + Classic blue/gray). Covers design tokens, component architecture, Alpine.js store patterns, glass morphism effects, and responsive design.

## Architecture Overview

The UI is a vanilla JavaScript + Alpine.js single-page application rendered by Flask/Jinja2. There is no build step — all JS uses native ES modules loaded via `<script type="module">`.

### File Organization

```
webui/
├── css/
│   ├── tokens.css          ← Design tokens (SOURCE OF TRUTH for all colors/fonts)
│   ├── messages.css         ← Chat message styling (glass effects)
│   ├── modals.css           ← Modal dialogs (glass effects)
│   ├── buttons.css          ← Button styles
│   ├── settings.css         ← Settings panel
│   ├── tables.css           ← Data tables
│   ├── notification.css     ← Notification system
│   ├── toast.css            ← Toast messages
│   ├── speech.css           ← Speech UI
│   ├── scheduler.css        ← Scheduler views
│   └── scheduler-datepicker.css
├── index.css                ← Master stylesheet (imports tokens.css, utility classes, glass classes)
├── js/
│   ├── AlpineStore.js       ← Store factory (createStore, getStore, saveState, loadState)
│   ├── branding-store.js    ← Branding config from /branding_get API
│   ├── css.js               ← Dynamic CSS property toggles
│   └── ...                  ← Utilities (api, modals, scroller, shortcuts, etc.)
├── components/              ← Self-contained HTML components with embedded <style>
│   ├── welcome/             ← Welcome dashboard (clock, status, action cards)
│   ├── sidebar/             ← Left sidebar (hover-expand, pin, sections)
│   ├── chat/                ← Chat input, messages, speech, navigation
│   ├── messages/            ← Process groups, action buttons, resize
│   ├── modals/              ← File browser, history, memory, scheduler, etc.
│   ├── settings/            ← Agent, MCP, backup, developer, skills, tunnel
│   ├── notifications/       ← Toast + modal notifications
│   ├── projects/            ← Project CRUD
│   ├── sync/                ← WebSocket connection status
│   └── tooltips/            ← Tooltip system
├── vendor/
│   └── fonts/
│       ├── fonts.css              ← @font-face declarations (LOCAL, no CDN)
│       ├── inter-latin.woff2
│       ├── playfair-display-latin.woff2
│       ├── playfair-display-italic-latin.woff2
│       ├── work-sans-latin.woff2
│       └── jetbrains-mono-latin.woff2
└── public/
    ├── splash.svg           ← Brand logo (renders natively in dark mode)
    └── darkSymbol.svg       ← Background watermark
```

## Theme System

### Two Themes, Four Modes

The theme system uses two orthogonal axes:

1. **Theme**: `data-theme` attribute on `<body>` — `"executive"` (default) or `"classic"`
2. **Mode**: CSS class on `<body>` — `.dark-mode` (default) or `.light-mode`

This produces 4 combinations: executive-dark, executive-light, classic-dark, classic-light.

### Token Resolution (Critical Pattern)

In `tokens.css`, the executive dark-mode tokens are defined on `:root` with `-dark` suffixes. The master stylesheet (`index.css`) maps them to shorthand variables:

```css
/* index.css resolves dark-mode tokens to shorthands */
:root {
  --color-background: var(--color-background-dark);
  --color-highlight: var(--color-highlight-dark);
  /* ... etc */
}
```

**Important**: Theme overrides MUST use the shorthand variable names (e.g., `--color-highlight`), NOT the suffixed names (e.g., `--color-highlight-dark`). CSS custom properties resolve at declaration time, so overriding `-dark` variants in a `[data-theme]` selector has no effect on the already-resolved shorthands.

### Adding a New Theme

1. Add a new `[data-theme="name"]` block in `tokens.css` overriding ALL shorthand color variables
2. Add `[data-theme="name"].light-mode` for light-mode overrides
3. Disable glass effects if the theme doesn't use them (set `--color-glass-*` to `transparent`, add `backdrop-filter: none` rules)
4. Add the option to `themeOptions` array in `components/sidebar/bottom/preferences/preferences-store.js`
5. The `_applyTheme()` method handles persistence and DOM attribute

### Glass Morphism

Glass effects use `backdrop-filter: blur()` with semi-transparent backgrounds. Controlled by three CSS variables:

- `--color-glass-bg` — Panel backgrounds (e.g., `rgba(20, 21, 23, 0.6)`)
- `--color-glass-border` — Subtle gold-tinted borders
- `--color-glass-sidebar` — Sidebar-specific opacity

Glass utility classes in `index.css`:
- `.glass-panel` — Standard glass panel
- `.glass-sidebar` — Sidebar glass (higher opacity)

**Performance**: Glass effects are GPU-intensive. Classic theme disables them. `prefers-reduced-motion` media query also disables all `backdrop-filter` globally.

## Alpine.js Store Pattern

Every store follows this pattern:

```javascript
import { createStore } from "/js/AlpineStore.js";

const model = {
  someProperty: "default",
  init() { /* runs when Alpine initializes */ },
  someMethod() { /* business logic */ },
};

export const store = createStore("storeName", model);
```

Access in HTML templates: `$store.storeName.someProperty`

### Key Stores for Theming

| Store | File | Purpose |
|-------|------|---------|
| `preferences` | `sidebar/bottom/preferences/preferences-store.js` | Theme, dark mode, width, detail mode, speech, utils toggles |
| `sidebar` | `sidebar/sidebar-store.js` | Open/close, pin/unpin, hover-expand, section collapse |
| `branding` | `js/branding-store.js` | Brand name, accent color, URLs from API |
| `welcomeStore` | `welcome/welcome-store.js` | Clock, system status, action cards, banners |
| `sync` | `sync/sync-store.js` | WebSocket connection state |

### Preference Persistence Pattern

Preferences use getter/setter pairs with backing `_fields` and `_apply*` methods:

```javascript
get theme() { return this._theme; },
set theme(value) { this._theme = value; this._applyTheme(value); },
_theme: "executive",

_applyTheme(value) {
  document.body.setAttribute("data-theme", value);
  localStorage.setItem("theme", value);
},
```

The `init()` method loads from `localStorage` with validation against option arrays.

## Component Pattern

Components are self-contained `.html` files with embedded `<script type="module">` and `<style>`. Loaded via `<x-component path="...">` custom element.

```html
<html>
<head>
  <script type="module">
    import { store } from "/components/path/to/store.js";
  </script>
</head>
<body>
  <div x-data>
    <!-- Alpine.js template -->
  </div>
  <style>
    /* Scoped styles */
  </style>
</body>
</html>
```

## Typography & Fonts

All fonts are **vendored locally** for offline/Docker support. Never use Google Fonts CDN links.

**Font files**: `webui/vendor/fonts/` (`.woff2` variable fonts)
**Declarations**: `webui/vendor/fonts/fonts.css` (`@font-face` rules with `font-display: swap`)

| Font | CSS Variable | Usage | Weight Range |
|------|-------------|-------|-------------|
| Inter | `--font-family-main` | Body text, UI | 300–700 |
| Playfair Display | `--font-family-serif` | Headings, brand name, clock | 400–700 (+ italic) |
| Work Sans | `--font-family-display` | Display text, labels, buttons | 300–600 |
| JetBrains Mono | `--font-family-code` | Code blocks | 400–500 |

**Loading fonts in standalone pages** (e.g., `login.html` which is outside the SPA):
```html
<link rel="stylesheet" href="/vendor/fonts/fonts.css">
```

The main SPA (`index.html`) loads fonts via `index.css` which imports `tokens.css`. Standalone pages must load `fonts.css` explicitly since they don't use the SPA stylesheet chain.

## Responsive Breakpoints

- **768px**: Mobile breakpoint (sidebar becomes fixed overlay, grid collapses)
- **520px**: Small mobile (action cards stack vertically, status bar goes column)

## Additional Resources

### Reference Files

For detailed token values, color palettes, and component-specific styling:
- **`references/design-tokens.md`** — Complete token catalog with hex values across all 4 theme modes
- **`references/component-map.md`** — Full component tree with store dependencies and styling notes

## Common Tasks

### Fix a color/styling issue
1. Identify the CSS variable in use (inspect element or grep the component)
2. Check `tokens.css` for the variable definition across all theme modes
3. Verify the fix works in all 4 modes (exec-dark, exec-light, classic-dark, classic-light)

### Add a new preference toggle
1. Add getter/setter/backing field to `preferences-store.js`
2. Add `_apply*` method with `localStorage.setItem`
3. Add localStorage load in `init()` with validation
4. Add `_apply*` call in the init apply-all block
5. Add UI control in `preferences-panel.html`

### Add a new sidebar section
1. Add default state in `sidebar-store.js` `sectionStates` object
2. Use Bootstrap collapse + `x-effect` pattern from existing sections
3. Toggle via `$store.sidebar.toggleSection('name')`

### Logo rendering
- Dark mode: No filter (SVG renders with native colors)
- Light mode: `filter: invert(100%) grayscale(100%)`
- Never use `filter: invert()` in dark mode — it washes out the gold palette
