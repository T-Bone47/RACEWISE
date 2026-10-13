FROM node:20-alpine

WORKDIR /app

COPY backend/package*.json ./
RUN npm ci --only=production

COPY backend/ ./

EXPOSE 3001
CMD ["node", "server.js"]