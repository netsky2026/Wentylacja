FROM node:20-alpine AS build
WORKDIR /src
COPY frontend/package.json deploy/frontend-yarn-lock.tx[t] ./
RUN if [ -f frontend-yarn-lock.txt ]; then mv frontend-yarn-lock.txt yarn.lock && yarn install --frozen-lockfile --network-timeout 600000; \
    else yarn install --network-timeout 600000; fi
COPY frontend/ .
RUN rm -f .env
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
ENV GENERATE_SOURCEMAP=false
RUN yarn build

FROM caddy:2-alpine
COPY --from=build /src/build /srv
