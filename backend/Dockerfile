FROM python:3.14.8-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS dependencies
ENV PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --require-hashes --only-binary=:all: \
    --wheel-dir /wheels -r requirements.txt

FROM python:3.14.8-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
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
