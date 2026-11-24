"""Locate the external tools on Windows, macOS or Linux. Reads only; installs nothing."""
import glob
import json
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
MAC = "/Applications/KiCad/KiCad.app/Contents/"


def first(*patterns):
    for p in patterns:
        hits = sorted(glob.glob(p), reverse=True)
        if hits:
            return hits[0]
    return None


def run(*cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=60)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)


def registry_dirs():
    """KiCad may be installed in any folder; the uninstall entry records which."""
    if os.name != "nt":
        return []
    import winreg
    found = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                base = winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
                                      0, winreg.KEY_READ | view)
            except OSError:
                continue
            for i in range(winreg.QueryInfoKey(base)[0]):
                try:
                    k = winreg.OpenKey(base, winreg.EnumKey(base, i))
                    if winreg.QueryValueEx(k, "DisplayName")[0].startswith("KiCad"):
                        found.append(winreg.QueryValueEx(k, "InstallLocation")[0].strip('"'))
                except OSError:
                    continue
    return found


def find_cli():
    roots = [os.environ.get(k) for k in ("ProgramFiles", "ProgramW6432")]
    if os.environ.get("LOCALAPPDATA"):
        roots.append(os.path.join(os.environ["LOCALAPPDATA"], "Programs"))
    return os.environ.get("KICAD_CLI") or shutil.which("kicad-cli") or first(
        *[os.path.join(r, "KiCad", "*", "bin", "kicad-cli.exe") for r in roots if r],
        *[os.path.join(glob.escape(r), "bin", "kicad-cli.exe") for r in registry_dirs()],
        MAC + "MacOS/kicad-cli")


def find_python(cli):
    if os.environ.get("KICAD_PYTHON"):
        return os.environ["KICAD_PYTHON"]
    if os.name == "nt":
        p = os.path.join(os.path.dirname(cli), "python.exe") if cli else ""
        return p if os.path.exists(p) else None
    if sys.platform == "darwin":
        return first(MAC + "Frameworks/Python.framework/Versions/Current/bin/python3")
    return shutil.which("python3")


cli = find_cli()
kpy = find_python(cli)
java = shutil.which("java")
jar = os.environ.get("FREEROUTING_JAR") or first("freerouting*.jar", "tools/freerouting*.jar",
                                                 "workflow/freerouting*.jar") or shutil.which("freerouting")
out = {"kicad_cli": {"path": cli}, "kicad_python": {"path": kpy},
       "java": {"path": java}, "freerouting": {"path": jar}}
if cli:
    rc, text = run(cli, "version")
    out["kicad_cli"].update(ok=rc == 0, version=text)
if kpy:
    rc, text = run(kpy, "-c", "import pcbnew; print(pcbnew.Version())")
    out["kicad_python"].update(ok=rc == 0, pcbnew=text.splitlines()[-1] if text else "")
if java:
    rc, text = run(java, "-version")
    out["java"].update(ok=rc == 0, version=text.splitlines()[:1])
out["missing"] = [k for k, v in out.items() if not v["path"] or v.get("ok") is False]
out["hint"] = "Set KICAD_CLI, KICAD_PYTHON or FREEROUTING_JAR if a tool is installed elsewhere."
print(json.dumps(out, ensure_ascii=False, indent=2))
sys.exit(1 if out["missing"] else 0)
