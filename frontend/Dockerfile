FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
ARG NEXT_PUBLIC_AUTH_URL=https://auth-production-dae4.up.railway.app
ARG NEXT_PUBLIC_GOALS_URL=https://goals-production-604f.up.railway.app
ARG NEXT_PUBLIC_AGENT_URL=https://agent-production-8568.up.railway.app
ARG NEXT_PUBLIC_APP_ENV=production
ARG NEXT_PUBLIC_REQUIRE_AUTH=true
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_AUTH_URL=$NEXT_PUBLIC_AUTH_URL \
    NEXT_PUBLIC_GOALS_URL=$NEXT_PUBLIC_GOALS_URL \
    NEXT_PUBLIC_AGENT_URL=$NEXT_PUBLIC_AGENT_URL \
    NEXT_PUBLIC_APP_ENV=$NEXT_PUBLIC_APP_ENV \
    NEXT_PUBLIC_REQUIRE_AUTH=$NEXT_PUBLIC_REQUIRE_AUTH
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ARG NEXT_PUBLIC_AUTH_URL=https://auth-production-dae4.up.railway.app
ARG NEXT_PUBLIC_GOALS_URL=https://goals-production-604f.up.railway.app
ARG NEXT_PUBLIC_AGENT_URL=https://agent-production-8568.up.railway.app
ARG NEXT_PUBLIC_APP_ENV=production
ARG NEXT_PUBLIC_REQUIRE_AUTH=true
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    NEXT_PUBLIC_AUTH_URL=$NEXT_PUBLIC_AUTH_URL \
    NEXT_PUBLIC_GOALS_URL=$NEXT_PUBLIC_GOALS_URL \
    NEXT_PUBLIC_AGENT_URL=$NEXT_PUBLIC_AGENT_URL \
    NEXT_PUBLIC_APP_ENV=$NEXT_PUBLIC_APP_ENV \
    NEXT_PUBLIC_REQUIRE_AUTH=$NEXT_PUBLIC_REQUIRE_AUTH
RUN addgroup -S arceus && adduser -S arceus -G arceus
COPY --from=build /app ./
USER arceus
EXPOSE 3000
CMD ["npm", "run", "start"]
