#!/bin/bash
set -e
export NVM_DIR="$HOME/.nvm"
if [ -s "$NVM_DIR/nvm.sh" ]; then
  . "$NVM_DIR/nvm.sh"
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "NODE=$(node -v 2>/dev/null || echo missing) NPM=$(npm -v 2>/dev/null || echo missing)"
npm run build
echo "BUILD_EXIT=$?"
