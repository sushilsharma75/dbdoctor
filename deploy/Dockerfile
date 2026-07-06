# dbdoctor api/worker image (one image, two roles — architecture §6)
FROM python:3.12-slim

WORKDIR /app

# chromium for PDF rendering
COPY pyproject.toml README.md ./
COPY engine ./engine
COPY report ./report
COPY collector ./collector
COPY cli ./cli
COPY webapp ./webapp
RUN pip install --no-cache-dir . \
    && playwright install --with-deps chromium

ENV DBDOCTOR_DATA_DIR=/data
VOLUME ["/data"]

EXPOSE 8000
CMD ["uvicorn", "webapp.backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
