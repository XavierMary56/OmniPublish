# OmniPublish V2.0 — File Integrity Check (no Python/Node needed)
# Usage: Right-click -> Run with PowerShell, or:
#   powershell -ExecutionPolicy Bypass -File verify.ps1

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pass = 0
$fail = 0
$warns = @()

function Test-OK {
    param([string]$Name)
    Write-Host "  [PASS] $Name" -ForegroundColor Green
    $script:pass++
}

function Test-NG {
    param([string]$Name, [string]$Detail = "")
    Write-Host "  [FAIL] $Name $Detail" -ForegroundColor Red
    $script:fail++
}

function Test-Item {
    param([string]$Name, [bool]$Result, [string]$Detail = "")
    if ($Result) { Test-OK $Name } else { Test-NG $Name $Detail }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  OmniPublish V2.0 - File Integrity Check"
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ═══ 1. Directory Structure ═══
Write-Host "=== 1. Directory Structure ===" -ForegroundColor White

$requiredDirs = @(
    "backend", "backend\routers", "backend\services", "backend\models",
    "backend\middleware", "backend\scripts", "backend\websocket",
    "backend\tests", "backend\migrations", "docs",
    "frontend", "frontend\src", "frontend\src\views",
    "frontend\src\stores", "frontend\src\api"
)

foreach ($dir in $requiredDirs) {
    Test-Item "DIR $dir" (Test-Path (Join-Path $root $dir) -PathType Container)
}

# ═══ 2. Backend Core Files ═══
Write-Host ""
Write-Host "=== 2. Backend Core Files ===" -ForegroundColor White

$backendFiles = @(
    @("main.py", 100), @("config.py", 50), @("database.py", 80),
    @("requirements.txt", 10),
    @("routers\auth.py", 40), @("routers\pipeline.py", 100),
    @("routers\tasks.py", 40), @("routers\platforms.py", 40),
    @("routers\stats.py", 40), @("routers\tools.py", 40),
    @("services\pipeline_service.py", 60), @("services\copywrite_service.py", 30),
    @("services\rename_service.py", 20), @("services\cover_service.py", 30),
    @("services\watermark_service.py", 40), @("services\publish_service.py", 40),
    @("services\tools_service.py", 40),
    @("models\user.py", 10), @("models\task.py", 20),
    @("models\platform.py", 10), @("models\common.py", 5),
    @("middleware\auth.py", 30), @("websocket\manager.py", 20),
    @("tests\run_selftest.py", 50), @("tests\test_api.py", 50)
)

foreach ($item in $backendFiles) {
    $file = $item[0]; $minLines = $item[1]
    $full = Join-Path $root "backend\$file"
    if (Test-Path $full) {
        $lines = (Get-Content $full -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
        if ($lines -ge $minLines) { Test-OK "backend\$file ($lines lines)" }
        else { Test-NG "backend\$file" "only $lines lines (need >=$minLines)" }
    } else {
        Test-NG "backend\$file" "FILE NOT FOUND"
    }
}

# ═══ 3. Python Syntax Check ═══
Write-Host ""
Write-Host "=== 3. Python Syntax Check ===" -ForegroundColor White

$pythonAvailable = $false
try {
    $pyVer = & python --version 2>&1
    if ("$pyVer" -match "Python 3") {
        $pythonAvailable = $true
        Write-Host "  Python found: $pyVer" -ForegroundColor Gray
    }
} catch {}

if ($pythonAvailable) {
    $pyFiles = Get-ChildItem -Path (Join-Path $root "backend") -Filter "*.py" -Recurse
    $syntaxPass = 0
    $syntaxFail = 0
    foreach ($f in $pyFiles) {
        # Use python -m py_compile to avoid Windows path escape issues
        $result = & python -m py_compile $f.FullName 2>&1
        if ($LASTEXITCODE -eq 0) {
            $syntaxPass++
        } else {
            Test-NG "SYNTAX $($f.Name)" "$result"
            $syntaxFail++
        }
    }
    if ($syntaxFail -eq 0) {
        Test-OK "All $syntaxPass Python files syntax OK"
    }
} else {
    Write-Host "  [SKIP] Python not installed, skipping syntax check" -ForegroundColor Yellow
    $script:warns += "Python syntax check skipped (no Python)"
}

# ═══ 4. Frontend Files ═══
Write-Host ""
Write-Host "=== 4. Frontend Files ===" -ForegroundColor White

$frontendFiles = @(
    "index.html", "package.json", "vite.config.ts", "tsconfig.json",
    "src\main.ts", "src\router.ts", "src\App.vue",
    "src\views\Login.vue", "src\views\Dashboard.vue", "src\views\Pipeline.vue",
    "src\views\Tasks.vue", "src\views\Analytics.vue", "src\views\Platforms.vue",
    "src\views\Accounts.vue", "src\views\Toolbox.vue",
    "src\stores\auth.ts", "src\stores\pipeline.ts",
    "src\api\http.ts", "src\api\ws.ts", "src\assets\styles.css"
)

foreach ($file in $frontendFiles) {
    $full = Join-Path $root "frontend\$file"
    if (Test-Path $full) {
        $size = (Get-Item $full).Length
        if ($size -gt 50) { Test-OK "frontend\$file ($size bytes)" }
        else { Test-NG "frontend\$file" "file too small ($size bytes)" }
    } else {
        Test-NG "frontend\$file" "FILE NOT FOUND"
    }
}

# ═══ 5. Config & Deploy Files ═══
Write-Host ""
Write-Host "=== 5. Config & Deploy Files ===" -ForegroundColor White

$deployFiles = @(
    "config.json", "Dockerfile", "docker-compose.yml",
    "start.bat", "start.sh", ".gitignore", "CLAUDE.md",
    "docs\DEPLOY.md", "docs\USER_GUIDE.md", "docs\API.md"
)

foreach ($file in $deployFiles) {
    Test-Item $file (Test-Path (Join-Path $root $file))
}

# ═══ 6. Design Documents ═══
Write-Host ""
Write-Host "=== 6. Design Documents ===" -ForegroundColor White

# Use wildcards to avoid Chinese encoding issues in PowerShell
$designPatterns = @(
    @("01_PRD*", "PRD"),
    @("02_*", "State Machine"),
    @("03_*", "Tech Assets"),
    @("04_*", "Platform Config"),
    @("05_*html", "Prototype HTML"),
    @("06_*", "Implementation Plan")
)

foreach ($item in $designPatterns) {
    $pattern = $item[0]; $label = $item[1]
    $found = Get-ChildItem -Path $root -Filter $pattern -ErrorAction SilentlyContinue
    if ($found) { Test-OK "$label ($($found.Name))" }
    else { Test-NG "$label (pattern: $pattern)" "NOT FOUND" }
}

# ═══ 7. Code Content Checks ═══
Write-Host ""
Write-Host "=== 7. Code Content Checks ===" -ForegroundColor White

# Read files with explicit encoding
$mainContent = Get-Content (Join-Path $root "backend\main.py") -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
Test-Item "main.py has FastAPI" ($mainContent -match "FastAPI")
Test-Item "main.py has CORS" ($mainContent -match "CORSMiddleware")
Test-Item "main.py has WebSocket" ($mainContent -match "websocket")
Test-Item "main.py registers all routers" (
    $mainContent -match "auth" -and $mainContent -match "pipeline" -and
    $mainContent -match "tasks" -and $mainContent -match "platforms" -and
    $mainContent -match "stats" -and $mainContent -match "tools"
)

$dbContent = Get-Content (Join-Path $root "backend\database.py") -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
Test-Item "database.py has users table" ($dbContent -match "CREATE TABLE.*users")
Test-Item "database.py has platforms table" ($dbContent -match "CREATE TABLE.*platforms")
Test-Item "database.py has tasks table" ($dbContent -match "CREATE TABLE.*tasks \(")
Test-Item "database.py has task_steps table" ($dbContent -match "CREATE TABLE.*task_steps")
Test-Item "database.py has platform_tasks table" ($dbContent -match "CREATE TABLE.*platform_tasks")
Test-Item "database.py has task_logs table" ($dbContent -match "CREATE TABLE.*task_logs")

$authContent = Get-Content (Join-Path $root "backend\middleware\auth.py") -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
Test-Item "auth middleware has JWT" ($authContent -match "JWT|jwt|token")

# Pipeline checks using ASCII keywords only
$pipeContent = Get-Content (Join-Path $root "backend\routers\pipeline.py") -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
Test-Item "pipeline has create_task" ($pipeContent -match "create_task|CreateTask")
Test-Item "pipeline has step 2 (copy)" ($pipeContent -match "step/2|generate.*copy|copywrite")
Test-Item "pipeline has step 3 (rename)" ($pipeContent -match "step/3|rename")
Test-Item "pipeline has step 4 (cover)" ($pipeContent -match "step/4|cover")
Test-Item "pipeline has step 5 (watermark)" ($pipeContent -match "step/5|watermark")
Test-Item "pipeline has step 6 (publish)" ($pipeContent -match "step/6|publish")

$reqContent = Get-Content (Join-Path $root "backend\requirements.txt") -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
Test-Item "requirements has fastapi" ($reqContent -match "fastapi")
Test-Item "requirements has aiosqlite" ($reqContent -match "aiosqlite")
Test-Item "requirements has PyJWT" ($reqContent -match "PyJWT")
Test-Item "requirements has Pillow" ($reqContent -match "Pillow")

$dockerContent = Get-Content (Join-Path $root "Dockerfile") -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
Test-Item "Dockerfile has Python base" ($dockerContent -match "python:")
Test-Item "Dockerfile has ffmpeg" ($dockerContent -match "ffmpeg")
Test-Item "Dockerfile exposes port" ($dockerContent -match "EXPOSE")

# ═══ 8. Security Checks ═══
Write-Host ""
Write-Host "=== 8. Security Checks ===" -ForegroundColor White

$allPy = Get-ChildItem -Path (Join-Path $root "backend") -Filter "*.py" -Recurse
$foundSecrets = $false
foreach ($f in $allPy) {
    if ($f.Name -match "test|selftest|seed|migration") { continue }
    $content = Get-Content $f.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($content -match "sk-[a-zA-Z0-9]{20,}" -or $content -match "AKIA[A-Z0-9]{16}") {
        Write-Host "  [WARN] Potential secret in $($f.Name)" -ForegroundColor Yellow
        $script:warns += "Potential secret in $($f.Name)"
        $foundSecrets = $true
    }
}
if (-not $foundSecrets) { Test-OK "No hardcoded secrets found" }

$gitignore = Get-Content (Join-Path $root ".gitignore") -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
Test-Item ".gitignore excludes data" ($gitignore -match "data")
Test-Item ".gitignore excludes __pycache__" ($gitignore -match "__pycache__")
Test-Item ".gitignore excludes config.json" ($gitignore -match "config\.json")

# ═══ Results ═══
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  RESULTS" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PASSED: $pass" -ForegroundColor Green
if ($fail -gt 0) {
    Write-Host "  FAILED: $fail" -ForegroundColor Red
} else {
    Write-Host "  FAILED: 0" -ForegroundColor Green
}
if ($warns.Count -gt 0) {
    Write-Host "  WARNS:  $($warns.Count)" -ForegroundColor Yellow
} else {
    Write-Host "  WARNS:  0" -ForegroundColor Green
}
$total = $pass + $fail
Write-Host "  TOTAL:  $total" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Cyan

if ($fail -eq 0) {
    Write-Host ""
    Write-Host "  ALL CHECKS PASSED" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "  $fail checks failed - fix before deployment." -ForegroundColor Red
}

Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Gray
Write-Host "    With Python:  cd backend && python tests\run_selftest.py" -ForegroundColor Gray
Write-Host "    With Docker:  docker compose up --build" -ForegroundColor Gray
Write-Host "    No env:       results above confirm file integrity" -ForegroundColor Gray
Write-Host ""
