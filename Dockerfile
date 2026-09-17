FROM python:3.13-alpine
RUN adduser -D -u 10001 relay
WORKDIR /app
COPY app /app
RUN mkdir /data && chown relay:relay /data
USER relay
ENV DATA_DIR=/data PYTHONUNBUFFERED=1
EXPOSE 8090
CMD ["python", "server.py"]
