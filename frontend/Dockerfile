# ---------------------------------------------------------------------------
# Build stage — compila o app React com Vite
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Copia manifesto de dependências primeiro (melhor uso do cache do Docker)
COPY package.json package-lock.json* ./
RUN npm ci

# Argumentos de build — variáveis VITE_ são injetadas em tempo de build
# e ficam embutidas no bundle JS gerado
ARG VITE_API_URL=http://localhost:8081
ARG VITE_APP_ENV=local
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_APP_ENV=$VITE_APP_ENV

# Copia o restante do código e gera o build de produção
COPY . .
RUN npm run build

# ---------------------------------------------------------------------------
# Runtime stage — serve os arquivos estáticos com Nginx
# ---------------------------------------------------------------------------
FROM nginx:alpine

# Copia o build gerado para o diretório padrão do Nginx
COPY --from=builder /app/dist /usr/share/nginx/html

# Configuração do Nginx: redireciona todas as rotas para o index.html
# necessário para roteamento client-side (React Router, etc.)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
