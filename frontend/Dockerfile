FROM node:24.22.0-alpine3.24@sha256:44fce696f38ba8c987c4db89954051000bbd05ffd8d8659ba15ed4a8602e937f
RUN apk add --no-cache bash curl
WORKDIR /app
RUN chown node:node /app
USER node
COPY --chown=node:node package*.json .npmrc ./
COPY --chown=node:node scripts/install-dependencies.sh scripts/check-install-scripts.mjs ./scripts/
RUN bash scripts/install-dependencies.sh
COPY --chown=node:node . .
CMD ["sh", "-c", "npm run fetch-pyodide && npm run build"]
