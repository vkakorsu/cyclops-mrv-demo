FROM ghcr.io/osgeo/gdal:ubuntu-small-latest

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3-pip && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY pipeline.py .

RUN mkdir -p /app/output

CMD ["python3", "pipeline.py"]
