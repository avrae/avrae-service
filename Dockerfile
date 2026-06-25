FROM dhi.io/python:3.14.6-alpine3.24-dev AS build

ARG ENVIRONMENT=production

RUN apk add --no-cache git

WORKDIR /app

COPY requirements.txt .

RUN python -m venv /app/venv \
    && /app/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY . .

COPY docker/config-${ENVIRONMENT}.py config.py

RUN wget -O global-bundle.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem

FROM dhi.io/python:3.14.6-alpine3.24

WORKDIR /app

USER nonroot

COPY --from=build --chown=nonroot:nonroot /app /app

ENV PATH="/app/venv/bin:$PATH"

CMD ["ddtrace-run", "gunicorn", "--workers", "2", "--bind", "0:8000", "app:app"]