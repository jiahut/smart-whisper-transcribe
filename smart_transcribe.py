import argparse
import os
import time
import datetime
import platform
import psutil
from typing import List, Dict, Any

def format_time(seconds):
    td = datetime.timedelta(seconds=seconds)
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = td.microseconds // 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

class BaseTranscriber:
    def __init__(self, model_size: str, compute_type: str = "auto"):
        self.model_size = model_size
        self.compute_type = compute_type

    def transcribe(self, audio_path: str, language: str, initial_prompt: str, beam_size: int) -> tuple[List[Dict[str, Any]], str, float]:
        """Returns: (segments, detected_language, language_probability)
        segments format: [{"start": 0.0, "end": 1.0, "text": "xxx"}, ...]
        """
        raise NotImplementedError()

class FasterWhisperTranscriber(BaseTranscriber):
    def __init__(self, model_size: str, device: str, compute_type: str):
        super().__init__(model_size, compute_type)
        self.device = device
        print(f"[*] 引擎: Faster-Whisper | 正在加载模型: {model_size} ({compute_type} on {device})...")
        from faster_whisper import WhisperModel
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio_path: str, language: str, initial_prompt: str, beam_size: int):
        kwargs = {"beam_size": beam_size, "initial_prompt": initial_prompt}
        if language and language != "auto":
            kwargs["language"] = language

        segments_gen, info = self.model.transcribe(audio_path, **kwargs)

        segments = []
        for seg in segments_gen:
            segments.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text
            })
        return segments, info.language, info.language_probability

class MlxTranscriber(BaseTranscriber):
    def __init__(self, model_size: str, compute_type: str):
        super().__init__(model_size, compute_type)
        self.model_path = self._map_model_to_mlx(model_size)
        print(f"[*] 引擎: MLX-Whisper | 正在准备模型: {self.model_path} (Apple Silicon GPU加速)...")

    def _map_model_to_mlx(self, size: str) -> str:
        # 默认映射到 mlx-community 上的标准模型，由于 MLX 的极度优化，可以轻松加载大模型
        mapping = {
            "tiny": "mlx-community/whisper-tiny-mlx",
            "base": "mlx-community/whisper-base-mlx",
            "small": "mlx-community/whisper-small-mlx",
            "medium": "mlx-community/whisper-medium-mlx",
            "large-v3": "mlx-community/whisper-large-v3-mlx",
        }
        return mapping.get(size, f"mlx-community/whisper-{size}-mlx")

    def transcribe(self, audio_path: str, language: str, initial_prompt: str, beam_size: int):
        import mlx_whisper
        kwargs = {"path_or_hf_repo": self.model_path}

        # 组装 decode_options
        decode_opts = {}
        if language and language != "auto":
            decode_opts["language"] = language
        if initial_prompt:
            decode_opts["initial_prompt"] = initial_prompt

        result = mlx_whisper.transcribe(
            audio_path,
            **kwargs,
            **decode_opts
        )

        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"]
            })

        detected_lang = result.get("language", language if language != "auto" else "unknown")
        # mlx-whisper 返回结构较简，未直接抛出全局概率，这里用 1.0 占位
        return segments, detected_lang, 1.0

def detect_best_config():
    system = platform.system()
    machine = platform.machine()
    # 转换为 GB
    total_ram_gb = psutil.virtual_memory().total / (1024 ** 3)

    config = {
        "backend": "faster-whisper",
        "device": "cpu",
        "model": "small",
        "compute_type": "int8"
    }

    # 1. 探测物理内存/显存，智能选择最优模型大小
    # MLX和FasterWhisper都有很好的量化，普通16GB即可跑 large-v3
    if total_ram_gb >= 15:
        config["model"] = "large-v3"
    elif total_ram_gb >= 7:
        config["model"] = "medium"
    else:
        config["model"] = "small"

    # 2. 探测底层硬件，智能路由引擎
    if system == "Darwin" and machine == "arm64":
        config["backend"] = "mlx-whisper"
        config["device"] = "mps" # 仅作标示，mlx内部自动调度
    else:
        # 尝试探测是否有 NVIDIA CUDA
        try:
            # 这是一个轻量级的启发式探测方案，如果没有安装 torch 会优雅回退到 cpu
            import torch
            if torch.cuda.is_available():
                config["device"] = "cuda"
                config["compute_type"] = "float16" # CUDA推荐使用float16
        except ImportError:
            pass

    return config

