# Start FilingFinder: database, AI model check, web page build, then the server.
#
# Run from the project folder:
#   powershell -ExecutionPolicy Bypass -File .\start.ps1
# Then use the page at http://localhost:8000 (opens automatically).
# Press Ctrl+C in this window to stop the server.

# Not "Stop": Windows PowerShell treats progress text that docker/npm print on
# stderr as errors. Every step checks $LASTEXITCODE or its result instead.
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "    OK  $text" -ForegroundColor Green }
function Fail($text, $fix) {
    Write-Host "    PROBLEM  $text" -ForegroundColor Red
    Write-Host "    FIX      $fix" -ForegroundColor Yellow
    exit 1
}

# Read a setting from .env (falls back to a default).
function Get-Setting($name, $default) {
    $line = Get-Content .env -ErrorAction SilentlyContinue | Where-Object { $_ -match "^\s*$name\s*=" } | Select-Object -First 1
    if ($line) { return ($line -split "=", 2)[1].Trim() }
    return $default
}

# 1. Python environment and settings ------------------------------------------
Step "Checking Python environment and settings"
$python = ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Fail "No Python environment (.venv) found." "See README: 'python -m venv .venv' then 'pip install -r requirements.txt'."
}
if (-not (Test-Path .env)) {
    Fail "No .env settings file." "Copy .env.example to .env and fill in the values."
}
Ok "Python environment and .env found"

# 2. Docker and the database ----------------------------------------------------
Step "Starting the database (Docker)"
$docker = (Get-Command docker -ErrorAction SilentlyContinue).Source
if (-not $docker) {
    $candidate = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
    if (Test-Path $candidate) { $docker = $candidate } else { $docker = "C:\Program Files\Docker\Docker\resources\bin\docker.exe" }
}
if (-not (Test-Path $docker)) { Fail "Docker isn't installed." "Install Docker Desktop (free) from https://www.docker.com/products/docker-desktop/" }

& $docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "    Docker Desktop isn't running; starting it (this can take a minute)..."
    $desktop = @("$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe",
                 "C:\Program Files\Docker\Docker\Docker Desktop.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($desktop) { Start-Process $desktop }
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 3
        & $docker info *> $null
        if ($LASTEXITCODE -eq 0) { break }
    }
    if ($LASTEXITCODE -ne 0) { Fail "Docker Desktop didn't start." "Open Docker Desktop and wait for 'Engine running', then run this script again." }
}
& $docker compose up -d --wait *> $null
if ($LASTEXITCODE -ne 0) { Fail "The database container didn't start." "Run 'docker compose up -d' to see the error." }

$passages = & $python -c "from src.db import connect; c = connect(); print(c.execute('select count(embedding) from chunks').fetchone()[0])" 2>$null
if (-not $passages -or [int]$passages -eq 0) {
    Fail "The database has no indexed passages." "Build them once (about 1.5 hours): see README steps 4-6."
}
Ok "Database running with $passages indexed passages"

# 3. Ollama and the AI model ----------------------------------------------------
Step "Checking the AI model (Ollama)"
$ollamaUrl = Get-Setting "OLLAMA_URL" "http://127.0.0.1:11434"
$model = Get-Setting "OLLAMA_MODEL" "qwen3.5:4b"
function Get-OllamaModels {
    try { return (Invoke-RestMethod "$ollamaUrl/api/tags" -TimeoutSec 3).models.name } catch { return $null }
}
$models = Get-OllamaModels
if ($null -eq $models) {
    $app = "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
    if (Test-Path $app) {
        Write-Host "    Ollama isn't running; starting it..."
        Start-Process $app
        for ($i = 0; $i -lt 20 -and $null -eq $models; $i++) { Start-Sleep -Seconds 2; $models = Get-OllamaModels }
    }
}
if ($null -eq $models) { Fail "Ollama isn't running." "Install it from https://ollama.com/download and start the Ollama app." }
if ($models -notcontains $model) { Fail "The model '$model' isn't downloaded." "Run: ollama pull $model" }
Ok "Ollama running with $model"

# 4. The web page -----------------------------------------------------------------
Step "Preparing the web page"
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Fail "Node.js isn't installed." "Install Node.js 20 or newer (free) from https://nodejs.org/"
}
Push-Location web
try {
    if (-not (Test-Path node_modules)) {
        Write-Host "    Installing page packages (first run only)..."
        npm install --no-audit --no-fund *> $null
        if ($LASTEXITCODE -ne 0) { Fail "npm install failed." "Run 'npm install' in the web folder to see the error." }
    }
    $built = Get-Item dist\index.html -ErrorAction SilentlyContinue
    $newest = Get-ChildItem src, index.html, vite.config.js -Recurse -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $built -or $newest.LastWriteTime -gt $built.LastWriteTime) {
        Write-Host "    Building the page..."
        npm run build *> $null
        if ($LASTEXITCODE -ne 0) { Fail "Building the page failed." "Run 'npm run build' in the web folder to see the error." }
    }
} finally { Pop-Location }
Ok "Web page ready"

# 5. Start the server and open the browser ------------------------------------------
Step "Starting FilingFinder at http://localhost:8000  (Ctrl+C to stop)"
Start-Job -ScriptBlock {
    for ($i = 0; $i -lt 60; $i++) {
        try { Invoke-RestMethod "http://127.0.0.1:8000/api/health" -TimeoutSec 2 | Out-Null; Start-Process "http://localhost:8000"; return } catch { Start-Sleep -Seconds 2 }
    }
} | Out-Null
& $python -m uvicorn src.api.app:app --port 8000
