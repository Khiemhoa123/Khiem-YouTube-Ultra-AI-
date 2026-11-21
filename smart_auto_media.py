"""Independent Wikimedia Commons media downloader. No renderer imports."""
import time
import os
from urllib.error import HTTPError
from urllib.parse import quote_plus
import webbrowser
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

def plan(key, voice_root=None, images=20, videos=5, script_root=None, log=lambda msg: None):
    groups = []
    current = None
    for raw in key.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip().strip("#* ").strip()
        if not line:
            continue
        m = re.match(r"^(?:(\d{1,2})\s*[-.:)]\s*)?(Opening|Ending|Hook|Number\s+(?:\d+|[a-z]+))\b(.*)$", line, re.I)
        if m:
            n = int(m[1]) if m[1] else len(groups)+1
            current = {"number":n,"title":m[2]+m[3],"queries":[]}
            groups.append(current)
        elif current is not None:
            q = line.strip(" -*\x60")
            if q and len(q)<=180:
                current["queries"].append(q)
    if not groups or any(not g["queries"] for g in groups):
        raise ValueError("KEY cần các mục Opening, Number Five..., Ending và từ khóa bên dưới.")
    if len({g["number"] for g in groups}) != len(groups):
        raise ValueError("Trùng số thứ tự trong KEY.")
    voice = indexed(voice_root, AUDIO) if voice_root else {}
    if voice_root and set(voice) != {g["number"] for g in groups}:
        raise ValueError("Số thứ tự Voice không khớp các mục KEY.")
    scripts = indexed(script_root, {".txt"}) if script_root else {}
    if script_root and set(scripts) != {g["number"] for g in groups}:
        raise ValueError("Số thứ tự TXT kịch bản không khớp các mục KEY.")
    contents = {}
    for n,p in sorted(scripts.items()):
        contents[n] = p.read_text(encoding="utf-8-sig").strip()
        if not contents[n]:
            raise ValueError("TXT kịch bản rỗng: "+p.name)
        log(f"TXT {n:02d}: {p.name} | {len(contents[n].split())} từ")
    for g in groups:
        n=g["number"]
        g["duration"]=duration(voice[n]) if n in voice else None
        g["queries"]=list(dict.fromkeys(g["queries"]))
        script = contents.get(n,"")
        if script:
            words = set(re.findall(r"\w+",script.casefold()))
            def relevance(q):
                tokens = {w for w in re.findall(r"\w+",q.casefold()) if len(w)>3}
                return len(tokens & words)/max(1,len(tokens))
            g["queries"].sort(key=relevance,reverse=True)
            g["script_file"]=str(scripts[n])
            g["script_words"]=len(script.split())
            g["context_terms"]=sorted(words)
            log(f"Phần {n:02d}: đã xếp ưu tiên {len(g['queries'])} KEY theo TXT.")
            if g["duration"] is None:
                g["duration"]=len(script.split())*60/145
                log(f"Phần {n:02d}: thời lượng ước tính từ TXT {g['duration']:.1f}s.")
        g["image_target"]=images
        g["video_target"]=videos
    return groups

class RateLimited(RuntimeError):
    pass

_search_cache = {}
_next_request = 0.0

def request_json(url, stop):
    global _next_request
    for attempt in range(3):
        if stop.wait(max(0, _next_request-time.monotonic())):
            return {}
        _next_request=time.monotonic()+2.0
        try:
            with urlopen(Request(url,headers={"User-Agent":UA}),timeout=25) as r:
                return json.load(r)
        except HTTPError as e:
            if e.code != 429:
                raise
            try: delay=max(15,int(e.headers.get("Retry-After","30")))
            except ValueError: delay=60
            _next_request=time.monotonic()+delay
            raise RateLimited(f"HTTP 429: tạm dừng Commons {delay}s; chạy lại sau.")
    return {}

