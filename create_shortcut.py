import os, sys

desktop = r'C:\Users\Manuel\Desktop'
shortcut_path = os.path.join(desktop, 'Frame Extractor.lnk')
target = r'C:\Users\Manuel\Documents\antigravity\blissful-hypatia\frame-extractor\main.py'
icon = r'C:\Users\Manuel\Documents\antigravity\blissful-hypatia\frame-extractor\icon.ico'
work_dir = r'C:\Users\Manuel\Documents\antigravity\blissful-hypatia\frame-extractor'

python_exe = sys.executable
if python_exe.lower().endswith("python.exe"):
    pythonw_exe = python_exe[:-10] + "pythonw.exe"
else:
    pythonw_exe = python_exe

if os.path.exists(shortcut_path):
    try:
        os.remove(shortcut_path)
    except Exception:
        pass

try:
    from win32com.client import Dispatch
    use_com = True
except ImportError:
    use_com = False

if use_com:
    shell = Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.Targetpath = pythonw_exe
    shortcut.Arguments = f'"{target}"'
    shortcut.WorkingDirectory = work_dir
    # Set IconLocation to the .ico path directly (WITHOUT ,0)
    shortcut.IconLocation = icon
    shortcut.Description = 'Frame Extractor - Extrae frames de videos'
    shortcut.save()
    print(f'Shortcut created via COM: {shortcut_path}')
else:
    import subprocess
    ps_script = f"""
$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut('{shortcut_path}')
$Shortcut.TargetPath = '{pythonw_exe}'
$Shortcut.Arguments = '"{target}"'
$Shortcut.WorkingDirectory = '{work_dir}'
$Shortcut.IconLocation = '{icon}'
$Shortcut.Description = 'Frame Extractor - Extrae frames de videos'
$Shortcut.Save()
"""
    subprocess.run(['powershell', '-NoProfile', '-Command', ps_script])
    print('Shortcut created via PowerShell')

# Force Windows Explorer refresh
import subprocess
subprocess.run(["powershell", "-NoProfile", "-Command", "ie4uinit.exe -show"], capture_output=True)
subprocess.run(["powershell", "-NoProfile", "-Command", "(New-Object -ComObject Shell.Application).Namespace(0x10).Self.InvokeVerb('Refresh')"], capture_output=True)

print("Done!")
