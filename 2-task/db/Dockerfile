FROM mysql:latest

ARG MAIN_ADMIN

COPY . /db

WORKDIR /db

RUN sed -i "s/MAIN_ADMIN_ID/${MAIN_ADMIN}/g" /db/init.sql

RUN mv /db/init.sql /docker-entrypoint-initdb.d/init.sql