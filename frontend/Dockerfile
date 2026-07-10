FROM node:22-alpine AS build

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

ARG VITE_API_BASE_URL=/api/v1
ARG VITE_API_MODE=real
ARG VITE_DEV_AUTH_TOKEN=local-development-token
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_API_MODE=$VITE_API_MODE \
    VITE_DEV_AUTH_TOKEN=$VITE_DEV_AUTH_TOKEN

COPY . .
RUN pnpm build

FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
