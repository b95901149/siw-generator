# Build SIW-Generator.exe (isolated venv + PyInstaller)
# Output: dist/SIW-Generator_{version}/ full package
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$Venv = Join-Path $Root ".venv-build"
$Py = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Host "Creating build venv..."
    & C:\ProgramData\anaconda3\python.exe -m venv $Venv
}

Write-Host "Installing dependencies..."
& $Py -m pip install -q --upgrade pip
& $Py -m pip install -q -e ".[cst]"
& $Py -m pip install -q pyinstaller

$Version = (& $Py -c "from siw_generator import __version__; print(__version__)").Trim()
$PackageName = "SIW-Generator_$Version"
$PackageDir = Join-Path $Root "dist\$PackageName"

Write-Host "Version: $Version"
Write-Host "Package: $PackageDir"

Write-Host "Generating guide images..."
$env:MPLBACKEND = "Agg"
$env:OPENBLAS_NUM_THREADS = "1"
$guideScript = Join-Path $Root "scripts\generate_guide_images.py"
if (Test-Path $guideScript) {
    & $Py $guideScript
} else {
    Write-Host "  (skip: generate_guide_images.py not found)"
}

Write-Host "Building SIW-Generator.exe..."
$outExe = Join-Path $Root "dist\SIW-Generator.exe"
if (Get-Process -Name "SIW-Generator" -ErrorAction SilentlyContinue) {
    Write-Error "Please close SIW-Generator.exe before rebuilding."
}
& $Py -m PyInstaller --noconfirm --clean siw_generator.spec

$exe = $outExe
if (-not (Test-Path $exe)) {
    Write-Error "Build failed: $exe not found"
}

$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "Built: $exe ($size MB)"

if (Test-Path $PackageDir) {
    Remove-Item -Recurse -Force $PackageDir
}
New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null

Copy-Item -Force $exe (Join-Path $PackageDir "SIW-Generator.exe")

# docs
$docsDest = Join-Path $PackageDir "docs"
New-Item -ItemType Directory -Force -Path $docsDest | Out-Null
Copy-Item -Force (Join-Path $Root "docs\AGENT_HISTORY.md") (Join-Path $docsDest "AGENT_HISTORY.md")
Copy-Item -Force (Join-Path $Root "docs\USER_GUIDE.md") (Join-Path $docsDest "USER_GUIDE.md")
if (Test-Path (Join-Path $Root "docs\images")) {
    Copy-Item -Recurse -Force (Join-Path $Root "docs\images") (Join-Path $docsDest "images")
}

# user data from dev tree
function Copy-TreeJson {
    param([string]$SrcDir, [string]$DestDir)
    New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
    if (Test-Path $SrcDir) {
        Get-ChildItem -Path $SrcDir -File | Copy-Item -Destination $DestDir -Force
    }
}

Copy-TreeJson (Join-Path $Root "recipe") (Join-Path $PackageDir "recipe")
Copy-TreeJson (Join-Path $Root "module") (Join-Path $PackageDir "module")
Copy-TreeJson (Join-Path $Root "combination") (Join-Path $PackageDir "combination")

New-Item -ItemType Directory -Force -Path (Join-Path $PackageDir "CST") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PackageDir "log") | Out-Null

$buildTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$versionText = @"
SIW Via Generator
Version: $Version
Build: $buildTime
Package: $PackageName

Milestone release - keep this folder to roll back to 0.9.1beta.
"@
Set-Content -Path (Join-Path $PackageDir "VERSION.txt") -Value $versionText -Encoding UTF8

Write-Host "Done: $PackageDir"
Write-Host "  recipe:  $((Get-ChildItem (Join-Path $PackageDir 'recipe') -File -ErrorAction SilentlyContinue).Count) files"
Write-Host "  module:  $((Get-ChildItem (Join-Path $PackageDir 'module') -File -ErrorAction SilentlyContinue).Count) files"
Write-Host "  combination: $((Get-ChildItem (Join-Path $PackageDir 'combination') -File -ErrorAction SilentlyContinue).Count) files"
