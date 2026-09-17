# Dockerfile for Node.js Express Salon Tool on Google Cloud Run
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    PORT=8080

# Install production dependencies
COPY package*.json ./
RUN npm ci --only=production

# Copy application files
COPY . .

# Run as non-root user
USER node

EXPOSE 8080

CMD ["node", "server.js"]
