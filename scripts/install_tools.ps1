# Choi Studio - installs the external tools WITHOUT winget or admin rights.
#   -Node   : portable Node.js LTS  -> tools\node
#   -Ffmpeg : portable FFmpeg (GPL build with NVENC + zimg) -> tools\ffmpeg
#   -Python : official Python 3.12 installer, per-user (%LOCALAPPDATA%\Programs\Python\Python312)
# Called by setup_windows.bat. Messages are ASCII on purpose (Windows PowerShell 5.1 encoding).
param(
  [string]$Root = (Split-Path -Parent $PSScriptRoot),
  [switch]$Node,
  [switch]$Ffmpeg,
  [switch]$Python
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is very slow with the progress bar
try {
  [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {}

$tools = Join-Path $Root 'tools'
$dl = Join-Path $tools '_downloads'
New-Item -ItemType Directory -Force -Path $dl | Out-Null

function Get-File([string]$url, [string]$dest) {
  Write-Host "    download: $url"
  $tmp = "$dest.part"
  if (Test-Path $tmp) { Remove-Item -Force $tmp }
  $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
  if ($curl) {
    & $curl.Source -L --fail --retry 3 --retry-delay 3 -o $tmp $url
    if ($LASTEXITCODE -ne 0) { throw "download failed ($LASTEXITCODE): $url" }
  } else {
    Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
  }
  Move-Item -Force $tmp $dest
}

function Expand-Zip([string]$zip, [string]$dest) {
  if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  $tar = Get-Command tar.exe -ErrorAction SilentlyContinue
  if ($tar) {
    & $tar.Source -xf $zip -C $dest
    if ($LASTEXITCODE -eq 0) { return }
  }
  Expand-Archive -Force -Path $zip -DestinationPath $dest
}

function Install-Node {
  Write-Host '[Node.js] looking up the latest LTS version...'
  $index = Invoke-RestMethod -UseBasicParsing -Uri 'https://nodejs.org/dist/index.json'
  $rel = $index | Where-Object { $_.lts -and ($_.files -contains 'win-x64-zip') } | Select-Object -First 1
  if (-not $rel) { throw 'could not find a Node.js LTS release' }
  $v = $rel.version
  $name = "node-$v-win-x64"
  $zip = Join-Path $dl "$name.zip"
  if (-not (Test-Path $zip)) { Get-File "https://nodejs.org/dist/$v/$name.zip" $zip }
  $tmp = Join-Path $tools '_node_tmp'
  Expand-Zip $zip $tmp
  $target = Join-Path $tools 'node'
  if (Test-Path $target) { Remove-Item -Recurse -Force $target }
  Move-Item (Join-Path $tmp $name) $target
  Remove-Item -Recurse -Force $tmp
  Remove-Item -Force $zip   # keep the folder small once installed
  Write-Host "[Node.js] $v installed -> $target"
}

function Install-Ffmpeg {
  $urls = @(
    'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n9.0-latest-win64-gpl-9.0.zip',
    'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n8.1-latest-win64-gpl-8.1.zip',
    'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip',
    'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
  )
  $zip = Join-Path $dl 'ffmpeg.zip'
  if (-not (Test-Path $zip)) {
    $ok = $false
    foreach ($u in $urls) {
      try { Get-File $u $zip; $ok = $true; break } catch { Write-Host "    failed, trying the next mirror: $($_.Exception.Message)" }
    }
    if (-not $ok) { throw 'FFmpeg download failed from every mirror' }
  }
  $tmp = Join-Path $tools '_ffmpeg_tmp'
  Expand-Zip $zip $tmp
  $exe = Get-ChildItem -Path $tmp -Recurse -Filter 'ffmpeg.exe' | Select-Object -First 1
  if (-not $exe) { throw 'ffmpeg.exe not found inside the archive' }
  $top = $exe.Directory.Parent.FullName
  $target = Join-Path $tools 'ffmpeg'
  if (Test-Path $target) { Remove-Item -Recurse -Force $target }
  Move-Item $top $target
  Remove-Item -Recurse -Force $tmp
  Remove-Item -Force $zip
  Write-Host "[FFmpeg] installed -> $target\bin"
}

function Install-Python {
  $ver = '3.12.10'
  $exe = Join-Path $dl "python-$ver-amd64.exe"
  if (-not (Test-Path $exe)) { Get-File "https://www.python.org/ftp/python/$ver/python-$ver-amd64.exe" $exe }
  Write-Host "[Python] installing $ver for the current user (1-3 minutes)..."
  $pyArgs = @('/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_test=0', 'Include_launcher=1',
            'InstallLauncherAllUsers=0', 'SimpleInstall=1')
  $p = Start-Process -FilePath $exe -ArgumentList $pyArgs -Wait -PassThru
  if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { throw "Python installer failed (exit code $($p.ExitCode))" }
  Remove-Item -Force $exe
  Write-Host "[Python] $ver installed -> $env:LOCALAPPDATA\Programs\Python\Python312"
}

try {
  if ($Python) { Install-Python }
  if ($Node) { Install-Node }
  if ($Ffmpeg) { Install-Ffmpeg }
  exit 0
} catch {
  Write-Host ''
  Write-Host "[ERROR] $($_.Exception.Message)"
  Write-Host 'Check the internet connection (school/company networks may block downloads) and run setup again.'
  exit 1
}
