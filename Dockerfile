FROM ubuntu:26.04

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATH="/venv/bin:$PATH"

# 国内网络直连 archive.ubuntu.com 常超时；默认切阿里云 Ubuntu 镜像（用 http，基础镜像未装 ca-certificates）。
# 需要时用 --build-arg APT_MIRROR=http://archive.ubuntu.com/ubuntu/ 覆盖。
ARG APT_MIRROR=http://mirrors.aliyun.com/ubuntu/

RUN sed -i -E \
        -e "s|https?://archive\.ubuntu\.com/ubuntu/?|${APT_MIRROR}|g" \
        -e "s|https?://security\.ubuntu\.com/ubuntu/?|${APT_MIRROR}|g" \
        /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates python3 python3-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# 国内网络（公司内网/家庭带宽）直连 files.pythonhosted.org 易超时，默认走阿里云 PyPI 镜像；
# 需要时用 --build-arg PIP_INDEX_URL=https://pypi.org/simple/ 覆盖。
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
RUN python3 -m venv /venv \
    && /venv/bin/pip install --no-cache-dir \
        --index-url "${PIP_INDEX_URL}" \
        --timeout 60 --retries 5 \
        -r requirements.txt

COPY backend ./backend
COPY data/sample ./data/sample
COPY tests ./tests
COPY alembic.ini ./alembic.ini

RUN useradd -m appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
