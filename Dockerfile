FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x deploy/entrypoint.sh \
    && useradd --create-home --uid 1000 app \
    && mkdir -p /app/staticfiles \
    && chown -R app:app /app
USER app

EXPOSE 8000
ENTRYPOINT ["./deploy/entrypoint.sh"]