def search(query, kind, stop):
    params = {"action":"query","format":"json","generator":"search","gsrnamespace":6,
        "gsrsearch":query + (" filetype:bitmap" if kind=="image" else " filetype:video"),
        "gsrlimit":20,"prop":"imageinfo","iiprop":"url|size|mime|extmetadata|sha1"}
    cache_key=(query,kind)
    if cache_key in _search_cache: return list(_search_cache[cache_key])
    data=request_json(API+"?"+urlencode(params),stop)
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    pages=sorted(data.get("query",{}).get("pages",{}).values(),key=lambda p:p.get("index",999))
    _search_cache[cache_key]=pages
    return list(pages)

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

def run(root, mode, stop, log, key, voice_root=None, image_count=20, video_count=5, script_root=None):
    log('Đang đọc KEY: '+key.name)
    timeline=plan(key, voice_root, image_count, video_count, script_root, log)
    log(f'Đã đọc {len(timeline)} phần. Đang kiểm tra tư liệu có sẵn.')
    # Search links are for human review, not automatic downloads from restricted sites.
    links=["<meta charset='utf-8'><title> Tìm tư liệu </title>"]
    for part in timeline:
        links.append("<h2>"+html.escape(str(part["number"])+" "+part["title"])+"</h2>")
        for q in part["queries"]:
            x=quote_plus(q)
            links.append("<p>"+html.escape(q)+" | "+" | ".join(
                '<a target="_blank" rel="noopener" href="'+html.escape(u,quote=True)+'">'+label+'</a>'
                for label,u in [("Google Images","https://www.google.com/search?tbm=isch&q="+x),("Bing Images","https://www.bing.com/images/search?q="+x),("Getty","https://www.gettyimages.com/photos/"+x.replace("+","-")),("YouTube","https://www.youtube.com/results?search_query="+x)])+"</p>")
    (root/"_media_search.html").write_text("\n".join(links),encoding="utf-8")
    log("Đã lưu _media_search.html: liên kết đa nguồn để kiểm tra và chọn tư liệu có quyền sử dụng.")
    commons_blocked=False
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
        log(f"Phần {n:02d}: {part['title']} | {d if d is not None else 'Không có Voice'} | {images} ảnh, {videos} cảnh video ước tính")
        def fill(kind,need):
            nonlocal commons_blocked
            added=0
            if commons_blocked: return 0
            title=part["title"]
            person=title.split("|")[-1].strip() if "|" in title else ""
            queries=list(dict.fromkeys(([person] if person else [])+part["queries"]))
            for q in queries:
                if stop.is_set() or added>=need: break
                log("Tìm "+kind+": "+q)
                try:
                    pages=search(q,kind,stop)
                except RateLimited as e:
                    log(str(e))
                    commons_blocked=True
                    break
                except Exception as e:
                    log("Lỗi tìm kiếm: "+str(e))
                    continue
                terms=set(part.get("context_terms",[]))
                if terms:
                    def page_score(page):
                        tokens={w for w in re.findall(r"\w+",page.get("title","").casefold()) if len(w)>3}
                        return len(tokens & terms)/max(1,len(tokens))
                    pages.sort(key=page_score,reverse=True)
                log(f"Nhận {len(pages)} kết quả; đã tải {added}/{need}")
                for page in pages:
                    if stop.is_set() or added>=need: break
                    try:
                        if person and not all(w in (page.get("title","")+" "+str(page.get("imageinfo",[]))).casefold() for w in person.casefold().split()):
                            continue
                        log("Kiểm tra ứng viên: "+page.get("title",""))
                        p=download(page,folder,kind,known,stop)
                        if p:
                            added+=1
                            log("Đã tải: "+p.name)
                    except HTTPError as e:
                        if e.code==429:
                            commons_blocked=True
                            log("HTTP 429 khi tải: dừng Commons, giữ tư liệu đã tải.")
                            return added
                        log("Bỏ qua: "+str(e))
                    except (OSError,ValueError) as e: log("Bỏ qua: "+str(e))
            return added
        if mode!="image":
            target=part["video_target"] if d is None else min(20,math.ceil(d*(1 if mode=="video" else .5)/8))
            videos+=fill("video",max(0,target-videos))
        if mode!="video":
            target=part["image_target"] if d is None else min(120,math.ceil(max(0,d-(videos*8 if mode=="both" else 0))/6*1.15))
            images+=fill("image",max(0,target-images))
        log("Phần %02d: %d ảnh, %d cảnh video ước tính. Cần xem lại đúng nhân vật và quyền sử dụng."%(n,images,videos))
    log("Dừng do giới hạn Commons. Mở danh sách tìm kiếm để bổ sung." if commons_blocked else "Hoàn thành tìm tải. Kiểm tra số lượng thực tế từng phần.")


