# Hugging Face Spaces (Docker SDK) deployment. This is the CPU, always-on
# public URL judges click; the AMD GPU demo lives in the video + benchmark.json.
# Serves the API, the WebSocket, AND the built SPA from one origin/port.
FROM python:3.11-slim
WORKDIR /app

# CPU-only torch (small; the ROCm notebook uses its own preinstalled build).
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# single-origin: the backend serves the built SPA (frontend/dist) too
COPY backend /app/backend
COPY scripts /app/scripts
COPY frontend/dist /app/frontend/dist
ENV PYTHONPATH=/app

# Bind to the platform's injected $PORT (Render, Koyeb, Cloud Run all set it);
# fall back to 7860 for local runs. Shell form so ${PORT} expands.
EXPOSE 7860
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860}
