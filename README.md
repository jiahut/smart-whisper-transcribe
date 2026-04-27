# Smart Transcribe 🎙️

一个跨平台、环境自适应的高精度音频转录与 SRT 字幕生成工具。

## ✨ 特性

* **智能硬件路由 (Auto-Routing)**：
  * **Apple Silicon (Mac M1/M2/M3/M4)**：自动调用苹果官方 `mlx-whisper`，充分压榨统一内存与 Mac GPU 算力。
  * **NVIDIA GPU**：自动检测 CUDA 环境，无缝切换为 `faster-whisper` + `float16` 高速推理。
  * **常规环境**：优雅回退到普通 CPU 模式运行。
* **智能模型选择**：根据系统内存自动匹配最优的 Whisper 模型大小（从 `small` 到 `large-v3`），无需手动纠结，兼顾速度与准确度。
* **跨平台兼容**：一套代码即可在 Mac、Windows、Linux 上顺畅运行，相关依赖根据环境按需加载防崩溃。

## 🚀 快速开始

### 1. 全局安装 (推荐)

本项目已支持作为命令行工具进行全局安装。推荐使用 [uv](https://github.com/astral-sh/uv) 进行极速安装：

```bash
# 在项目根目录下执行全局安装
uv tool install .

# 或者使用可编辑模式（推荐开发者使用，修改代码后实时生效）
uv tool install -e .
```

*备选方案（仅在当前目录下同步开发环境依赖）：*
```bash
uv venv
source .venv/bin/activate
uv sync
```

### 2. 基本使用

安装完成后，你可以在任何目录下直接使用 `smart-transcribe` 命令。只需要传入音频文件，脚本会自动探测当前机器的最优配置（引擎、模型大小、计算精度）并执行：

```bash
smart-transcribe path/to/your/audio.mp3
```

生成的高精度 `_音频_精准版.srt` 字幕文件会自动保存在原音频的同级目录下。

### 3. 高级参数

你也可以随时手动覆盖智能探测的结果：

```bash
smart-transcribe audio.mp3 \
    --model small \
    --backend faster-whisper \
    --device cpu \
    --language zh \
    --initial_prompt "这是一段简体中文的音频文件" \
    --beam_size 5
```

查看所有可用参数说明：

```bash
smart-transcribe --help
```

### 4. 使用 Docker 运行 (推荐 Linux 服务器/GPU 环境)

如果你在 Linux 服务器上运行（特别是拥有 NVIDIA GPU 的环境），可以通过 Docker 隔离复杂的依赖。我们将脚本配置成了容器的 Entrypoint，你可以像执行命令行一样向容器传递参数。

**构建镜像：**
```bash
docker build -t smart-whisper:latest .
```

**运行容器：**
为了让容器能读取到你的音频文件并保存生成的字幕，并且**避免每次重复下载模型**，请务必挂载当前工作目录以及宿主机的 Hugging Face 缓存目录。

```bash
# 假设你的音频文件在当前目录下，文件名为 audio.mp3
docker run --rm --gpus all --ipc=host \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    -v $(pwd):/app \
    smart-whisper:latest audio.mp3
    
# 你也可以在后面继续追加高级参数
docker run --rm --gpus all --ipc=host \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    -v $(pwd):/app \
    smart-whisper:latest audio.mp3 --model medium
```

### 5. 特殊架构支持：ARM64 + NVIDIA GPU (如 aarch64 服务器)

如果在 **ARM 架构**的 Linux 服务器（例如拥有 NVIDIA Tesla T4 等 GPU 的 `aarch64` 机器）上运行，由于 PyPI 官方提供的 `ctranslate2` (Faster-Whisper 的底层推理库) 预编译包默认不支持 CUDA，直接使用默认的 Dockerfile 会报错 `This CTranslate2 package was not compiled with CUDA support` 并在实际推理时回退到 CPU。

为此，我们提供了专门的 `Dockerfile.arm`。它会在构建镜像时，从 C++ 源码重新编译带有 CUDA 支持的 `CTranslate2`：

**构建 ARM64 GPU 镜像 (源码编译耗时较长，请耐心等待)：**
```bash
docker build -t smart-whisper-arm:latest -f Dockerfile.arm .
```

**运行容器：**
运行方式与常规 Docker 完全一致，只需将镜像名称替换为 `smart-whisper-arm:latest` 即可：

```bash
docker run --rm --gpus all --ipc=host \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    -v $(pwd):/app \
    smart-whisper-arm:latest audio.mp3
```
