FROM ubuntu:25.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/workspace/anima_lora_webui/.venv \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    WEBUI_HOST=0.0.0.0 \
    WEBUI_PORT=20102 \
    CODE_SERVER_AUTH=password \
    CODE_SERVER_PORT=4200 \
    PATH=/root/.local/bin:/workspace/anima_lora_webui/.venv/bin:${PATH}

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    tar \
    unzip \
    vim \
    inxi \
    telnet \
    tree \
    openssh-server \
    net-tools \
    supervisor \
    procps \
    git \
    git-lfs \
    build-essential \
    pkg-config \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
 && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

COPY docker/patch_code_server_extensions.js /usr/local/lib/patch_code_server_extensions.js

RUN curl -fsSL https://code-server.dev/install.sh | sh \
 && /usr/lib/code-server/lib/node /usr/local/lib/patch_code_server_extensions.js \
      /usr/lib/code-server/lib/vscode/extensions \
 && code-server --version

RUN curl -fsSL https://gosspublic.alicdn.com/ossutil/install.sh | bash \
 && ossutil --version

RUN wget -O /usr/local/bin/dumb-init https://bizy-air.oss-cn-beijing.aliyuncs.com/dumb-init_1.2.5_x86_64 \
 && chmod +x /usr/local/bin/dumb-init

WORKDIR /workspace/anima_lora_webui

COPY . /workspace/anima_lora_webui
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY docker/supervisord.conf /etc/supervisor/conf.d/anima_lora.conf

RUN chmod +x /usr/local/bin/entrypoint.sh \
 && chmod +x /workspace/anima_lora_webui/scripts/download_models_from_oss.sh \
 && git lfs install --system \
 && mkdir -p /var/log/supervisor /var/run/sshd /workspace/anima_lora_webui/logs \
 && mkdir -p /workspace/anima_lora_webui/models /workspace/anima_lora_webui/output \
 && mkdir -p /workspace/anima_lora_webui/image_dataset /workspace/anima_lora_webui/post_image_dataset \
 && uv python install 3.13 \
 && uv sync --no-dev --python 3.13

EXPOSE 22 20102 4200

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
    CMD bash -lc "curl -fsS http://127.0.0.1:${WEBUI_PORT}/ >/dev/null || exit 1"

ENTRYPOINT ["/usr/local/bin/dumb-init", "--", "/usr/local/bin/entrypoint.sh"]
