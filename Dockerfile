FROM node:26-slim
WORKDIR /app
COPY src ./src
USER node
CMD ["node", "src/server.ts"]
