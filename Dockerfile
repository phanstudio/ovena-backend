# ---- Base image with GIS libraries ----
FROM carrycat/gis:latest

# Install Python + required system libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip \
    libdeflate0 liblerc4 libwebp7 libgeos-c1v5 \
    && rm -rf /var/lib/apt/lists/*

# ---- App directory ----
WORKDIR /app

# ---- Install Python dependencies ----
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# ---- Copy application code ----
COPY . .

# ---- Set GDAL/GEOS/PROJ paths ----
ENV GDAL_LIBRARY_PATH=/usr/lib/libgdal.so \
    GEOS_LIBRARY_PATH=/usr/lib/libgeos_c.so \
    PROJ_LIB=/usr/share/proj \
    PYTHONUNBUFFERED=1

# ---- Entrypoint ----
COPY entrypoint.sh /app/entrypoint.sh

# Make it executable
# RUN chmod +x /app/entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]

# ---- Default CMD: run Gunicorn ----
# CMD ["gunicorn", "-b", "0.0.0.0:8000", "core.wsgi:application", "--workers=4", "--threads=2", "--timeout=120"]
# ---- Start ASGI server ----
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "core.asgi:application"]
# CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
