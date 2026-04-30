# Transcribe Task Manager

一个用 Go 语言编写的轻量级任务管理器，专门用于接收音频文件并调度 `smart-whisper` Docker 容器进行后台转录处理。
使用 SQLite 作为单文件数据库，无外部依赖（CGO-Free），非常适合跨平台编译并直接部署到 Linux 服务器（如 `cuttlefish154`）上。

## 📦 编译与部署

在开发机上交叉编译为 Linux 可执行文件（无需在服务器上安装 Go 环境）：

```bash
# 对于 Linux x86_64 架构
GOOS=linux GOARCH=amd64 go build -o transcribe-task-mgr main.go

# 对于 Linux ARM64 架构 (如使用 aarch64 服务器)
GOOS=linux GOARCH=arm64 go build -o transcribe-task-mgr main.go
```

将编译好的二进制文件传输到目标服务器：
```bash
scp transcribe-task-mgr user@cuttlefish154:/path/to/deploy/
```

在服务器上运行：
```bash
chmod +x transcribe-task-mgr
./transcribe-task-mgr
# 默认会在 8080 端口启动服务，并在当前目录创建 `tasks.db` 和 `uploads/` 文件夹。
```

## 🚀 API 使用指南

### 1. 提交转录任务 (Upload)

使用 `curl` 上传音频文件，服务器会自动保存并在后台启动 Docker 任务。

```bash
curl -X POST -F "file=@/path/to/your/audio.mp3" http://<服务器IP>:8080/upload
```
**返回示例：**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "pending",
  "message": "File uploaded and task queued successfully"
}
```

### 2. 查看所有任务状态 (Status List)

```bash
curl http://<服务器IP>:8080/status
```
**返回示例：**
```json
[
  {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "filename": "123e4567-e89b-12d3-a456-426614174000.mp3",
    "status": "completed",
    "created_at": "2026-04-27T10:00:00Z",
    "updated_at": "2026-04-27T10:05:00Z"
  }
]
```

### 3. 查看单个任务状态 (Single Status)

```bash
curl http://<服务器IP>:8080/status/123e4567-e89b-12d3-a456-426614174000
```

### 4. 下载生成的字幕文件 (Download)

当任务状态为 `completed` 时，可以下载生成的 SRT 字幕文件：

```bash
curl -O -J http://<服务器IP>:8080/download/123e4567-e89b-12d3-a456-426614174000
```
*(注：`-O -J` 参数会让 curl 自动使用服务器返回的文件名保存，例如 `123e4567-e89b-12d3-a456-426614174000_音频_精准版.srt`)*

## 🛠️ 后台执行逻辑说明

本服务收到文件后，会执行以下等效命令：
```bash
docker run --rm --gpus all --ipc=host \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    -v /absolute/path/to/uploads:/app \
    smart-whisper:latest <filename>
```
确保服务器上已构建好 `smart-whisper:latest` 镜像，并已配置好 NVIDIA Docker 运行时环境。
