#!/usr/bin/env bash
# One command to bring CrisisCommand up on an AMD ROCm notebook/droplet.
#
#   bash scripts/notebook_bootstrap.sh              # deps + tests + benchmark + serve
#   bash scripts/notebook_bootstrap.sh --no-serve   # evidence only, then exit
#   bash scripts/notebook_bootstrap.sh --tunnel     # also expose a public URL
#
# Never installs torch: the ROCm image ships the correct build, and a plain
# `pip install torch` would silently replace it with the CUDA wheel and drop
# you back to CPU. That is the single most common way to lose the AMD story.
set -euo pipefail

cd "$(dirname "$0")/.."
SERVE=1
TUNNEL=0
PORT="${PORT:-8000}"
for arg in "$@"; do
  case "$arg" in
    --no-serve) SERVE=0 ;;
    --tunnel)   TUNNEL=1 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

echo "==> 1/5  Which GPU did we get?"
python - <<'PY'
import torch
from backend.device import device_label
if torch.cuda.is_available():
    print(f"    device: {device_label(0)}")
    print(f"    torch : {torch.__version__}  hip={getattr(torch.version, 'hip', None)}")
else:
    print("    WARNING: no GPU visible — the demo still runs, on CPU.")
PY

echo "==> 2/5  Backend deps (torch deliberately excluded)"
pip install -q -r requirements.txt

echo "==> 3/5  Tests"
python -m pytest -q

echo "==> 4/5  Evidence: CPU vs GPU benchmark -> evidence/benchmark.json"
# This artifact outlives the session. Capture it even if you do nothing else.
python scripts/benchmark.py --runs 10000 50000 100000

if [ -d frontend/dist ]; then
  echo "==> 5/5  Built SPA found; backend will serve UI + API + WS on one origin"
else
  echo "==> 5/5  No frontend/dist — API only. Build it where Node exists:"
  echo "         (cd frontend && npm install && npm run build), then commit dist."
fi

if [ "$SERVE" -eq 0 ]; then
  echo "done (--no-serve): evidence/benchmark.json is your AMD number."
  exit 0
fi

if [ "$TUNNEL" -eq 1 ] && [ ! -x ./cloudflared ]; then
  echo "==> fetching cloudflared"
  curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
  chmod +x cloudflared
fi

# Warn loudly before serving: a missing .env silently yields SEED mode + template
# briefings, which looks like a broken demo rather than a missing config file.
if [ ! -f .env ]; then
  echo "!!  no .env found -> SEED mode, template briefings (no live feeds, no AI)"
  echo "    create one with FIREWORKS_API_KEY and SEED_MODE=false, then rerun."
elif ! grep -q '^FIREWORKS_API_KEY=fw' .env 2>/dev/null; then
  echo "!!  .env has no FIREWORKS_API_KEY -> briefings will use the raw-data template"
fi
# main.py defaults SEED_MODE to "true" when unset — do not imply otherwise here.
echo "==> serving on :$PORT  (SEED_MODE=${SEED_MODE:-<unset -> true>})"
uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" &
UVICORN_PID=$!
trap 'kill $UVICORN_PID 2>/dev/null || true' EXIT

until curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null; do sleep 1; done
echo "    health OK; device: $(curl -s "http://127.0.0.1:$PORT/api/health/gpu")"

if [ "$TUNNEL" -eq 1 ]; then
  echo "==> public URL below. It is UNAUTHENTICATED — stop it after the demo."
  ./cloudflared tunnel --url "http://localhost:$PORT"
else
  echo "==> open http://localhost:$PORT (add --tunnel to reach it from a laptop)"
  wait $UVICORN_PID
fi
