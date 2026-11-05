# Local stand-in for the contest sandbox (rulebook 5.1-5.4): Python 3.11 with
# numpy and scipy only. Run with --network none --read-only --cpus 1 --memory 1g.
FROM python:3.11-slim
RUN pip install --no-cache-dir numpy scipy
ENV PYTHONDONTWRITEBYTECODE=1
