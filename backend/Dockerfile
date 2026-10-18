# Preserve source tree paths expected by .parents[] references in OLYMPUS.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./backend/app
COPY olympus ./olympus
COPY vendor ./vendor
RUN mkdir -p /data && chown -R 10001:10001 /data /workspace
ENV PYTHONPATH=/workspace:/workspace/backend
ENV OLYMPUS_CLOUD_DATA_DIR=/data
ENV OLYMPUS_SKILLS_DIR=/data/skills
ENV OLYMPUS_MEMORY_DB=/data/memory.sqlite3
ENV OLYMPUS_SKILLS_FABRIC_STATE_DIR=/data/skills-fabric
WORKDIR /workspace/backend
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