def browser_images(root, key, vr, sr, ni, nv, inbox, browser, source, stop, log, advance):
    from PIL import Image
    import shutil
    log("BROWSER MEDIA: Đọc KEY + TXT + Voice; không gọi Commons.")
    parts=plan(key,vr,ni,nv,sr,log)
    if inbox==root or root in inbox.parents or inbox in root.parents:
        raise ValueError("Chọn thư mục Downloads riêng, không nằm trong dự án.")
    known=set()
    for p in root.rglob("*"):
        if stop.is_set(): return
        if p.is_file() and p.suffix.lower() in IMG:
            with p.open("rb") as f:
                known.add(hashlib.sha256(f.read()).hexdigest())
    for part in parts:
        if stop.is_set(): return
        n=part["number"]
        matches=[p for p in root.iterdir() if p.is_dir() and section(p)==n]
        if len(matches)>1: raise ValueError("Trùng thư mục phần "+str(n))
        folder=matches[0] if matches else root/("%02d"%n)
        folder.mkdir(exist_ok=True)
        if folder.resolve().parent!=root: raise ValueError("Thư mục ngoài dự án.")
        target=ni if part["duration"] is None else min(120,math.ceil(part["duration"]/6*1.15))
        count=sum(p.is_file() and p.suffix.lower() in IMG for p in folder.rglob("*"))
        log(f"Phần {n:02d}: cần {target} ảnh, hiện có {count}.")
        person=part["title"].split("|")[-1].strip() if "|" in part["title"] else ""
        queries=list(dict.fromkeys(([person] if person else [])+part["queries"]))
        for q in queries:
            if stop.is_set() or count>=target: break
            before={p.name for p in inbox.iterdir()}
            url=("https://www.gettyimages.com/photos/"+quote_plus(q).replace("+","-") if source=="Getty" else "https://www.google.com/search?tbm=isch&q="+quote_plus(q))
            advance.clear()
            subprocess.Popen([str(browser),url])
            log(f"Phần {n:02d} | {part['title']} | {count}/{target} ảnh")
            log("Cốc Cốc: "+q)
            log("Dùng Imageye tải ảnh có quyền sử dụng vào thư mục nhận. Đợi tải xong rồi bấm NHẬN ẢNH / TIẾP.")
            waiting=time.monotonic()
            while not advance.wait(0.5):
                if stop.is_set(): return
                if time.monotonic()-waiting>=15:
                    log(f"Đang chờ bạn tải ảnh Imageye cho phần {n:02d}, rồi bấm NHẬN ẢNH / TIẾP.")
                    waiting=time.monotonic()
            if stop.is_set(): return
            log("Đang kiểm tra ảnh mới trong: "+str(inbox))
            previous_count=count
            for p in sorted(inbox.iterdir()):
                if stop.is_set() or count>=target: break
                if p.name in before or not p.is_file() or p.suffix.lower() not in IMG: continue
                try:
                    with Image.open(p) as im:
                        w,h=im.size
                        if w<640 or h<360: log("Bỏ ảnh nhỏ: "+p.name); continue
                        im.verify()
                    if p.stat().st_size>30*1024**2: continue
                    digest=hashlib.sha256(p.read_bytes()).hexdigest()
                    if digest in known: log("Trùng ảnh: "+p.name); continue
                    dest=folder/("browser_"+digest[:20]+p.suffix.lower())
                    shutil.copy2(p,dest)
                    known.add(digest); count+=1
                    with (folder/"_browser_sources.jsonl").open("a",encoding="utf-8") as f:
                        f.write(json.dumps({"file":dest.name,"search":url,"original_filename":p.name,"rights":"user review required"},ensure_ascii=False)+"\n")
                    log(f"Đã nhận {count}/{target}: {p.name}")
                except (OSError,ValueError) as e: log("Bỏ qua: "+str(e))
            log(f"Đợt này nhận {count-previous_count} ảnh; tổng {count}/{target}.")
        log(f"Phần {n:02d}: {count}/{target} ảnh. Kiểm tra nhân vật và giấy phép.")
    log("Kết thúc nhận ảnh. Ảnh gốc vẫn nằm trong thư mục tải.")



