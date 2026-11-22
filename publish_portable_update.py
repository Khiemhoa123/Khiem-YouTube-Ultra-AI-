# -*- coding: utf-8 -*-
"""Publish a tested Portable binary update to GitHub Releases.
Requires GitHub CLI installed and authenticated: gh auth login
Usage: python publish_portable_update.py v11.4
"""
import hashlib, json, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DIST=ROOT/"dist_portable"/"KhiemYoutube"
REPO="Khiemhoa123/Khiem-YouTube-Ultra-AI-"
def digest(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()
def main():
    if len(sys.argv)!=2 or not sys.argv[1].startswith("v"):
        raise SystemExit("Usage: python publish_portable_update.py v11.4")
    version=sys.argv[1]
    if not (DIST/"KhiemYoutube.exe").is_file():
        raise RuntimeError("Chưa build Portable. Chạy python build_portable.py trước.")
    if not shutil.which("gh"):
        raise RuntimeError("Cần GitHub CLI (gh) và đăng nhập bằng gh auth login.")
    with tempfile.TemporaryDirectory(prefix="khiem_release_") as tmp:
        folder=Path(tmp)
        archive=folder/"portable_update.zip"
        with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for file in DIST.rglob("*"):
                if not file.is_file():continue
                rel=file.relative_to(DIST)
                if any(p in ("models","tools") for p in rel.parts):continue
                if rel.parts[0] in ("_PORTABLE_BACKUP",):continue
                if file.name in ("KhiemUpdater.exe","portable_version.txt","khiem_settings.json","project_queue_v11.json"):continue
                z.write(file,rel.as_posix())
        manifest=folder/"portable_manifest.json"
        manifest.write_text(json.dumps({"version":version,"zip_sha256":digest(archive)},indent=2),encoding="utf-8")
        command=["gh","release","create",version,str(archive),str(manifest),
                 "--repo",REPO,"--title","Khiem Youtube "+version,
                 "--notes","Portable binary update. AI models and FFmpeg remain installed locally.",
                 "--latest"]
        print("Đang tải bản cập nhật lên GitHub Releases...")
        subprocess.run(command,check=True)
        print("PUBLISHED:",version)
if __name__=="__main__":main()
