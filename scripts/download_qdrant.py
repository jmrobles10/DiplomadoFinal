"""
PitWall · Descarga el binario oficial de Qdrant para Windows (releases de GitHub) en tools/qdrant/qdrant.exe.

Uso: python scripts/download_qdrant.py
"""
import io
import json
import os
import sys
import urllib.request
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "tools", "qdrant")
UA = {"User-Agent": "PitWall-RAG-F1/1.0", "Accept": "application/vnd.github+json"}


def main():
    os.makedirs(DEST, exist_ok=True)
    exe = os.path.join(DEST, "qdrant.exe")
    if os.path.exists(exe):
        print("Ya existe", exe); return
    rel = json.load(urllib.request.urlopen(urllib.request.Request("https://api.github.com/repos/qdrant/qdrant/releases/latest", headers=UA), timeout=60))
    asset = next(a for a in rel["assets"] if "x86_64-pc-windows-msvc" in a["name"] and a["name"].endswith(".zip"))
    print(f"Descargando Qdrant {rel['tag_name']} ({asset['size']/1e6:.0f} MB)...")
    data = urllib.request.urlopen(urllib.request.Request(asset["browser_download_url"], headers=UA), timeout=600).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(DEST)
    print("Listo:", exe)


if __name__ == "__main__":
    main()
