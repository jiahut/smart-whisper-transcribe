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

### 1. 安装依赖

推荐使用极速包管理器 [uv](https://github.com/astral-sh/uv) 在虚拟环境中安装依赖，以获得最佳体验：

```bash
# 1. 创建并激活虚拟环境
uv venv
source .venv/bin/activate  # Mac/Linux
# .venv\Scripts\activate   # Windows

# 2. 极速安装依赖
uv pip install -r requirements.txt
```

*备选方案（使用传统 pip）：*
```bash
pip install -r requirements.txt
```

> **注意**：`requirements.txt` 内置了针对 Mac arm64 的环境过滤规则，仅在 Mac 环境下才会安装 `mlx-whisper`，保证跨平台分享时不报错。

### 2. 基本使用

你只需要传入音频文件，脚本会自动探测当前机器的最优配置（引擎、模型大小、计算精度）并执行：

```bash
python smart_transcribe.py path/to/your/audio.mp3
```

生成的高精度 `_音频_精准版.srt` 字幕文件会自动保存在原音频的同级目录下。

### 3. 高级参数

你也可以随时手动覆盖智能探测的结果：

```bash
python smart_transcribe.py audio.mp3 \
    --model small \
    --backend faster-whisper \
    --device cpu \
    --language zh \
    --initial_prompt "这是一段简体中文的音频文件" \
    --beam_size 5
```

查看所有可用参数说明：

```bash
python smart_transcribe.py --help
```
