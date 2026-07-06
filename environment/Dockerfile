# Fully offline at runtime; stdlib-only Python and git
FROM python:3.11-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY build/ /opt/build/
RUN python3 /opt/build/generate_data.py /app \
 && bash /opt/build/make_repo.sh /app/repo \
 && python3 /opt/build/make_dashboard.py /app \
 && cp -r /app /opt/pristine \
 && rm -rf /opt/build

CMD ["/bin/bash"]
