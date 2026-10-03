$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ProjectDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPythonw = Join-Path $VenvDir "Scripts\pythonw.exe"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

try {
    $PythonLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($PythonLauncher) {
        $PythonCommand = $PythonLauncher.Source
        $PythonPrefix = @("-3")
    } else {
        $PythonLauncher = Get-Command "python.exe" -ErrorAction SilentlyContinue
        if (-not $PythonLauncher) {
            throw "Python was not found. Install Python 3.10 or later, then run install.bat again."
        }
        $PythonCommand = $PythonLauncher.Source
        $PythonPrefix = @()
    }

    Write-Step "Checking Python"
    $VersionText = & $PythonCommand @PythonPrefix --version 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or $VersionText -notmatch "Python\s+(\d+)\.(\d+)") {
        throw "Could not determine the Python version."
    }
    $PythonMajor = [int]$Matches[1]
    $PythonMinor = [int]$Matches[2]
    if ($PythonMajor -lt 3 -or ($PythonMajor -eq 3 -and $PythonMinor -lt 10)) {
        throw "Python 3.10 or later is required. Detected: $($VersionText.Trim())"
    }
    Write-Host $VersionText.Trim()

    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Write-Step "Creating virtual environment"
        & $PythonCommand @PythonPrefix -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment." }
    } else {
        Write-Step "Existing virtual environment detected"
    }

    Write-Step "Installing dependencies"
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }
    & $VenvPython -m pip install -r (Join-Path $ProjectDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Could not install the application dependencies." }

    if (-not (Test-Path -LiteralPath $VenvPythonw)) {
        throw "pythonw.exe was not found in the virtual environment. Check your Python installation."
    }

    Write-Step "Creating desktop shortcut"
    $Desktop = [Environment]::GetFolderPath("Desktop")
    if (-not $Desktop -or -not (Test-Path -LiteralPath $Desktop)) {
        throw "Could not find the Windows Desktop folder."
    }
    $ShortcutPath = Join-Path $Desktop "Frame Extractor.lnk"
    $MainScript = Join-Path $ProjectDir "main.py"
    $IconPath = Join-Path $ProjectDir "icon.ico"
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $VenvPythonw
    $Shortcut.Arguments = "`"$MainScript`""
    $Shortcut.WorkingDirectory = $ProjectDir
    if (Test-Path -LiteralPath $IconPath) { $Shortcut.IconLocation = $IconPath }
    $Shortcut.Description = "Frame Extractor - Save frames and create video clips"
    $Shortcut.Save()
    if (-not (Test-Path -LiteralPath $ShortcutPath -PathType Leaf)) {
        throw "Windows did not create the desktop shortcut at: $ShortcutPath"
    }
    Write-Host "Desktop shortcut created and verified: $ShortcutPath" -ForegroundColor Green

    if (-not (Get-Command "ffmpeg.exe" -ErrorAction SilentlyContinue) -or
        -not (Get-Command "ffprobe.exe" -ErrorAction SilentlyContinue)) {
        Write-Host "Warning: FFmpeg/FFprobe are not on PATH. The app will run, but clip export will be unavailable." -ForegroundColor Yellow
    }

    Write-Host "`nInstallation complete." -ForegroundColor Green
    exit 0
} catch {
    Write-Host "`nInstallation error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
