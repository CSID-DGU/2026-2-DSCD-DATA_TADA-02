FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 APP_ENV=production SEED_ON_START=false
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home service
COPY backend/ ./backend/
COPY data/catalog/commercial_areas.json ./data/catalog/commercial_areas.json
COPY data/demo/snapshots.json ./data/demo/snapshots.json
COPY data/certificates/supabase-ca.crt ./data/certificates/supabase-ca.crt
COPY scripts/import_demo.py scripts/start_container.py ./scripts/
COPY --from=web /web/dist ./frontend/dist/
RUN mkdir -p /app/tmp && chown -R service:service /app/tmp
USER service
EXPOSE 8080
CMD ["python", "scripts/start_container.py"]
