# -*- coding: utf-8 -*-
"""Portable binary updater. Downloads a published release, never executes remote Python."""
import hashlib, json, os, shutil, subprocess, sys, tempfile, time, urllib.request, zipfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
REPO = "Khiemhoa123/Khiem-YouTube-Ultra-AI-"
ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
API = "https://api.github.com/repos/" + REPO + "/releases/latest"
def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent":"KhiemYoutube-Updater","Accept":"application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()
def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024),b""): h.update(block)
    return h.hexdigest()
def apply():
    status.set("Đang kiểm tra bản phát hành...")
    window.update_idletasks()
    release=json.loads(fetch(API))
    assets={x["name"]:x for x in release.get("assets",[])}
    if "portable_update.zip" not in assets or "portable_manifest.json" not in assets:
        raise RuntimeError("Chưa có bản cập nhật Portable được phát hành trên GitHub Releases.")
    manifest=json.loads(fetch(assets["portable_manifest.json"]["browser_download_url"]))
    if manifest.get("version") != release.get("tag_name"):
        raise RuntimeError("Manifest không khớp phiên bản phát hành.")
    current=ROOT / "portable_version.txt"
    if current.is_file() and current.read_text(encoding="utf-8").strip()==manifest["version"]:
        messagebox.showinfo("Khiêm Youtube","Phần mềm đã là phiên bản mới nhất.")
        return
    if not messagebox.askyesno("Cập nhật Khiêm Youtube", "Cài phiên bản "+manifest["version"]+"?\nPhải đóng KhiemYoutube.exe trước khi tiếp tục."):
        return
    status.set("Đang tải bản cập nhật. Không tắt cửa sổ này...")
    window.update_idletasks()
    work=Path(tempfile.mkdtemp(prefix="khiem_update_"))
    try:
        archive=work/"update.zip"
        archive.write_bytes(fetch(assets["portable_update.zip"]["browser_download_url"]))
        if sha256(archive)!=manifest.get("zip_sha256"):
            raise RuntimeError("SHA256 không khớp. Hủy cập nhật.")
        stage=work/"stage"
        stage.mkdir()
        with zipfile.ZipFile(archive) as z:
            for member in z.infolist():
                rel=Path(member.filename.replace("\\","/"))
                if member.is_dir(): continue
                if rel.is_absolute() or ".." in rel.parts or not rel.parts:
                    raise RuntimeError("Đường dẫn ZIP không an toàn.")
                if rel.parts[0] in ("models","tools") or rel.name in ("khiem_settings.json","project_queue_v11.json"):
                    continue
                dest=stage.joinpath(*rel.parts)
                dest.parent.mkdir(parents=True,exist_ok=True)
                with z.open(member) as source, dest.open("wb") as target: shutil.copyfileobj(source,target)
        if not (stage/"KhiemYoutube.exe").is_file():
            raise RuntimeError("Bản cập nhật thiếu KhiemYoutube.exe.")
        status.set("Đang đợi ứng dụng đóng...")
        window.update_idletasks()
        # The updater runs as a separate EXE, so the main EXE can be replaced.
        for _ in range(60):
            try:
                with (ROOT/"KhiemYoutube.exe").open("ab"): break
            except PermissionError: time.sleep(1)
        else: raise RuntimeError("Hãy đóng KhiemYoutube.exe rồi thử lại.")
        backup=ROOT/"_PORTABLE_BACKUP"
        backup.mkdir(exist_ok=True)
        changed=[]
        try:
            for src in stage.rglob("*"):
                if not src.is_file(): continue
                rel=src.relative_to(stage)
                dest=ROOT/rel
                if dest.is_file() and sha256(dest)==sha256(src): continue
                old=backup/rel
                old.parent.mkdir(parents=True,exist_ok=True)
                if dest.exists(): shutil.copy2(dest,old)
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(src,dest)
                changed.append((dest,old))
            current.write_text(manifest["version"],encoding="utf-8")
        except Exception:
            for dest,old in reversed(changed):
                if old.exists(): shutil.copy2(old,dest)
                elif dest.exists(): dest.unlink()
            raise
        status.set("Cập nhật thành công: "+manifest["version"])
        messagebox.showinfo("Khiêm Youtube","Đã cập nhật. Mở lại KhiemYoutube.exe.")
    finally: shutil.rmtree(work,ignore_errors=True)
window=tk.Tk()
window.title("KHIÊM YOUTUBE | CẬP NHẬT PORTABLE")
window.geometry("520x190")
ttk.Label(window,text="CẬP NHẬT PORTABLE TỪ GITHUB",font=("Segoe UI",14,"bold")).pack(pady=(20,8))
status=tk.StringVar(value="Sẵn sàng kiểm tra phiên bản mới.")
ttk.Label(window,textvariable=status,wraplength=470).pack(pady=6)
def start():
    button.configure(state="disabled")
    try: apply()
    except Exception as exc:
        status.set("Cập nhật thất bại")
        messagebox.showerror("Cập nhật",str(exc))
    finally: button.configure(state="normal")
button=ttk.Button(window,text="KIỂM TRA VÀ CẬP NHẬT",command=start)
button.pack(pady=12)
if __name__=="__main__": window.mainloop()
