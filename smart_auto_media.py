"""Independent Wikimedia Commons media downloader. No renderer imports."""
import json
import math
import re
import hashlib
import subprocess
import threading
import queue
import html
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode, urlparse
import tkinter as tk
from tkinter import ttk, filedialog

API = "https://commons.wikimedia.org/w/api.php"
UA = "KhiemYouTubeMedia/1.0 (Wikimedia Commons licensed media desktop client)"
IMG = {".jpg", ".jpeg", ".png", ".webp"}
VID = {".webm", ".mp4", ".ogv"}
AUDIO = {".mp3", ".wav", ".m4a", ".flac"}

def section(p):
    m = re.match(r"^\s*(\d+)(?=\D|$)", p.stem)
    return int(m[1]) if m else None

def duration(p):
    opts = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    d = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=nw=1:nk=1", str(p)],
        timeout=30, **opts).decode().strip())
    if not math.isfinite(d) or d <= 0:
        raise ValueError("Thời lượng không hợp lệ: " + str(p))
    return d

def indexed(root, suffixes):
    result = {}
    for p in sorted(root.iterdir()):
        n = section(p)
        if p.is_file() and p.suffix.lower() in suffixes and n is not None:
            if n in result:
                raise ValueError("Trùng số thứ tự: " + str(p))
            result[n] = p
    return result

