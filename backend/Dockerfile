# Build context is the repo root (see docker-compose.yml) so the image can
# carry backend/ and scripts/ (seed events) together.
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
# CPU-only torch keeps this image small (the default index pulls the large
# CUDA build). The MI300X droplet ignores this image and uses the ROCm torch
# from the vLLM base image with the backend on the host — see DEPLOY.md.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt
COPY backend /app/backend
COPY scripts /app/scripts
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
