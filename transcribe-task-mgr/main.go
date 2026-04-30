package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	_ "modernc.org/sqlite"
)

type Task struct {
	ID               string    `json:"id"`
	SavedFilename    string    `json:"-"`
	OriginalFilename string    `json:"filename"`
	Status           string    `json:"status"` // pending, processing, completed, failed
	ErrorMsg         string    `json:"error_msg,omitempty"`
	CreatedAt        time.Time `json:"created_at"`
	UpdatedAt        time.Time `json:"updated_at"`
}

var db *sql.DB
var gpuPool chan int

func initGPU() {
	// Try to dynamically get GPU count
	cmd := exec.Command("sh", "-c", "nvidia-smi --query-gpu=name --format=csv,noheader | wc -l")
	out, err := cmd.Output()
	gpuCount := 1 // fallback
	if err == nil {
		countStr := strings.TrimSpace(string(out))
		if c, err := strconv.Atoi(countStr); err == nil && c > 0 {
			gpuCount = c
		}
	}
	log.Printf("Detected %d GPUs", gpuCount)
	
	// Create worker pool with GPU IDs
	gpuPool = make(chan int, gpuCount)
	for i := 0; i < gpuCount; i++ {
		gpuPool <- i
	}
}

func initDB() {
	var err error
	db, err = sql.Open("sqlite", "tasks.db")
	if err != nil {
		log.Fatalf("Failed to open database: %v", err)
	}

	createTableQuery := `
	CREATE TABLE IF NOT EXISTS tasks (
		id TEXT PRIMARY KEY,
		filename TEXT NOT NULL,
		original_filename TEXT DEFAULT '',
		status TEXT NOT NULL,
		error_msg TEXT,
		created_at DATETIME NOT NULL,
		updated_at DATETIME NOT NULL
	);`
	_, err = db.Exec(createTableQuery)
	if err != nil {
		log.Fatalf("Failed to create table: %v", err)
	}

	// Add column if it doesn't exist (ignore error if it already exists)
	_, _ = db.Exec("ALTER TABLE tasks ADD COLUMN original_filename TEXT DEFAULT ''")
}

func main() {
	// Ensure uploads directory exists
	if err := os.MkdirAll("uploads", 0755); err != nil {
		log.Fatalf("Failed to create uploads directory: %v", err)
	}

	initDB()
	initGPU()
	defer db.Close()

	http.HandleFunc("/upload", handleUpload)
	http.HandleFunc("/status", handleStatusList)
	http.HandleFunc("/status/", handleStatusSingle) // handles /status/{id}
	http.HandleFunc("/download/", handleDownload)   // handles /download/{id}

	port := "8080"
	log.Printf("Starting server on :%s", port)
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatalf("Server error: %v", err)
	}
}

func handleUpload(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// 100 MB max memory for multipart parsing
	err := r.ParseMultipartForm(100 << 20)
	if err != nil {
		http.Error(w, "Failed to parse form: "+err.Error(), http.StatusBadRequest)
		return
	}

	file, header, err := r.FormFile("file")
	if err != nil {
		http.Error(w, "Failed to get file from form", http.StatusBadRequest)
		return
	}
	defer file.Close()

	taskID := uuid.New().String()[:8]
	originalName := header.Filename
	ext := filepath.Ext(originalName)
	// We use taskID as the base name to avoid collisions
	savedFileName := fmt.Sprintf("%s%s", taskID, ext)
	savedPath := filepath.Join("uploads", savedFileName)

	dst, err := os.Create(savedPath)
	if err != nil {
		http.Error(w, "Failed to create file on server", http.StatusInternalServerError)
		return
	}
	defer dst.Close()

	if _, err := io.Copy(dst, file); err != nil {
		http.Error(w, "Failed to save file", http.StatusInternalServerError)
		return
	}

	now := time.Now()
	_, err = db.Exec(
		"INSERT INTO tasks (id, filename, original_filename, status, error_msg, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
		taskID, savedFileName, originalName, "pending", "", now, now,
	)
	if err != nil {
		http.Error(w, "Failed to save task to db: "+err.Error(), http.StatusInternalServerError)
		return
	}

	go processTask(taskID, savedFileName)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	json.NewEncoder(w).Encode(map[string]string{
		"id":      taskID,
		"status":  "pending",
		"message": "File uploaded and task queued successfully",
	})
}

func updateTaskStatus(id, status, errorMsg string) {
	_, err := db.Exec(
		"UPDATE tasks SET status = ?, error_msg = ?, updated_at = ? WHERE id = ?",
		status, errorMsg, time.Now(), id,
	)
	if err != nil {
		log.Printf("Failed to update task %s status: %v", id, err)
	}
}