def plan(root):
    voice = indexed(root / "voice", AUDIO)
    txt = indexed(root / "txt", {".txt"})
    if not voice or set(voice) != set(txt):
        raise ValueError("Voice và TXT phải có cùng số thứ tự.")
    key = next((p for p in root.iterdir() if p.is_file() and p.name.lower() == "key.txt"), None)
    if not key:
        raise ValueError("Cần KEY.txt ở thư mục dự án.")
    groups = {}
    current = None
    for raw in key.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(?:#+\s*)?(\d{1,2})\s*[-.:)]\s*(Opening|Ending|Number\b.*|Hook)\b", line, re.I)
        if m:
            current = int(m[1])
            groups.setdefault(current, [])
        elif current is not None:
            q = line.strip(" -*\x60")
            if q and len(q) <= 180:
                groups[current].append(q)
    if set(groups) != set(voice) or any(not groups[n] for n in voice):
        raise ValueError("KEY.txt cần tiêu đề 01 - Opening, 02 - Number ... và từ khóa bên dưới từng phần.")
    result = []
    for n,p in sorted(voice.items()):
        script = txt[n].read_text(encoding="utf-8-sig").strip()
        if not script:
            raise ValueError("TXT rỗng: " + str(txt[n]))
        d = duration(p)
        result.append({"number":n,"voice":str(p),"txt":str(txt[n]),"duration":d,
            "queries":list(dict.fromkeys(groups[n])), "image_slots":math.ceil(d/6),
            "video_slots":math.ceil(d/8)})
    return result

def search(query, kind):
    params = {"action":"query","format":"json","generator":"search","gsrnamespace":6,
        "gsrsearch":query + (" filetype:bitmap" if kind=="image" else " filetype:video"),
        "gsrlimit":20,"prop":"imageinfo","iiprop":"url|size|mime|extmetadata|sha1"}
    with urlopen(Request(API+"?"+urlencode(params),headers={"User-Agent":UA}),timeout=25) as r:
        data=json.load(r)
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    return sorted(data.get("query",{}).get("pages",{}).values(),key=lambda p:p.get("index",999))

def download(page, folder, kind, known, stop):
    info=page.get("imageinfo",[{}])[0]
    meta=info.get("extmetadata",{})
    def field(k): return meta.get(k,{}).get("value","")
    license_name=field("LicenseShortName")
    lic=license_name.lower().strip()
    if not (lic in {"public domain","cc0","cc0 1.0"} or re.fullmatch(r"cc by(?:-sa)? [0-9.]+",lic)):
        return None
    url=info.get("url","")
    parsed=urlparse(url)
    ext=Path(parsed.path).suffix.lower()
    if parsed.scheme!="https" or parsed.hostname!="upload.wikimedia.org":
        return None
    if ext not in (IMG if kind=="image" else VID) or info.get("width",0)<640:
        return None
    limit=20*1024**2 if kind=="image" else 150*1024**2
    if not 0<info.get("size",0)<=limit:
        return None
    name="commons_"+str(page["pageid"])+ext
    target=folder/name
    if target.exists(): return None
    temp=folder/(name+".partial")
    h=hashlib.sha256()
    try:
        with urlopen(Request(url,headers={"User-Agent":UA}),timeout=30) as r, temp.open("wb") as f:
            count=0
            while True:
                if stop.is_set(): return None
                chunk=r.read(65536)
                if not chunk: break
                count+=len(chunk)
                if count>limit: return None
                h.update(chunk); f.write(chunk)
        if not count or h.hexdigest() in known: return None
        credits={"file":name,"source":info.get("descriptionurl"),"license":license_name,
            "license_url":field("LicenseUrl"),"author":html.unescape(re.sub("<[^>]+>","",field("Artist")))}
        with (folder/"_commons_credits.jsonl").open("a",encoding="utf-8") as f:
            f.write(json.dumps(credits,ensure_ascii=False)+"\n")
        temp.replace(target)
        known.add(h.hexdigest())
        return target
    finally:
        temp.unlink(missing_ok=True)

def run(root, mode, stop, log):
    timeline=plan(root)
    (root/"_media_plan.json").write_text(json.dumps(timeline,ensure_ascii=False,indent=2),encoding="utf-8")
    known=set()
    for p in root.rglob("*"):
        if stop.is_set(): return
        if p.is_file() and p.suffix.lower() in IMG|VID:
            with p.open("rb") as f:
                h=hashlib.sha256()
                for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
            known.add(h.hexdigest())
    for part in timeline:
        if stop.is_set(): return
        n=part["number"]
        matches=[p for p in root.iterdir() if p.is_dir() and section(p)==n]
        if len(matches)>1: raise ValueError("Trùng thư mục phần "+str(n))
        folder=matches[0] if matches else root/("%02d"%n)
        folder.mkdir(exist_ok=True)
        if folder.resolve().parent!=root: raise ValueError("Thư mục nằm ngoài dự án.")
        existing=list(folder.rglob("*"))
        images=sum(p.is_file() and p.suffix.lower() in IMG for p in existing)
        videos=0
        for p in existing:
            if p.is_file() and p.suffix.lower() in VID:
                try: videos+=min(3,int(duration(p)/8))
                except Exception: pass
        d=part["duration"]
        log("Phần %02d: %.1fs | %d ảnh có sẵn, %d cảnh video ước tính"%(n,d,images,videos))
        def fill(kind,need):
            added=0
            for q in part["queries"]:
                if stop.is_set() or added>=need: break
                log("Tìm "+kind+": "+q)
                for page in search(q,kind):
                    if stop.is_set() or added>=need: break
                    try:
                        p=download(page,folder,kind,known,stop)
                        if p:
                            added+=1
                            log("Đã tải: "+p.name)
                    except (OSError,ValueError) as e: log("Bỏ qua: "+str(e))
            return added
        if mode!="image":
            target=min(20,math.ceil(d*(1 if mode=="video" else .5)/8))
            videos+=fill("video",max(0,target-videos))
        if mode!="video":
            target=min(120,math.ceil(max(0,d-(videos*8 if mode=="both" else 0))/6*1.15))
            images+=fill("image",max(0,target-images))
        log("Phần %02d: %d ảnh, %d cảnh video ước tính. Cần xem lại đúng nhân vật và quyền sử dụng."%(n,images,videos))
    log("Hoàn thành tìm tải. Có thể thiếu tư liệu nếu nguồn không có kết quả phù hợp.")

def add_tab(notebook):
    frame=ttk.Frame(notebook,padding=12)
    notebook.add(frame,text="05  TẢI TƯ LIỆU AI")
    path=tk.StringVar()
    mode=tk.StringVar(value="both")
    events=queue.Queue()
    stop=threading.Event()
    ttk.Label(frame,text="Tải tư liệu Wikimedia Commons theo Voice + TXT + KEY").pack(anchor="w")
    row=ttk.Frame(frame); row.pack(fill="x",pady=8)
    ttk.Entry(row,textvariable=path).pack(side="left",fill="x",expand=True)
    def choose():
        p=filedialog.askdirectory()
        if p:path.set(p)
    ttk.Button(row,text="Chọn thư mục",command=choose).pack(side="left")
    row=ttk.Frame(frame); row.pack(fill="x")
    for label,value in [("Ảnh","image"),("Video","video"),("Ảnh + Video","both")]:
        ttk.Radiobutton(row,text=label,variable=mode,value=value).pack(side="left")
    ttk.Label(frame,text="Cần voice/, txt/, KEY.txt. Nguồn miễn phí có giấy phép; không bảo đảm đủ tư liệu.").pack(anchor="w",pady=5)
    buttons=ttk.Frame(frame); buttons.pack(fill="x")
    output=tk.Text(frame,height=14,wrap="word"); output.pack(fill="both",expand=True,pady=8)
    def start():
        if not path.get().strip(): return
        root=Path(path.get()).resolve()
        selected=mode.get()
        stop.clear(); button.configure(state="disabled")
        def worker():
            try: run(root,selected,stop,events.put)
            except Exception as e: events.put("Lỗi: "+str(e))
            finally: events.put(None)
        threading.Thread(target=worker,daemon=True).start()
    button=ttk.Button(buttons,text="BẮT ĐẦU TẢI",command=start);button.pack(side="left")
    ttk.Button(buttons,text="DỪNG",command=stop.set).pack(side="left")
    def poll():
        while True:
            try: item=events.get_nowait()
            except queue.Empty: break
            if item is None: button.configure(state="normal")
            else: output.insert("end",item+"\n");output.see("end")
        frame.after(200,poll)
    poll()
