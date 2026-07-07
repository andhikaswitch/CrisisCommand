# Multi-stage: build the Vite bundle with Node, serve it with nginx.
# nginx also reverse-proxies /api and /ws to the backend service, so the
# browser talks to a single origin (VITE_API_BASE stays empty → same-origin).
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
