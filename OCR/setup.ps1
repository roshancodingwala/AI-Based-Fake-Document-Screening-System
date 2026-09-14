<#
    Digital Identity Verifier - one-shot setup (CPU only)
    Run:   powershell -ExecutionPolicy Bypass -File setup.ps1
    Usage: .\setup.ps1 -SkipVerify        # skip the offline demo run
           .\setup.ps1 -Backend paddle    # also exercise an online real-OCR check
#>
param(
    [switch]$SkipVerify,
    [ValidateSet("paddle", "mock")]
    [string]$Backend = "mock"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Digital Identity Verifier - setup (CPU)"   -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# -- 1. Find a usable Python interpreter (prefer 3.11) -----------------------
$pyExe = $null
$pyArgs = @()
$pyVersion = ""
$candidates = @(@("python"), @("py", "-3.11"), @("py"))
foreach ($call in $candidates) {
    $head = $call[0]
    $tail = @()
    if ($call.Count -gt 1) { $tail = $call[1..($call.Count - 1)] }
    try {
        $out = & $head @tail -c "import sys; print(sys.version.split()[0])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            $pyExe = $head
            $pyArgs = $tail
            $pyVersion = ($out | Select-Object -First 1).Trim()
            break
        }
    } catch { }
}

if (-not $pyExe) {
    Write-Host "[ERROR] No Python found." -ForegroundColor Red
    Write-Host "        Install Python 3.11 from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "        and TICK 'Add python.exe to PATH', then re-run this script."
    exit 1
}
if ($pyVersion -notlike "3.11*") {
    Write-Host "[1/4] Python $pyVersion detected (warn: 3.11 expected; may still work)." -ForegroundColor Yellow
} else {
    Write-Host "[1/4] Python $pyVersion detected."
}

# -- 2. Virtual environment ---------------------------------------------------
Write-Host "[2/4] Creating virtual environment..."
$venvDir = Join-Path $root "venv"
if (-not (Test-Path $venvDir)) {
    & $pyExe @pyArgs -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] venv creation failed." -ForegroundColor Red; exit 1 }
} else {
    Write-Host "      venv already exists, reusing it."
}
$venvPy = Join-Path $venvDir "Scripts\python.exe"

# -- 3. Dependencies ----------------------------------------------------------
Write-Host "[3/4] Installing dependencies (downloads ~500 MB; give it several minutes)..." -ForegroundColor Cyan
& $venvPy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] pip upgrade failed." -ForegroundColor Red; exit 1 }
& $venvPy -m pip install -r (Join-Path $root "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] pip install failed. Check internet and retry." -ForegroundColor Red
    Write-Host "        If paddleocr fails, try separately:" -ForegroundColor Yellow
    Write-Host "        & '$venvPy' -m pip install paddlepaddle==2.6.2" -ForegroundColor Yellow
    Write-Host "        & '$venvPy' -m pip install paddleocr==2.9.1" -ForegroundColor Yellow
    exit 1
}

# -- 4. Verify ----------------------------------------------------------------
Write-Host "[4/4] Verifying installation (offline mock run)..." -ForegroundColor Cyan
if ($SkipVerify) {
    Write-Host "      skipped (-SkipVerify)."
} else {
    & $venvPy "manual_check.py" --front "fakeadh.jpg" --back "adhard.jpg" --backend $Backend
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARNING] verification run had errors - paste the output above to the project owner." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "SUCCESS. To run the real check:" -ForegroundColor Green
Write-Host "   & '$venvPy' '$root\manual_check.py' --front aadharc.jpg --back adhard.jpg"
Write-Host ""
Write-Host "NOTE: the first real OCR run downloads ~16 MB of models (internet needed once)."
Write-Host "      For a fully offline demo:  ... --backend mock"
Read-Host -Prompt "Press Enter to close"