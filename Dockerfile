FROM docker.io/library/python:3.14-slim

ARG SERVICE
ENV SERVICE=${SERVICE} PYTHONPATH=/app/libs/events:/app/services/${SERVICE} DATABASE_PATH=/data/service.db

WORKDIR /app
COPY requirements/services.txt requirements/services.txt
RUN pip install --no-cache-dir -r requirements/services.txt
COPY libs/events libs/events
COPY services/${SERVICE} services/${SERVICE}
RUN mkdir -p /data

CMD ["sh", "-c", "uvicorn ${SERVICE}_service.main:app --host 0.0.0.0 --port 8000"]
