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

### Localhost & LAN Wi-Fi testing

Previews bind to `127.0.0.1` by default, which is the safe choice on public or
shared Wi-Fi. The startup card is pure ASCII:

```
+--[ web preview ]-----------------------------------------------+
directory:   /data/data/com.termux/files/home/myapp
local:       http://localhost:3000/
+----------------------------------------------------------------+
  Locked to localhost. To test from another device: wob preview --lan
  Secrets (.env, .git, keys) and directory listings are always blocked.
  Press Ctrl+C to stop.
```

To test from a laptop or tablet on the same Wi-Fi, opt in explicitly:

```bash
wob web preview --lan
```

Wobble detects the phone's LAN address, prints it, and warns that the files are
exposed to the local network:

```
network:     http://192.168.1.45:3000/
  [!] LAN exposure is ON: anyone on this Wi-Fi can read these files.
      Use 'wob preview' (without --lan) on public networks.
```

The same flag works for framework dev servers (`wob web dev --lan`,
`wob dev --lan`) and for the plain file server (`wob web serve --lan`).

Regardless of the bind address, the preview server refuses to serve:

- dotfiles and directories such as `.git`, `.env*`, `.npmrc`, `.netrc`;
- credential material such as `*.pem`, `*.key`, `*.jks`, `*.keystore`,
  `id_rsa*`, `local.properties`, `debug.keystore`;
- directory listings (an ASCII 404 card is returned instead);
- `..` traversal, percent-encoded traversal, and symlinks that escape the
  project root.

Text assets are gzip-compressed with a small in-memory cache, and HTTP/1.1
keep-alive is enabled so pages with many small assets load quickly.

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
