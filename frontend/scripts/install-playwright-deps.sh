#!/usr/bin/env bash
# Install Playwright browser dependencies without root access.
# Downloads .deb packages and extracts shared libraries to a local directory.
set -euo pipefail

LIBS_DIR="/tmp/playwright-libs"
DEBS_DIR="/tmp/playwright-deps"
APT_ROOT="/tmp/apt-root"
FONTCACHE="/tmp/fontconfig-cache"

if [ -f "$LIBS_DIR/.installed" ]; then
  exit 0
fi

mkdir -p "$DEBS_DIR" "$LIBS_DIR" "$FONTCACHE"
mkdir -p "$APT_ROOT/etc/apt" "$APT_ROOT/var/lib/apt/lists" "$APT_ROOT/var/cache/apt/archives/partial" "$APT_ROOT/var/lib/dpkg"
cp -r /etc/apt/* "$APT_ROOT/etc/apt/" 2>/dev/null || true
touch "$APT_ROOT/var/lib/dpkg/status"

apt-get -o Dir=/tmp/apt-root -o Dir::Etc="$APT_ROOT/etc/apt" -o Dir::State="$APT_ROOT/var/lib/apt" -o Dir::Cache="$APT_ROOT/var/cache/apt" update -qq 2>/dev/null || true

PACKAGES=(
  libglib2.0-0t64 libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64
  libgbm1 libasound2t64 libxrandr2 libxcomposite1 libxdamage1
  libdbus-1-3 libatspi2.0-0t64 libxfixes3 libxext6 libx11-6
  libxcb1 libxkbcommon0 libdrm2 libx11-xcb1 libpango-1.0-0
  libcairo2 libexpat1 libfontconfig1 libfreetype6 libpangocairo-1.0-0
  libpixman-1-0 libxcb-shm0 libxcb-render0 libxrender1
  libcups2t64 libxi6 libxau6 libxdmcp6
  libavahi-common3 libavahi-client3 libpng16-16t64
  libfribidi0 libthai0 libharfbuzz0b libdatrie1 libgraphite2-3
  fontconfig fonts-dejavu-core
)

cd "$DEBS_DIR"
for pkg in "${PACKAGES[@]}"; do
  apt-get -o Dir::Etc="$APT_ROOT/etc/apt" -o Dir::State="$APT_ROOT/var/lib/apt" -o Dir::Cache="$APT_ROOT/var/cache/apt" download "$pkg" 2>/dev/null || true
done

for deb in "$DEBS_DIR"/*.deb; do
  dpkg-deb -x "$deb" "$LIBS_DIR/" 2>/dev/null || true
done

# Create minimal fontconfig
cat > "$LIBS_DIR/etc/fonts/fonts.conf" << 'XMLEOF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <dir>/tmp/playwright-libs/usr/share/fonts</dir>
  <cachedir>/tmp/fontconfig-cache</cachedir>
  <config><rescan><int>30</int></rescan></config>
</fontconfig>
XMLEOF

touch "$LIBS_DIR/.installed"
echo "Playwright browser dependencies installed to $LIBS_DIR"
