Frontend Build (Optional: Vite)

Overview
- The backend ships with a lightweight Python static hasher (scripts/build_static.py). For richer bundling, you can use Vite.
- This project includes an optional Vite config under ./frontend that builds into payroll_portal/static/dist and generates a manifest.json compatible with resolve_static.

Usage
1) Install Node.js (LTS), then inside ./frontend run:
   - npm install
   - npm run build
2) The output goes to payroll_portal/static/dist with hashed filenames and dist/manifest.json.
3) The backend will automatically use the manifest via payroll_portal/utils/assets.py.

Docker
- The Dockerfile includes an optional Node build stage. If Vite produces `dist/manifest.json`, the runtime image copies those assets; otherwise the Python hasher builds fingerprints at image build time.

Inputs
- Configured inputs map to the existing static entry points:
  - app.js, init_csrf.js, i18n.js, portal_home.js, admin_withholding.js, runtime.js
  - styles.css
  - payroll/* (calc.js, dom.js, state.js, ui.js, utils.js)

Notes
- Vite manifest uses entry keys equal to the relative filenames above, matching the Python hasher mapping. This keeps templates unchanged.
- CI/Docker currently use scripts/build_static.py; switch to Vite by adding a Node builder stage and copying dist/ into the runtime image if desired.
