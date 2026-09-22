FROM node:22-bookworm-slim AS frontend
WORKDIR /build/apps/frontend
COPY apps/frontend/package*.json ./
RUN npm ci
COPY apps/frontend/ ./
COPY resources/catalog/ /build/resources/catalog/
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    REALCENTER_DATA_ROOT=/app/data/tenants/default \
    REALCENTER_TENANTS_ROOT=/app/data/tenants \
    REALCENTER_ENV_ROOT=/app/data/platform \
    REALCENTER_RESOURCES_ROOT=/app/resources \
    REALCENTER_STATIC_ROOT=/app/apps/frontend/dist
WORKDIR /app
COPY apps/backend/ ./apps/backend/
COPY apps/frontend/src/ ./apps/frontend/src/
COPY resources/ ./resources/
COPY docs/ ./docs/
COPY scripts/ ./scripts/
COPY --from=frontend /build/apps/frontend/dist/ ./apps/frontend/dist/
RUN pip install --no-cache-dir ./apps/backend && useradd --create-home studio && mkdir -p data/tenants/default/campaigns data/tenants/default/brand data/platform && chown -R studio:studio /app
USER studio
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/config', timeout=3)" || exit 1
CMD ["python", "-m", "realcenter_marketing", "--host", "0.0.0.0"]

# Development image. The production stage installs the package normally, so the code runs
# from site-packages and syncing apps/backend/src into the container would change nothing.
# An editable install points site-packages back at the mounted source, which is what makes
# "edit a file, restart, see the change" work at all.
FROM runtime AS dev
USER root
RUN pip install --no-cache-dir -e ./apps/backend
USER studio