def auto_openverse(root,key,vr,sr,ni,nv,stop,log):
    from PIL import Image
    import io
    parts=plan(key,vr,ni,nv,sr,log)
    known=set()
    for p in root.rglob("*"):
        if stop.is_set(): return
        if p.is_file() and p.suffix.lower() in IMG:
            if p.stat().st_size<=30*1024**2:
                known.add(hashlib.sha256(p.read_bytes()).hexdigest())
    for part in parts:
        if stop.is_set(): return
        n=part["number"]
        matches=[p for p in root.iterdir() if p.is_dir() and section(p)==n]
        if len(matches)>1: raise ValueError("Trùng thư mục phần "+str(n))
        folder=matches[0] if matches else root/("%02d"%n)
        folder.mkdir(exist_ok=True)
        if folder.resolve().parent!=root: raise ValueError("Thư mục ngoài dự án.")
        target=ni if part["duration"] is None else min(120,math.ceil(part["duration"]/6*1.15))
        count=sum(p.is_file() and p.suffix.lower() in IMG for p in folder.rglob("*"))
        person=part["title"].split("|")[-1].strip() if "|" in part["title"] else ""
        queries=list(dict.fromkeys(([person] if person else [])+part["queries"]))
        log(f"Phần {n:02d}: {count}/{target} ảnh | {folder}")
        for q in queries:
            if stop.is_set() or count>=target: break
            log("Openverse: "+q)
            try:
                data=request_json("https://api.openverse.org/v1/images/?"+urlencode({"q":q,"page_size":20,"license":"cc0,pdm,by,by-sa"}),stop)
            except RateLimited as e:
                log("Openverse giới hạn truy cập. Dừng và giữ ảnh đã tải: "+str(e)); return
            except Exception as e:
                log("Lỗi tìm kiếm: "+str(e)); continue
            results=data.get("results",[])
            log(f"Nhận {len(results)} ứng viên.")
            for item in results:
                if stop.is_set() or count>=target: break
                if item.get("license") not in ("cc0","pdm","by","by-sa"): continue
                if person and not all(w in str(item.get("title","")).casefold() for w in person.casefold().split()): continue
                url=item.get("url") or ""
                if urlparse(url).scheme!="https": continue
                log("Kiểm tra: "+str(item.get("title","")))
                try:
                    if stop.wait(2): return
                    with urlopen(Request(url,headers={"User-Agent":UA}),timeout=20) as response:
                        if urlparse(response.geturl()).scheme!="https": continue
                        raw=response.read(20*1024**2+1)
                    if len(raw)>20*1024**2: continue
                    digest=hashlib.sha256(raw).hexdigest()
                    if digest in known: continue
                    with Image.open(io.BytesIO(raw)) as im:
                        if im.width<640 or im.height<360 or im.width*im.height>40000000: continue
                        ext={"JPEG":".jpg","PNG":".png","WEBP":".webp"}.get(im.format)
                        if not ext: continue
                        im.verify()
                    dest=folder/("openverse_"+digest[:24]+ext)
                    if dest.exists(): continue
                    with (folder/"_openverse_credits.jsonl").open("a",encoding="utf-8") as f:
                        f.write(json.dumps({"file":dest.name,"source":item.get("foreign_landing_url"),"url":url,"license":item.get("license"),"license_url":item.get("license_url"),"creator":item.get("creator"),"title":item.get("title")},ensure_ascii=False)+"\n")
                    dest.write_bytes(raw)
                    known.add(digest); count+=1
                    log(f"Đã tải {count}/{target}: {dest.name}")
                except HTTPError as e:
                    if e.code==429:
                        log("Nguồn ảnh giới hạn truy cập, dừng để tránh gửi quá nhiều yêu cầu."); return
                    log("Bỏ ứng viên: "+str(e))
                except Exception as e:
                    log("Bỏ ứng viên: "+str(e))
        log(f"Phần {n:02d}: {count}/{target}. "+("Đủ số lượng." if count>=target else "Thiếu ảnh phù hợp.")+" Kiểm tra nhân vật và giấy phép.")
    log("Kết thúc tải tự động Openverse.")


