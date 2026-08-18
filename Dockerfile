# =====================================================================
# Multi-Stage Dockerfile — Pharma Analytics Platform
# Stage 1: Pipeline Builder (Generates synthetic dataset & ML models)
# Stage 2: Production Nginx Server (Serves web UI & exported JSON data)
# =====================================================================

# ── STAGE 1: BUILD DATA PIPELINE ──────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and master datasets
COPY data/ data/
COPY schema/ schema/
COPY src/ src/
COPY generate_dataset.py .
COPY data_preprocessing.py .
COPY analytics_engine.py .
COPY ml_models_suite.py .

# Run full backend data pipeline
RUN python generate_dataset.py && \
    python data_preprocessing.py && \
    python analytics_engine.py && \
    python ml_models_suite.py && \
    python src/export/build_dashboard_data.py

# ── STAGE 2: PRODUCTION SERVING ───────────────────────────────────────
FROM nginx:1.25-alpine AS final

# Copy static frontend assets and exported JSON dataset payloads
COPY --from=builder /app/dashboard/data /usr/share/nginx/html/dashboard/data
COPY --from=builder /app/schema /usr/share/nginx/html/schema
COPY index.html /usr/share/nginx/html/
COPY styles.css /usr/share/nginx/html/
COPY app.js /usr/share/nginx/html/
COPY js/ /usr/share/nginx/html/js/

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
