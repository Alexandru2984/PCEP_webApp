ARG NODE_IMAGE=node:24.21.0-alpine3.24@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1
FROM ${NODE_IMAGE}
RUN apk add --no-cache bash curl
WORKDIR /app
RUN chown node:node /app
USER node
COPY --chown=node:node package*.json .npmrc ./
RUN npm ci
COPY --chown=node:node . .
CMD ["sh", "-c", "npm run fetch-pyodide && npm run build"]
