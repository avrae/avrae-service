FROM python:3.6-stretch

ARG ENVIRONMENT=production

RUN useradd --create-home avraeservice
USER avraeservice
WORKDIR /home/avraeservice

COPY --chown=avraeservice:avraeservice requirements.txt .
RUN pip install --user --no-warn-script-location -r requirements.txt

COPY --chown=avraeservice:avraeservice . .

COPY --chown=avraeservice:avraeservice docker/config-${ENVIRONMENT}.py config.py

# Download AWS pubkey to connect to documentDB
RUN if [ "$ENVIRONMENT" = "production" ]; then wget https://s3.amazonaws.com/rds-downloads/rds-combined-ca-bundle.pem; fi

ENTRYPOINT .local/bin/newrelic-admin run-program .local/bin/gunicorn --workers 2 --bind 0:8000 app:app
