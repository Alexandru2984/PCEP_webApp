FROM python:3.12.15-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS dependencies
ENV PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --require-hashes --only-binary=:all: \
    --wheel-dir /wheels -r requirements.txt

FROM python:3.12.15-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ARG PCEP_RELEASE=development
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PCEP_RELEASE=${PCEP_RELEASE}
LABEL org.opencontainers.image.revision=${PCEP_RELEASE}
# The versioned upstream image can lag Debian security updates between rebuilds.
RUN apt-get update \
    && apt-get upgrade --yes \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=dependencies /wheels /wheels
COPY requirements.txt .
RUN pip install --require-hashes --no-index --find-links=/wheels \
    -r requirements.txt \
    && rm -rf /wheels \
    && adduser --disabled-password --gecos "" appuser
COPY --chown=appuser:appuser . .
RUN chmod +x /app/entrypoint.sh
USER appuser
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
