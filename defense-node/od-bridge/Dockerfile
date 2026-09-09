FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        nftables iproute2 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY od_bridge ./od_bridge

ENV PYTHONUNBUFFERED=1
EXPOSE 8500
CMD ["python", "-m", "od_bridge.main"]
