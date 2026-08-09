# =====================================================================
# CyberRisk AI — Docker deployment validation (Windows PowerShell)
#
# Verifies (from the repo root):
#   1. The Docker image builds successfully.
#   2. The container starts and stays healthy.
#   3. The API responds (GET /api/health).
#   4. The AI agent loads.
#   5. The risk engine executes.
#   6. RAG retrieval works.
#   7. Environment variables are injected at runtime (and no key is baked).
#
# Usage:
#   .\docker\validate\validate.ps1 [-NoBuild]
#
#   -NoBuild   reuse an existing cyberrisk:latest image instead of rebuilding
#
# Exit code 0 = all checks passed; nonzero otherwise.
#
# Bash users on macOS/Linux: run docker/validate/validate.sh instead.
# =====================================================================

param([switch]$NoBuild)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $RepoRoot

$Image = "cyberrisk:latest"
$Ctn   = "cyberrisk-validate"
$Net   = "cyberrisk-validate-net"
$Smoke = "docker\validate\smoke_test.py"

$Pass = 0
$Fail = 0

function Pass([string]$msg) { $script:Pass++; Write-Host "  [PASS] $msg" }
function Fail([string]$msg) { $script:Fail++; Write-Host "  [FAIL] $msg" }

function Cleanup {
    # Removing a non-existent container/network is normal on first run; the
    # error must not trip the trap (which would exit before the build starts).
    try {
        & docker rm -f $Ctn 2>$null | Out-Null
    } catch { }
    try {
        & docker network rm $Net 2>$null | Out-Null
    } catch { }
}
trap { Cleanup; exit 1 }
Cleanup

# ----------------------------------------------------------------------
# 1. Image builds
# ----------------------------------------------------------------------
Write-Host "== [1/7] Building image $Image =="
$skipBuild = $false
if ($NoBuild) {
    # Reuse an existing image when requested and one is present.  Check with
    # docker image inspect, swallowing its exit code (0 = image exists).
    & docker image inspect $Image 2>$null | Out-Null
    $skipBuild = ($LASTEXITCODE -eq 0)
}
if ($skipBuild) {
    Pass "image already exists (-NoBuild)"
} else {
    & docker build -t $Image . | Tee-Object -FilePath "$env:TEMP\cyberrisk-build.log" | Out-Host
    if ($LASTEXITCODE -eq 0) { Pass "docker build -t $Image ." }
    else {
        Fail "docker build failed"
        Get-Content "$env:TEMP\cyberrisk-build.log" -Tail 30
        exit 1
    }
}

# ----------------------------------------------------------------------
# 2. Container starts (and stays healthy)
# ----------------------------------------------------------------------
Write-Host "`n== [2/7] Starting container =="
& docker network create $Net 2>$null | Out-Null
& docker run -d --rm --name $Ctn --network $Net -p 18000:8000 `
    -v "${RepoRoot}\knowledge\corpus:/app/knowledge/corpus:ro" `
    -v "${RepoRoot}\knowledge\manifests:/app/knowledge/manifests:ro" `
    -v "${RepoRoot}\data\output:/app/data/output" `
    $Image | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "container failed to start"; exit 1 }
Pass "container started"

$healthy = $false
foreach ($i in 1..60) {
    $state = & docker inspect -f '{{.State.Health.Status}}' $Ctn 2>$null
    if ($state -eq "healthy")   { $healthy = $true; break }
    if ($state -eq "unhealthy") { break }
    Start-Sleep -Seconds 2
}
if ($healthy) { Pass "container healthy" }
else {
    Fail "container not healthy (state: $state)"
    & docker logs $Ctn 2>&1 | Select-Object -Last 30
    exit 1
}

# ----------------------------------------------------------------------
# 3. API responds
# ----------------------------------------------------------------------
Write-Host "`n== [3/7] API health check =="
$apiOk = $false
foreach ($i in 1..20) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:18000/api/health" -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) { $body = $resp.Content; $apiOk = $true; break }
    } catch { Start-Sleep -Seconds 1 }
}
if ($apiOk) { Pass "GET /api/health -> $body" }
else {
    Fail "API did not respond at http://127.0.0.1:18000/api/health"
    & docker logs $Ctn 2>&1 | Select-Object -Last 20
    exit 1
}

# ----------------------------------------------------------------------
# 4-7. Agent / engine / RAG / env - in-container smoke test
# ----------------------------------------------------------------------
Write-Host "`n== [4-7] In-container smoke test (agent, engine, RAG, env) =="
& docker run --rm --name "${Ctn}-smoke" --network $Net `
    -v "${RepoRoot}\config:/app/config:ro" `
    -v "${RepoRoot}\knowledge\corpus:/app/knowledge/corpus:ro" `
    -v "${RepoRoot}\knowledge\manifests:/app/knowledge/manifests:ro" `
    -v "${RepoRoot}\data\output:/app/data/output" `
    -v "${RepoRoot}\${Smoke}:/app/smoke_test.py:ro" `
    -e "LLM_PROVIDER=deepseek" `
    $Image python /app/smoke_test.py
if ($LASTEXITCODE -eq 0) { Pass "in-container smoke test passed" }
else { Fail "in-container smoke test failed"; exit 1 }

# ----------------------------------------------------------------------
# Env vars load from .env (runtime injection), if present.
# ----------------------------------------------------------------------
$envPath = Join-Path $RepoRoot ".env"
if (Test-Path $envPath) {
    Write-Host "`n== [env] .env present - verifying runtime injection =="
    & docker run --rm --name "${Ctn}-env" `
        -v "${RepoRoot}\${Smoke}:/app/smoke_test.py:ro" `
        --env-file $envPath `
        $Image python /app/smoke_test.py | Tee-Object -FilePath "$env:TEMP\cyberrisk-env.log" | Out-Host
    if ($LASTEXITCODE -eq 0) { Pass "env vars injected via --env-file" }
    else { Fail "env-file run failed"; Get-Content "$env:TEMP\cyberrisk-env.log" -Tail 20; exit 1 }
} else {
    Write-Host "`n== [env] .env absent - skipping .env injection check (engine still offline) =="
}

# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------
Write-Host "`n=========================================="
Write-Host "Docker validation: $Pass passed, $Fail failed"
Write-Host "=========================================="
Cleanup
if ($Fail -eq 0) { exit 0 } else { exit 1 }