def find_coccoc():
    for env in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        base=os.environ.get(env)
        if base:
            for rel in ("CocCoc/Browser/Application/browser.exe","Coc Coc/Browser/Application/browser.exe"):
                p=Path(base)/rel
                if p.is_file(): return str(p)
    return ""

def add_tab(notebook):
    frame=ttk.Frame(notebook,padding=12)
    notebook.add(frame,text="05  TẢI TƯ LIỆU AI")
    path=tk.StringVar()
    key_path=tk.StringVar()
    voice_path=tk.StringVar()
    script_path=tk.StringVar()
    image_count=tk.StringVar(value="20")
    video_count=tk.StringVar(value="5")
    mode=tk.StringVar(value="image")
    browser_mode=tk.BooleanVar(value=True)
    browser_path=tk.StringVar(value=find_coccoc())
    inbox_path=tk.StringVar(value=str(Path.home()/"Downloads"))
    source=tk.StringVar(value="Openverse tự động")
    advance=threading.Event()
    events=queue.Queue()
    stop=threading.Event()
    ttk.Label(frame,text="SMART AUTO MEDIA V4.0 | Openverse tự động hoặc Imageye hỗ trợ").pack(anchor="w")
    def picker(label,var,is_file=False, types=None):
        ttk.Label(frame,text=label).pack(anchor="w")
        row=ttk.Frame(frame); row.pack(fill="x",pady=3)
        ttk.Entry(row,textvariable=var).pack(side="left",fill="x",expand=True)
        def choose():
            p=filedialog.askopenfilename(filetypes=types or [("TXT","*.txt")]) if is_file else filedialog.askdirectory()
            if p: var.set(p)
        ttk.Button(row,text="Chọn",command=choose).pack(side="left")
    picker("File KEY TXT",key_path,True)
    picker("Thư mục lưu",path)
    picker("Thư mục TXT kịch bản (không bắt buộc)",script_path)
    picker("Thư mục Voice (không bắt buộc)",voice_path)
    ttk.Checkbutton(frame,text="Openverse / Cốc Cốc + Imageye (bỏ chọn để dùng Commons)",variable=browser_mode).pack(anchor="w")
    picker("Cốc Cốc (browser.exe)",browser_path,True,[("EXE","*.exe")])
    picker("Thư mục nhận ảnh tải xuống",inbox_path)
    ttk.Combobox(frame,textvariable=source,values=["Openverse tự động","Google","Getty"],state="readonly").pack(anchor="w")
    counts=ttk.Frame(frame); counts.pack(fill="x")
    ttk.Label(counts,text="Không có Voice/TXT: ảnh/phần").pack(side="left")
    ttk.Entry(counts,textvariable=image_count,width=5).pack(side="left")
    ttk.Label(counts,text="Video/phần").pack(side="left")
    ttk.Entry(counts,textvariable=video_count,width=5).pack(side="left")
    row=ttk.Frame(frame); row.pack(fill="x")
    for label,value in [("Ảnh","image"),("Video","video"),("Ảnh + Video","both")]:
        ttk.Radiobutton(row,text=label,variable=mode,value=value).pack(side="left")
    ttk.Label(frame,text="Openverse: tự tải ảnh. Google/Getty: dùng Imageye và bấm NHẬN ẢNH / TIẾP.").pack(anchor="w",pady=5)
    buttons=ttk.Frame(frame); buttons.pack(fill="x")
    output=tk.Text(frame,height=14,wrap="word"); output.pack(fill="both",expand=True,pady=8)
    def start():
        if not path.get().strip() or not key_path.get().strip():
            events.put("Hãy chọn KEY TXT và thư mục lưu.")
            return
        try:
            root=Path(path.get()).resolve()
            key=Path(key_path.get()).resolve()
            vr=Path(voice_path.get()).resolve() if voice_path.get().strip() else None
            sr=Path(script_path.get()).resolve() if script_path.get().strip() else None
            if sr and not sr.is_dir(): raise ValueError("Thư mục TXT không tồn tại.")
            if vr and not vr.is_dir(): raise ValueError("Thư mục Voice không tồn tại.")
            ni,nv=int(image_count.get()),int(video_count.get())
            if not root.is_dir() or not key.is_file() or not (0<=ni<=120 and 0<=nv<=20):
                raise ValueError("Kiểm tra đường dẫn và số lượng ảnh 0-120, video 0-20.")
        except Exception as e:
            events.put("Lỗi: "+str(e)); return
        selected=mode.get()
        use_browser=browser_mode.get()
        src=source.get()
        exe=Path(browser_path.get())
        inbox=Path(inbox_path.get()).resolve()
        if use_browser and src=="Openverse tự động" and selected!="image":
            events.put("Openverse tự động chỉ hỗ trợ ảnh."); return
        if use_browser and src!="Openverse tự động" and (not exe.is_file() or not inbox.is_dir() or selected!="image"):
            events.put("Chọn browser.exe Cốc Cốc, thư mục nhận và chế độ Ảnh."); return
        events.put("Chế độ: "+(("Openverse tự động" if src=="Openverse tự động" else "Cốc Cốc + Imageye | "+src) if use_browser else "Wikimedia Commons"))
        stop.clear(); button.configure(state="disabled")
        def worker():
            try:
                if use_browser and src=="Openverse tự động": auto_openverse(root,key,vr,sr,ni,nv,stop,events.put)
                elif use_browser: browser_images(root,key,vr,sr,ni,nv,inbox,exe,src,stop,events.put,advance)
                else: run(root,selected,stop,events.put,key,vr,ni,nv,sr)
            except Exception as e: events.put("Lỗi: "+str(e))
            finally: events.put(None)
        threading.Thread(target=worker,daemon=True).start()
    button=ttk.Button(buttons,text="BẮT ĐẦU TẢI",command=start);button.pack(side="left")
    ttk.Button(buttons,text="DỪNG",command=stop.set).pack(side="left")
    ttk.Button(buttons,text="NHẬN ẢNH / TIẾP",command=advance.set).pack(side="left")
    def open_links():
        p=Path(path.get()).resolve()/"_media_search.html"
        if p.is_file(): webbrowser.open(p.as_uri())
        else: events.put("Chưa có danh sách tìm kiếm.")
    ttk.Button(buttons,text="MỞ TÌM KIẾM ĐA NGUỒN",command=open_links).pack(side="left")
    def poll():
        while True:
            try: item=events.get_nowait()
            except queue.Empty: break
            if item is None: button.configure(state="normal")
            else: output.insert("end",time.strftime("[%H:%M:%S] ")+item+"\n");output.see("end")
        frame.after(200,poll)
    poll()