def main():
    parser = argparse.ArgumentParser(
        description="自适应跨平台高精度音频转录 SRT 字幕生成工具。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("audio_file", help="输入的音频文件路径 (绝对路径或相对路径均可)")
    parser.add_argument("--model", default="auto", help="模型大小 (auto/tiny/base/small/medium/large-v3)。auto会基于内存智能探测")
    parser.add_argument("--backend", default="auto", help="推理引擎 (auto/mlx-whisper/faster-whisper)")
    parser.add_argument("--device", default="auto", help="计算设备 (auto/cpu/cuda)")
    parser.add_argument("--compute_type", default="auto", help="计算精度 (auto/int8/float16)")
    parser.add_argument("--language", default="zh", help="语言代码 (auto表示自动检测)")
    parser.add_argument("--initial_prompt", default="你好！这里是一段标准的简体中文语音记录。请问准备好开始了吗？好的，那就让我们开始吧！", help="前置上下文提示词")
    parser.add_argument("--beam_size", type=int, default=5, help="Beam search 大小")

    args = parser.parse_args()

    audio_path = os.path.abspath(args.audio_file)
    if not os.path.exists(audio_path):
        print(f"[-] 错误：找不到文件 {audio_path}")
        return

    # 执行硬件和内存的自探测
    best_config = detect_best_config()

    # 优先应用用户传入的参数（覆盖 auto）
    backend = best_config["backend"] if args.backend == "auto" else args.backend
    device = best_config["device"] if args.device == "auto" else args.device
    model_size = best_config["model"] if args.model == "auto" else args.model
    compute_type = best_config["compute_type"] if args.compute_type == "auto" else args.compute_type

    print(f"[*] 系统内存检测: ~{psutil.virtual_memory().total / (1024**3):.1f} GB")
    print(f"[*] 最终运行配置 -> 引擎: {backend} | 模型: {model_size} | 设备: {device}")

    # 实例化转录器对象
    start_time = time.time()
    try:
        if backend == "mlx-whisper":
            transcriber = MlxTranscriber(model_size, compute_type)
        else:
            transcriber = FasterWhisperTranscriber(model_size, device, compute_type)
    except Exception as e:
        print(f"[-] 引擎初始化失败: {e}")
        return

    dir_name = os.path.dirname(audio_path)
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    output_path = os.path.join(dir_name, f"{base_name}_音频_精准版.srt")

    print(f"[*] 开始转录: {audio_path}")
    try:
        segments, detected_lang, lang_prob = transcriber.transcribe(
            audio_path,
            language=args.language,
            initial_prompt=args.initial_prompt,
            beam_size=args.beam_size
        )
    except Exception as e:
        print(f"[-] 转录失败: {e}")
        return

    print(f"[*] 成功识别到语言: '{detected_lang}' (概率: {lang_prob:.2f})")
    print(f"[*] 正在生成 SRT 字幕文件: {output_path}")

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments):
                start = format_time(segment["start"])
                end = format_time(segment["end"])

                f.write(f"{i+1}\n")
                f.write(f"{start} --> {end}\n")
                f.write(f"{segment['text'].strip()}\n\n")

                if i % 50 == 0 and i > 0:
                    print(f"  ... 已处理 {i} 条字幕 (音频进度: {start})")
    except Exception as e:
        print(f"[-] 写入文件失败: {e}")
        return

    total_time = time.time() - start_time
    print(f"\n[*] 转录任务圆满完成！总耗时: {total_time:.2f} 秒。")
    print(f"[*] 输出文件位置: {output_path}")

if __name__ == "__main__":
    main()
