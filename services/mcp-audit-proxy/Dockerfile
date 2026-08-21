FROM registry.access.redhat.com/ubi9/python-311:latest
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
# /data is where the sqlite queue.db lives (QUEUE_DB_PATH) -- pre-create it writable so
# the named volume Docker initializes from this inherits the same permissions, regardless
# of which non-root UID the base image runs as.
USER 0
RUN mkdir -p /data && chmod 777 /data
USER 1001
EXPOSE 8001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
