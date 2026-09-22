FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY playground ./playground
RUN pip install --no-cache-dir .
USER 65532:65532
EXPOSE 8075
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8075/health', timeout=3).read()"
CMD ["uvicorn", "playground.app:app", "--host", "0.0.0.0", "--port", "8075"]
