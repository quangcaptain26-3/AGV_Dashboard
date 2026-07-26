# build.ps1 - Build AGV_Analyzer thanh .exe (onedir)
#
# LY DO CO SCRIPT NAY:
#   PyInstaller loi khi duong dan du an chua ky tu co dau (vd "Du an CNTT").
#   Script tu dong build tai mot thu muc ASCII (%USERPROFILE%\agv_build) roi
#   chep ket qua ve thu muc dist cua du an.
#
# CACH DUNG (tu thu muc goc du an hoac bat ky dau):
#   powershell -ExecutionPolicy Bypass -File agv_app\build\build.ps1

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

# Thu muc goc du an = cha cua 'agv_app' (PSScriptRoot = ...\agv_app\build)
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$BuildRoot   = Join-Path $env:USERPROFILE "agv_build"

Write-Host "Project root : $ProjectRoot"
Write-Host "Build root   : $BuildRoot"

# 1. Chuan bi thu muc build ASCII
if (Test-Path $BuildRoot) { Remove-Item $BuildRoot -Recurse -Force }
New-Item -ItemType Directory -Path $BuildRoot | Out-Null
Copy-Item (Join-Path $ProjectRoot "agv_app") (Join-Path $BuildRoot "agv_app") -Recurse

# 2. Tao venv (uu tien 3.10, fallback 3.9 / 3.8 neu may chua cai 3.10)
$venvName = ".venv310"
$pyLauncher = $null
foreach ($ver in @("3.10", "3.11", "3.9", "3.8")) {
    try {
        $out = & py "-$ver" -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            $pyLauncher = "-$ver"
            if ($ver -ne "3.10") {
                $venvName = ".venv$($ver.Replace('.',''))"
                Write-Host "Canh bao: khong tim thay Python 3.10, dung Python $ver"
            }
            break
        }
    } catch { }
}
if (-not $pyLauncher) {
    throw "Khong tim thay Python 3.8+. Hay cai Python 3.10 (khuyen nghi) roi chay lai."
}

Write-Host "== Tao venv Python ($pyLauncher) tai $venvName =="
py $pyLauncher -m venv (Join-Path $BuildRoot $venvName)
$py = Join-Path $BuildRoot "$venvName\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r (Join-Path $BuildRoot "agv_app\requirements.txt")

# 3. Build
Write-Host "== PyInstaller build =="
Push-Location $BuildRoot
& (Join-Path $BuildRoot "$venvName\Scripts\pyinstaller.exe") "agv_app\build\agv_app.spec" --noconfirm
Pop-Location

# 4. Chep ket qua ve du an
$srcDist = Join-Path $BuildRoot "dist\AGV_Analyzer"
$dstDist = Join-Path $ProjectRoot "dist\AGV_Analyzer"
if (Test-Path $dstDist) { Remove-Item $dstDist -Recurse -Force }
New-Item -ItemType Directory -Path (Split-Path $dstDist) -Force | Out-Null
Copy-Item $srcDist $dstDist -Recurse

Write-Host ""
Write-Host "HOAN TAT! App o: $dstDist\AGV_Analyzer.exe"
