ARG POSTGRES_IMAGE
FROM ${POSTGRES_IMAGE}
ARG POSTGRES_IMAGE

# The restore drill may use this locally reviewed image only when Docker no
# longer retains metadata for the exact image of the still-running container.
LABEL com.pcep.restore-profile="pcep-postgres-16-v1" \
      org.opencontainers.image.base.name="${POSTGRES_IMAGE}"

# Compose starts the image as postgres, so the root-only user switcher is unused.
# Removing it reduces attack surface and excludes its independently compiled Go
# runtime from the production image.
RUN rm /usr/local/bin/gosu

COPY init-app-role.sh /docker-entrypoint-initdb.d/10-pcep-app-role.sh

USER postgres
