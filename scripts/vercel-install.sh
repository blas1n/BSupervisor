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
  # The .npmrc references ${NPM_TOKEN}; the read fails harmlessly on Vercel
  # without the secret because we only consume packages from the workspace
  # itself, not from the GitHub Package Registry. Strip the registry directive
  # to silence the warnings and avoid any auth attempt.
  if [ -f .npmrc ]; then
    grep -v 'NPM_TOKEN\|@bsvibe:registry\|//npm.pkg.github.com' .npmrc > .npmrc.clean || true
    mv .npmrc.clean .npmrc
  fi
  npx --yes pnpm@10 install --frozen-lockfile || npx --yes pnpm@10 install --no-frozen-lockfile
  # Build serially because @bsvibe/auth, @bsvibe/api etc depend on @bsvibe/types.
  # --parallel races the dependent packages before types' dist exists.
  npx --yes pnpm@10 -r run build
)

echo "[vercel-install] Removing @bsvibe/* deps from frontend package.json (will install via direct copy)"
node -e "
const fs = require('fs');
const path = require('path');
const pkgPath = path.join('$REPO_ROOT', 'frontend', 'package.json');
const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
const removed = [];
for (const key of ['dependencies', 'devDependencies']) {
  const deps = pkg[key] || {};
  for (const name of Object.keys(deps)) {
    if (name.startsWith('@bsvibe/')) {
      removed.push(name);
      delete deps[name];
    }
  }
}
fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n');
console.log('Removed @bsvibe/* deps:', removed.join(', '));
"

echo "[vercel-install] Running npm install in frontend/"
cd "$REPO_ROOT/frontend"
# Build cache may carry stale node_modules with workspace:* refs from a
# previous failed build — clean out everything before the fresh install.
rm -rf node_modules package-lock.json .next
# Vercel's runner has a user .npmrc with pnpm-only options
# (auto-install-peers, strict-peer-dependencies) that npm 10 mis-parses
# and then crashes with "Cannot read properties of null (reading 'matches')"
# on file: deps. Force npm to ignore the user config by pointing
# --userconfig at an empty file we control.
EMPTY_NPMRC="$(mktemp)"
: > "$EMPTY_NPMRC"
cat > .npmrc <<'EOF'
audit=false
fund=false
EOF
npm --userconfig="$EMPTY_NPMRC" install --no-audit --no-fund
rm -f "$EMPTY_NPMRC"

echo "[vercel-install] Copying built @bsvibe/* packages into frontend/node_modules/"
mkdir -p node_modules/@bsvibe
for pkg_dir in "$REPO_ROOT/.bsvibe-frontend-lib/packages"/*/; do
  pkg_name=$(basename "$pkg_dir")
  target_dir="node_modules/@bsvibe/$pkg_name"
  rm -rf "$target_dir"
  mkdir -p "$target_dir"
  # Copy everything declared in package.json's "files" field (dist + any
  # additional asset dirs like styles/, tools/) plus README, LICENSE so
  # subpath exports such as @bsvibe/design-tokens/css resolve correctly.
  node -e "
const fs = require('fs');
const path = require('path');
const src = JSON.parse(fs.readFileSync('$pkg_dir/package.json', 'utf8'));
const files = (src.files && src.files.length) ? src.files : ['dist'];
for (const f of files) {
  const from = path.join('$pkg_dir', f);
  const to = path.join('$target_dir', f);
  if (fs.existsSync(from)) {
    fs.cpSync(from, to, { recursive: true });
  }
}
for (const f of ['README.md', 'LICENSE']) {
  const from = path.join('$pkg_dir', f);
  const to = path.join('$target_dir', f);
  if (fs.existsSync(from)) fs.cpSync(from, to);
}
for (const k of ['dependencies', 'devDependencies', 'peerDependencies']) {
  const deps = src[k] || {};
  for (const name of Object.keys(deps)) {
    if (typeof deps[name] === 'string' && deps[name].startsWith('workspace:')) {
      // npm cannot interpret workspace: protocol outside a workspace.
      // Replace with '*' since the dist/ output already has paths resolved.
      deps[name] = '*';
    }
  }
}
delete src.devDependencies;
fs.writeFileSync(path.join('$target_dir', 'package.json'), JSON.stringify(src, null, 2) + '\n');
"
done

echo "[vercel-install] Done."
