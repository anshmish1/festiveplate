FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
RUN useradd --create-home --uid 10001 appuser && mkdir -p /app/uploads && chown -R appuser /app
USER appuser
EXPOSE 8000
# Apply migrations, seed demo data (idempotent; disable with SEED_DEMO_DATA=false), then serve.
CMD ["sh", "-c", "alembic upgrade head && if [ \"${SEED_DEMO_DATA:-true}\" = \"true\" ]; then python -m app.seed; fi && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
