#!/usr/bin/env bash
# Vercel install hook — vendor bsvibe-frontend-lib alongside, build it,
# then install BSupervisor frontend. Required because the frontend has
# `file:../../../bsvibe-frontend-lib/main/packages/*` deps which only
# work locally; on Vercel only this repo is cloned.
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
echo "[vercel-install] REPO_ROOT=$REPO_ROOT"

# Frontend file: dep relative path resolves to `<repo-root>/../../../bsvibe-frontend-lib/main/`
# from <repo-root>/frontend/, i.e. three levels up from frontend/ → /vercel/path0/../../../bsvibe-frontend-lib/main/
# On Vercel that's `/bsvibe-frontend-lib/main/` (root). We don't have write
# access to /. Instead we materialise it INSIDE the repo and update
# package.json file: paths to point there in-place.
LIB_DIR="$REPO_ROOT/.bsvibe-frontend-lib"
LIB_REPO="https://github.com/BSVibe/bsvibe-frontend-lib.git"
LIB_REF="${BSVIBE_FRONTEND_LIB_REF:-main}"

if [ ! -d "$LIB_DIR/.git" ]; then
  echo "[vercel-install] Cloning $LIB_REPO @ $LIB_REF → $LIB_DIR"
  git clone --depth=1 --branch "$LIB_REF" "$LIB_REPO" "$LIB_DIR"
else
  echo "[vercel-install] Reusing existing clone at $LIB_DIR"
  (cd "$LIB_DIR" && git fetch --depth=1 origin "$LIB_REF" && git checkout FETCH_HEAD) || true
fi

echo "[vercel-install] Building @bsvibe/* packages…"
(
  cd "$LIB_DIR"
  npx --yes pnpm@10 install --frozen-lockfile || npx --yes pnpm@10 install --no-frozen-lockfile
  npx --yes pnpm@10 -r --parallel run build
)

echo "[vercel-install] Rewriting frontend file: deps to point at .bsvibe-frontend-lib/packages/*"
node -e "
const fs = require('fs');
const path = require('path');
const pkgPath = path.join('$REPO_ROOT', 'frontend', 'package.json');
const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
let changed = false;
for (const key of ['dependencies', 'devDependencies']) {
  const deps = pkg[key] || {};
  for (const name of Object.keys(deps)) {
    const v = deps[name];
    if (typeof v === 'string' && v.startsWith('file:') && v.includes('bsvibe-frontend-lib/main/packages/')) {
      const m = v.match(/packages\/([^/]+)\/?$/);
      if (m) {
        deps[name] = 'file:../.bsvibe-frontend-lib/packages/' + m[1];
        changed = true;
      }
    }
  }
}
if (changed) {
  fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n');
  console.log('Updated', pkgPath);
}
"

echo "[vercel-install] Running npm install in frontend/"
cd "$REPO_ROOT/frontend"
# Lockfile expects old file: paths, so regenerate it.
rm -f package-lock.json
npm install --no-audit --no-fund

echo "[vercel-install] Done."
