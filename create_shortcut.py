import os
import sys
import subprocess

# Base paths
project_dir = os.path.dirname(os.path.abspath(__file__))
main_py = os.path.join(project_dir, "main.py")
icon_ico = os.path.join(project_dir, "icon.ico")

# Desktop path resolution
desktop = os.path.join(os.path.expanduser("~"), "Desktop")
if not os.path.exists(desktop):
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        desktop, _ = winreg.QueryValueEx(key, "Desktop")
        desktop = os.path.expandvars(desktop)
    except Exception:
        pass

shortcut_path = os.path.join(desktop, "Frame Extractor.lnk")

# Determine pythonw.exe
python_exe = sys.executable
if python_exe.lower().endswith("python.exe"):
    pythonw_exe = python_exe[:-10] + "pythonw.exe"
    if not os.path.exists(pythonw_exe):
        pythonw_exe = python_exe
else:
    pythonw_exe = python_exe

# If in a virtualenv created by uv, replace the uv launcher with official CPython venv pythonw.exe
try:
    import shutil
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(pythonw_exe)), "pyvenv.cfg")
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = f.read()
        for line in cfg.splitlines():
            if line.startswith("home ="):
                home_dir = line.split("=", 1)[1].strip()
                official_nt = os.path.join(home_dir, "Lib", "venv", "scripts", "nt", "pythonw.exe")
                if os.path.exists(official_nt) and os.path.getsize(pythonw_exe) != os.path.getsize(official_nt):
                    shutil.copy2(official_nt, pythonw_exe)
                    break
except Exception:
    pass

# Ensure pythonw.exe PE header is GUI subsystem (Windows subsystem 2, not CUI console 3)
try:
    import struct
    if os.path.exists(pythonw_exe):
        with open(pythonw_exe, "r+b") as f:
            data = f.read(1024)
            pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
            subsystem_offset = pe_offset + 24 + 68
            f.seek(subsystem_offset)
            subsystem = struct.unpack("<H", f.read(2))[0]
            if subsystem != 2:
                f.seek(subsystem_offset)
                f.write(struct.pack("<H", 2))
except Exception:
    pass

# Remove old shortcut if exists
if os.path.exists(shortcut_path):
    try:
        os.remove(shortcut_path)
    except Exception:
        pass

created = False

# Try pywin32 COM first
try:
    from win32com.client import Dispatch
    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.TargetPath = pythonw_exe
    shortcut.Arguments = f'"{main_py}"'
    shortcut.WorkingDirectory = project_dir
    shortcut.IconLocation = icon_ico
    shortcut.Description = "Frame Extractor - Extrae frames de videos"
    shortcut.save()
    created = True
    print(f"Acceso directo creado mediante COM: {shortcut_path}")
except Exception as e:
    print(f"COM fallback: {e}")

# PowerShell fallback
if not created:
    ps_script = f"""
$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut('{shortcut_path}')
$Shortcut.TargetPath = '{pythonw_exe}'
$Shortcut.Arguments = '"{main_py}"'
$Shortcut.WorkingDirectory = '{project_dir}'
$Shortcut.IconLocation = '{icon_ico}'
$Shortcut.Description = 'Frame Extractor - Extrae frames de videos'
$Shortcut.Save()
"""
    result = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Acceso directo creado mediante PowerShell: {shortcut_path}")
    else:
        print(f"Error al crear acceso directo: {result.stderr}")

# Refresh Windows Explorer icon cache
try:
    subprocess.run(["powershell", "-NoProfile", "-Command", "ie4uinit.exe -show"], capture_output=True)
    subprocess.run(["powershell", "-NoProfile", "-Command", "(New-Object -ComObject Shell.Application).Namespace(0x10).Self.InvokeVerb('Refresh')"], capture_output=True)
except Exception:
    pass

print("¡Listo!")
