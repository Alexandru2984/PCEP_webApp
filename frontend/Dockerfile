FROM node:24-alpine
RUN apk add --no-cache bash curl
WORKDIR /app
RUN chown node:node /app
USER node
COPY --chown=node:node package*.json ./
RUN npm ci
COPY --chown=node:node . .
CMD ["sh", "-c", "npm run fetch-pyodide && npm run build"]
