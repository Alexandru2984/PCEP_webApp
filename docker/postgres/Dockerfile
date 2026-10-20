FROM postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea

# The restore drill may use this locally reviewed image only when Docker no
# longer retains metadata for the exact image of the still-running container.
LABEL com.pcep.restore-profile="pcep-postgres-16-v1" \
      org.opencontainers.image.base.name="postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"

# Compose starts the image as postgres, so the root-only user switcher is unused.
# Removing it reduces attack surface and excludes its independently compiled Go
# runtime from the production image.
RUN rm /usr/local/bin/gosu

COPY init-app-role.sh /docker-entrypoint-initdb.d/10-pcep-app-role.sh

USER postgres
