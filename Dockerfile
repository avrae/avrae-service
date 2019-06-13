FROM python:3.6-stretch

ARG ENVIRONMENT=production

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

COPY docker/config-${ENVIRONMENT}.py config.py

ENTRYPOINT gunicorn --workers 2 --bind 0:8000 app:app
