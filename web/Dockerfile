# Friday web (Next.js 15) — container image.
FROM node:20-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-slim
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production
COPY --from=build /app ./
EXPOSE 3000
# FRIDAY_API (backend URL) is injected at runtime via compose.
CMD ["npm", "run", "start"]
