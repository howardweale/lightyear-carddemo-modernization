FROM python:3.13-slim
WORKDIR /workspace
RUN python -m pip install --no-cache-dir 'psycopg[binary]==3.2.10'
COPY src /workspace/src
COPY spec/modernization/carddemo-data /workspace/spec/modernization/carddemo-data
ENV PYTHONPATH=/workspace/src PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python", "-m", "lightyear_data.carddemo"]
