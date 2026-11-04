FROM node:24-alpine

WORKDIR /app

# package.json과 lock 파일을 먼저 복사한다. 코드만 바뀌면 설치 단계를 캐시로 건너뛴다
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_ 변수는 빌드할 때 코드에 들어간다. compose의 build.args로 받는다
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL

RUN npm run build

ENV NODE_ENV=production
CMD ["npm", "start"]
