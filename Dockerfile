FROM nvcr.io/nvidia/pytorch:25.04-py3

# 设置工作目录
WORKDIR /app

# 设置代理环境变量以加速后续网络请求
ENV HTTP_PROXY=http://10.158.68.105:1080
ENV HTTPS_PROXY=http://10.158.68.105:1080

# 安装 ffmpeg (因为 apt 在代理下报错，我们直接下载静态二进制文件)
RUN curl -x http://10.158.68.105:1080 -L -o /tmp/ffmpeg.tar.xz https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz && \
    tar -xvf /tmp/ffmpeg.tar.xz -C /tmp && \
    mv /tmp/ffmpeg-*-static/ffmpeg /usr/local/bin/ && \
    mv /tmp/ffmpeg-*-static/ffprobe /usr/local/bin/ && \
    rm -rf /tmp/ffmpeg*

# 安装 uv 包管理器
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh

# 复制项目文件
COPY pyproject.toml requirements.txt uv.lock ./
COPY . .

# 使用 uv 安装其余依赖（由于基础镜像已包含 torch，会自动满足 ctranslate2 等对 torch 的隐式需求，或根据需要略过）
# 设置代理环境变量以加速下载
ARG HTTP_PROXY=http://10.158.68.105:1080
ARG HTTPS_PROXY=http://10.158.68.105:1080
ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

RUN uv pip install --system --break-system-packages -r requirements.txt

# 将 python 脚本设置为入口点，允许在 docker run 时动态传递参数
ENTRYPOINT ["python", "smart_transcribe.py"]
# 默认如果不传参数，则打印帮助信息
CMD ["--help"]
