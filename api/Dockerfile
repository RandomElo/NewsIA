FROM node:20-slim

WORKDIR /app

# Installe les dépendances séparément pour profiter du cache Docker
COPY api/package*.json ./
RUN npm ci --omit=dev

COPY api ./

EXPOSE 8100

CMD ["node", "serveur.js"]
