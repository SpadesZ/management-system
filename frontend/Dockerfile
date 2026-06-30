# File Path: frontend/Dockerfile
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

FROM node:22-alpine

WORKDIR /app

COPY package.json /app/package.json
RUN npm install

COPY . /app

EXPOSE 5173

CMD ["npm", "run", "dev"]
