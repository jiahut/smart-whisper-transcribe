import argparse
import os
import time
import datetime
from faster_whisper import WhisperModel

def format_time(seconds):
    td = datetime.timedelta(seconds=seconds)
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = td.microseconds // 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def main():
    parser = argparse.ArgumentParser(
        description="基于 faster-whisper 的高精度音频转录 SRT 字幕生成工具。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # 必填位置参数：输入文件
    parser.add_argument("audio_file", help="输入的音频文件路径 (绝对路径或相对路径均可)")
    
    # 可选参数 (根据我们之前的实践设置了默认值)
    parser.add_argument("--model", default="small", help="使用的 faster-whisper 模型大小")
    parser.add_argument("--device", default="cpu", help="计算设备 ('cpu' 或 'cuda')")
    parser.add_argument("--compute_type", default="int8", help="计算精度类型 (如 'int8', 'float16')")
    parser.add_argument("--language", default="zh", help="强制指定的语言代码")
    parser.add_argument("--initial_prompt", default="这是一段简体中文的IT数字化建设汇报。", help="前置上下文提示词，用于引导输出简体中文和专业词汇")
    parser.add_argument("--beam_size", type=int, default=5, help="Beam search 大小")

    args = parser.parse_args()

    audio_path = os.path.abspath(args.audio_file)
    if not os.path.exists(audio_path):
        print(f"[-] 错误：找不到文件 {audio_path}")
        return

    # 构造输出路径：同目录下的 `原文件名_音频_精准版.srt`
    dir_name = os.path.dirname(audio_path)
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    output_path = os.path.join(dir_name, f"{base_name}_音频_精准版.srt")

    print(f"[*] 准备加载模型: {args.model} ({args.compute_type} on {args.device})...")
    start_time = time.time()
    
    try:
        model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    except Exception as e:
        print(f"[-] 模型加载失败: {e}")
        return

    print(f"[*] 模型加载完成。开始转录: {audio_path}")
    try:
        segments, info = model.transcribe(
            audio_path,
            beam_size=args.beam_size,
            language=args.language,
            initial_prompt=args.initial_prompt
        )
    except Exception as e:
        print(f"[-] 转录失败: {e}")
        return

    print(f"[*] 成功识别到语言: '{info.language}' (概率: {info.language_probability:.2f})")
    print(f"[*] 正在生成 SRT 字幕文件: {output_path}")

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments):
                start = format_time(segment.start)
                end = format_time(segment.end)
                
                # 写入 SRT 标准格式
                f.write(f"{i+1}\n")
                f.write(f"{start} --> {end}\n")
                f.write(f"{segment.text.strip()}\n\n")
                
                # 每处理 50 条打印一次进度
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