func processTask(id, filename string) {
	updateTaskStatus(id, "processing", "")
	log.Printf("Task %s started processing file %s", id, filename)

	// Get absolute path to uploads dir
	uploadsDir, err := filepath.Abs("uploads")
	if err != nil {
		updateTaskStatus(id, "failed", "Failed to get uploads dir absolute path")
		return
	}

	// Resolve Huggingface cache path safely (assuming ~/.cache/huggingface)
	homeDir, err := os.UserHomeDir()
	if err != nil {
		updateTaskStatus(id, "failed", "Failed to get user home dir")
		return
	}
	hfCacheDir := filepath.Join(homeDir, ".cache", "huggingface")

	// Acquire a GPU from the pool
	gpuID := <-gpuPool
	defer func() { gpuPool <- gpuID }()
	log.Printf("Task %s acquired GPU %d", id, gpuID)

	// Create command
	// docker run --rm --gpus "device=<gpuID>" --ipc=host -v ~/.cache/huggingface:/root/.cache/huggingface -v $(pwd)/uploads:/data smart-whisper-arm:latest <filename>
	cmd := exec.Command("docker", "run", "--rm", "--gpus", fmt.Sprintf("device=%d", gpuID), "--ipc=host",
		"-v", fmt.Sprintf("%s:/root/.cache/huggingface", hfCacheDir),
		"-v", fmt.Sprintf("%s:/data", uploadsDir),
		"smart-whisper-arm:latest",
		fmt.Sprintf("/data/%s", filename),
	)

	// Capture output for logging/debugging
	output, err := cmd.CombinedOutput()
	if err != nil {
		log.Printf("Task %s failed: %v\nOutput: %s", id, err, string(output))
		// Keep error message reasonably short for DB
		errMsg := err.Error()
		if len(output) > 0 {
			// Get last 500 chars of output to capture actual error
			outStr := string(output)
			if len(outStr) > 500 {
				outStr = outStr[len(outStr)-500:]
			}
			errMsg = fmt.Sprintf("%v: %s", err, outStr)
		}
		updateTaskStatus(id, "failed", errMsg)
		return
	}

	log.Printf("Task %s completed successfully", id)
	updateTaskStatus(id, "completed", "")
}

func handleStatusList(w http.ResponseWriter, r *http.Request) {
	rows, err := db.Query("SELECT id, filename, original_filename, status, error_msg, created_at, updated_at FROM tasks ORDER BY created_at DESC")
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var tasks []Task
	for rows.Next() {
		var t Task
		var errorMsg sql.NullString
		if err := rows.Scan(&t.ID, &t.SavedFilename, &t.OriginalFilename, &t.Status, &errorMsg, &t.CreatedAt, &t.UpdatedAt); err != nil {
			log.Printf("Row scan error: %v", err)
			continue
		}
		if errorMsg.Valid {
			t.ErrorMsg = errorMsg.String
		}
		tasks = append(tasks, t)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(tasks)
}

func handleStatusSingle(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimPrefix(r.URL.Path, "/status/")
	if id == "" {
		http.Error(w, "Task ID required", http.StatusBadRequest)
		return
	}

	var t Task
	var errorMsg sql.NullString
	err := db.QueryRow("SELECT id, filename, original_filename, status, error_msg, created_at, updated_at FROM tasks WHERE id = ?", id).
		Scan(&t.ID, &t.SavedFilename, &t.OriginalFilename, &t.Status, &errorMsg, &t.CreatedAt, &t.UpdatedAt)

	if err == sql.ErrNoRows {
		http.Error(w, "Task not found", http.StatusNotFound)
		return
	} else if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	if errorMsg.Valid {
		t.ErrorMsg = errorMsg.String
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(t)
}

func handleDownload(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimPrefix(r.URL.Path, "/download/")
	if id == "" {
		http.Error(w, "Task ID required", http.StatusBadRequest)
		return
	}

	var savedFilename, originalFilename, status string
	err := db.QueryRow("SELECT filename, original_filename, status FROM tasks WHERE id = ?", id).Scan(&savedFilename, &originalFilename, &status)
	if err == sql.ErrNoRows {
		http.Error(w, "Task not found", http.StatusNotFound)
		return
	} else if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	if status != "completed" {
		http.Error(w, "Task is not completed yet", http.StatusBadRequest)
		return
	}

	// smart_transcribe.py generates output like: {basename}_音频_精准版.srt
	baseName := strings.TrimSuffix(savedFilename, filepath.Ext(savedFilename))
	srtFilename := fmt.Sprintf("%s_音频_精准版.srt", baseName)
	srtPath := filepath.Join("uploads", srtFilename)

	if _, err := os.Stat(srtPath); os.IsNotExist(err) {
		http.Error(w, "Result file not found", http.StatusNotFound)
		return
	}

	origBase := strings.TrimSuffix(originalFilename, filepath.Ext(originalFilename))
	downloadName := fmt.Sprintf("%s_音频_精准版.srt", origBase)

	w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"; filename*=UTF-8''%s`, downloadName, url.PathEscape(downloadName)))
	w.Header().Set("Content-Type", "application/x-subrip")
	http.ServeFile(w, r, srtPath)
}
