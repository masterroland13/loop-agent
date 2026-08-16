#!/bin/bash
set -e
cd "/home/caapap/agent window"
echo "building frontend..."
npm run build
echo "restarting preview if any..."
pkill -f "preview-server" 2>/dev/null || true
pkill -f "vite preview" 2>/dev/null || true
# Prefer vite preview on 5173 so localhost:5173 serves fresh build
nohup npx --yes vite preview --host 0.0.0.0 --port 5173 > /tmp/hal-agent-preview.log 2>&1 &
sleep 2
echo "--- preview log ---"
head -40 /tmp/agent-window-preview.log || true
curl -s -o /dev/null -w "http=%{http_code}\n" http://127.0.0.1:5173/ || true
