FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY sql ./sql
EXPOSE 8000
# Migrations are tracked in schema_migrations, so running them on every start is safe.
CMD ["sh", "-c", "python -m app.db.migrate && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
