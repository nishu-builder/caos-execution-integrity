FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r /requirements.txt
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
ENTRYPOINT ["python3", "/app/lab.py"]
