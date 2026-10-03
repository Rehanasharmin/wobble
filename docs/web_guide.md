# Web Development on Termux with Wobble

Wobble provides a unified workflow for modern web applications inside Termux.

---

## 1. Supported Stacks

- **Vite (Vanilla JS/TS)**: `wob create web myapp --framework vite`
- **React (Vite)**: `wob create web myreact --framework react`
- **Vue 3 (Vite)**: `wob create web myvue --framework vue`
- **Svelte (Vite)**: `wob create web mysvelte --framework svelte`
- **Next.js**: `wob create web mynext --framework nextjs`
- **Python Web (Flask / FastAPI)**: `wob create web myapi --framework python`
- **PHP**: `wob create web mysite --framework php`
- **Static HTML5/CSS3**: `wob create web mylanding --framework static`

---

## 2. Development & Live Preview

Inside any web project:
```bash
wob web preview
```
Or use the shortcut:
```bash
wob preview
```

### Localhost & LAN Wi-Fi Testing:
Wobble detects your phone's active Wi-Fi LAN address dynamically:
```
⚡ WOBBLE WEB PREVIEW RUNNING
➜ Local:    http://localhost:3000/
➜ Network:  http://192.168.1.45:3000/
```
You can preview the site directly in Chrome/Firefox on Android via `http://localhost:3000/`, or enter `http://192.168.1.45:3000/` into a browser on your laptop or tablet on the same Wi-Fi.

---

## 3. Dependency Management

- Install all project dependencies:
  ```bash
  wob deps install
  ```
- Add a library:
  ```bash
  wob deps add axios
  ```
- Remove a library:
  ```bash
  wob deps remove axios
  ```
- Check dependency health:
  ```bash
  wob deps doctor
  ```

---

## 4. Production Build

To build your web application for distribution:
```bash
wob web build
```
This triggers the framework's bundler (e.g. `vite build`, `next build`) and outputs optimized bundles to `dist/`, `build/`, or `out/`.
