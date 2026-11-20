import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import subprocess as sp, json, re, random, hashlib, math, tempfile, threading, os, shutil
from turbo_cache import digest_cached, duration_cached


# KHIEM_SMART_SELECTOR_V81_INSTALLED
from smart_selector_v81 import (
    image_allowed as v81_image_allowed,
    remember_image as v81_remember_image,
    is_export as v81_is_export,
    save_timeline_report as v81_save_report,
)

A={'.mp3','.wav','.m4a','.flac'}; I={'.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff'}; V={'.mp4','.mov','.mkv','.webm','.avi','.m4v','.mts','.mpeg','.mpg'}
def run(args):
 p=sp.run(args,stdout=sp.PIPE,stderr=sp.PIPE,creationflags=getattr(sp,'CREATE_NO_WINDOW',0))
 if p.returncode: raise RuntimeError(p.stderr.decode(errors='replace')[-2500:])
 return p.stdout

def duration(p): return float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(p)]))
def number(p):
 m=re.match(r'^(\d+)',p.name); return int(m[1]) if m else None
def indexed(root,ext):
 d={}
 for p in sorted(Path(root).iterdir()):
  if p.is_file() and p.suffix.lower() in ext:
   n=number(p)
   if n is None or n in d: raise ValueError('Tên thiếu hoặc trùng số thứ tự: '+str(p))
   d[n]=p
 return d
def digest(p):
 with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def words(s): return set(re.findall(r'\w{3,}',s.lower()))
def times(s,mode):
 a=[float(x) for x in re.split(r'[,;\s]+',s.strip()) if x]
 if not a or any(not math.isfinite(x) or x<=0 for x in a) or (mode=='Cố định' and len(a)!=1): raise ValueError('Thời lượng không hợp lệ')
 return a

def plan(c,log):
 voices=indexed(c['voice'],A); scripts=indexed(c['txt'],{'.txt'}); fps=int(c['fps']); rng=random.Random(); used=set(); used_images=[]; intervals={}; hashes={}; lens={}; parts=[]; elapsed=0.; frames=0
 ai=None
 if c.get("ai"):
  from semantic import Semantic
  try: ai=Semantic(log,c.get("speed","Smart"))
  except Exception as e: log("CẢNH BÁO: AI CLIP không chạy; dùng tên file/TXT thay thế, không phải nhận diện AI: "+str(e))
 if not voices: raise ValueError('Không có voice')
 if set(voices)!=set(scripts): raise ValueError('Số thứ tự voice và TXT không khớp')
 counts=[int(c['vn']),int(c['an'])]; pattern=['video']*counts[0]+['image']*counts[1]
 if min(counts)<0 or not pattern: raise ValueError('Số cảnh không hợp lệ')
 ts={k:times(c[k+'time'],c[k+'mode']) for k in ['video','image']}
 for n,p in sorted(voices.items()):
  dur=duration_cached(p); script=scripts[n].read_text(encoding='utf-8-sig'); tokens=script.split(); pools={}
  for kind,ext,root in [('image',I,c['images']),('video',V,c['videos'])]:
   folders=[x for x in Path(root).iterdir() if x.is_dir() and number(x)==n]
   pools[kind]=[]
   for folder in folders:
    for src in sorted(folder.rglob('*')):
     if not src.is_file() or src.suffix.lower() not in ext: continue
     try:
      h=hashes.setdefault(src,digest_cached(src))
      if kind=='video':
       if h not in lens: lens[h]=duration_cached(src)
       if not math.isfinite(lens[h]) or lens[h]<=0: raise ValueError('Thời lượng không hợp lệ')
      if kind == 'video' and v81_is_export(src, c):
          log('V81: Bo qua video thanh pham: '+str(src))
          continue
      pools[kind].append(src)
     except Exception as e: log(f'Bỏ qua {src}: {e}')
   log(f'Phần {n} | {kind}: {len(pools[kind])} file | folder: {", ".join(map(str,folders)) or "KHÔNG TÌM THẤY"}')
   if kind=='video': log(f'Tổng video nguồn: {sum(lens[h] for h in {hashes[x] for x in pools[kind]}):.2f}s')
  aligned=[]
  if c.get('align') and ai:
   log(f'Whisper: phần {n}')
   try: aligned=ai.transcribe(p)
   except Exception as e: log('Whisper lỗi, dùng phân bổ TXT theo thời lượng (ước tính): '+str(e))
  elapsed+=dur; end=math.ceil(elapsed*fps); target=end-frames; pos=0; clips=[]
  def pick(kind,nf,context,query):
   t=nf/fps; candidates=[]
   for src in pools[kind]:
    h=hashes[src]; start=0.; gap=0.
    if kind=='image':
     if h in used: continue
     if kind == 'image' and not v81_image_allowed(src, used_images):
         continue
    else:
     bounds=sorted(intervals.get(h,[])); gaps=[]; cur=0.
     for l,r in bounds+[(lens[h],lens[h])]:
      if l-cur+1e-9>=t: gaps.append((cur,max(cur,l-t)))
      cur=max(cur,r)
     if not gaps: continue
     l,r=max(gaps,key=lambda g:g[1]-g[0]); gap=r-l
     # Pick near a gap edge to avoid wasting usable footage in fragments.
     start=rng.choice([l,r])
    label=src.stem
    side=src.with_suffix(src.suffix+'.txt')
    if side.exists(): label+=' '+side.read_text(encoding='utf-8-sig',errors='replace')
    score=len(context & words(label))
    if ai:
     starts=[start] if kind=='image' else sorted(set(round(x,6) for x in (l,(l+r)/2,r)))
     try:
      best=max((ai.score(kind,src,x,t,query),x) for x in starts)
      score=score*0.12+best[0]; start=best[1]
     except Exception as e: log("CLIP chấm điểm lỗi; dùng tên file: "+str(e))
    candidates.append((score,gap,rng.random(),src,h,start))
   return max(candidates) if candidates else None
  while pos<target:
   preferred=pattern[len(clips)%len(pattern)]; selected=None
   for kind in (preferred,'image' if preferred=='video' else 'video'):
    nf=min(target-pos,max(1,round(rng.choice(ts[kind])*fps)))
    mid=int(len(tokens)*(pos+nf/2)/max(target,1)); query=' '.join(tokens[max(0,mid-18):mid+18]); spoken=' '.join(w for a,b,w in aligned if b>=pos/fps and a<=(pos+nf)/fps); query=spoken or query; context=words(query) | words(re.sub(r"^\d+\s*[- ]*|number\s+\d+", "", scripts[n].stem, flags=re.I))
    selected=pick(kind,nf,context,query)
    if selected: break
   if not selected: raise ValueError(f'Phần {n}: hết tư liệu phù hợp tại {pos/fps:.2f}s; ảnh và video đều không đủ. Xem số file và thời lượng phía trên.')
   if kind!=preferred: log(f'Phần {n}, {pos/fps:.2f}s: thay {preferred} bằng {kind}')
   score,_,_,src,h,start=selected; t=nf/fps; log(f'Phần {n} {pos/fps:.2f}s | {src.name} | nguồn {start:.2f}s | điểm {score:.3f} | {query[:160]}')
   if kind=='image':
       used.add(h)
       v81_remember_image(src, used_images)
   else: intervals.setdefault(h,[]).append((start,start+t))
   clips.append(dict(part=n,type=kind,source=str(src.resolve()),source_start=start,start=(frames+pos)/fps,frames=nf,duration=t,effect=rng.choice(c['effects'] or ['Tĩnh']))); pos+=nf
  parts.append(dict(number=n,voice=str(p.resolve()),duration=dur,clips=clips)); frames=end; log(f'Phần {n}: {len(clips)} cảnh, {dur:.2f}s')
 v81_save_report(c, parts, log)
 return parts

def render(c,parts,log,progress):
 out=Path(c['out']); out.mkdir(parents=True,exist_ok=True); name=c['name']; fps=int(c['fps']); w,h=map(int,c['res'].split('x')); total=sum(len(p['clips']) for p in parts); index=0; enc=['-c:v','h264_nvenc','-preset','p4','-cq','20'] if c['gpu'] else ['-c:v','libx264','-preset','veryfast','-crf','20']; fit=f'scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1';
 with tempfile.TemporaryDirectory() as temp:
  tmp=Path(temp); paths=[]
  for p in parts:
   for s in p['clips']:
    dest=tmp/f'{index:06}.mp4'; nf=s['frames']; z=float(c['iz'] if s['type']=='image' else c['vz'])/100
    # Build a fitted canvas, optionally with a blurred copy behind it.
    if c.get('background')=='Nền mờ':
     base=f"split=2[bg][fg];[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,gblur=sigma={float(c.get('blur',30))}[b];[fg]scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1[f];[b][f]overlay=(W-w)/2:(H-h)/2:format=auto,setsar=1"
    else: base=fit
    if s['type']=='image':
     e=s['effect']; frac=f'on/{max(1,nf-1)}'; ease=f'(1-cos(PI*{frac}))/2'; expr=f'1+{z-1}*{ease}' if e=='Zoom in' else f'{z}-{z-1}*{ease}' if e=='Zoom out' else '1'
     vf=base+f",scale={w*2}:{h*2}:flags=lanczos,zoompan=z='{expr}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={nf}:s={w}x{h}:fps={fps},setsar=1"; inp=['-i',s['source']]
    else:
     zw=max(w,round(w*z/2)*2); zh=max(h,round(h*z/2)*2); vf=base+f',scale={zw}:{zh},crop={w}:{h},fps={fps},tpad=stop_mode=clone:stop_duration=0.15'; inp=['-ss',str(s['source_start']),'-i',s['source']]
    vf+=',format=yuv420p'
    cmd=['ffmpeg','-v','error','-y','-filter_threads','2']+inp+['-filter_complex_threads','2','-filter_complex',vf,'-frames:v',str(nf),'-an']; tail=['-pix_fmt','yuv420p','-threads','4',str(dest)]
    try: run(cmd+enc+tail)
    except RuntimeError:
     if enc[1]!='h264_nvenc': raise
     log('NVENC lỗi, chuyển CPU'); enc=['-c:v','libx264','-preset','veryfast','-crf','20']; run(cmd+enc+tail)
    paths.append(dest); index+=1; progress(90*index/total)
  # Render short transition bridges, preserving the original frame count.
  mode=c.get('transition','Không'); flat=[q for p in parts for q in p['clips']]
  if mode!='Không' and len(paths)>1:
   half=max(1,round(float(c.get('transition_time',.5))*fps/2)); cuts=[min(half,flat[j]['frames']//3,flat[j+1]['frames']//3) for j in range(len(paths)-1)]; result=[]
   def segment(inputs,filtergraph,count,dest):
    run(['ffmpeg','-v','error','-y','-filter_complex_threads','2']+inputs+['-filter_complex',filtergraph,'-r',str(fps),'-frames:v',str(count),'-an']+enc+['-pix_fmt','yuv420p','-threads','4',str(dest)])
   for j,src in enumerate(paths):
    left=cuts[j-1] if j else 0; right=cuts[j] if j<len(cuts) else 0; n=flat[j]['frames']; core=tmp/f'core{j:06}.mp4'
    segment(['-i',str(src)],f'[0:v]trim=start_frame={left}:end_frame={n-right},setpts=PTS-STARTPTS',n-left-right,core); result.append(core)
    if right:
     k=right; sec=k/fps; trans={'Dissolve':'fade','Fade':'fadeblack','Slide Left':'slideleft','Slide Right':'slideright','Blur':'hblur','Zoom Transition':'zoomin'}; style=random.choice(list(trans.values())) if mode=='Random' else trans[mode]; bridge=tmp/f'bridge{j:06}.mp4'
     graph=f'[0:v]trim=start_frame={n-k},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={2*sec:.9f},fps={fps},settb=AVTB[a];[1:v]trim=end_frame={k},setpts=PTS-STARTPTS,tpad=start_mode=clone:start_duration={sec:.9f}:stop_mode=clone:stop_duration={sec:.9f},fps={fps},settb=AVTB[b];[a][b]xfade=transition={style}:duration={2*sec:.9f}:offset=0,tpad=stop_mode=clone:stop_duration=1,format=yuv420p'
     segment(['-i',str(src),'-i',str(paths[j+1])],graph,2*k,bridge); result.append(bridge)
    progress(90+8*(j+1)/len(paths))
   paths=result
  listing=tmp/'list.txt'; listing.write_text(''.join(f"file '{p.name}'\n" for p in paths)); visual=tmp/'visual.mp4'; run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(visual)])
  aud=[]
  for j,p in enumerate(parts):
   dest=tmp/f'a{j}.wav'; run(['ffmpeg','-v','error','-y','-i',p['voice'],'-vn','-ar','48000','-ac','2','-c:a','pcm_s16le',str(dest)]); aud.append(dest)
  listing.write_text(''.join(f"file '{p.name}'\n" for p in aud)); audio=tmp/'audio.wav'; run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(audio)])
  dest=out/(name+'.mp4'); run(['ffmpeg','-v','error','-y','-i',str(visual),'-i',str(audio),'-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-b:a','320k','-movflags','+faststart',str(dest)]); progress(100); log('Hoàn thành: '+str(dest))

def main():
 root=tk.Tk(); root.title('AI AUTO CAPCUT V6.8 PRO TURBO - Local Preview'); root.geometry('1000x730'); panel=ttk.Frame(root,padding=15); panel.pack(fill='both',expand=True); panel.columnconfigure(1,weight=1); panel.columnconfigure(3,weight=1); vals={}; row=0; slot=0
 def field(key,label,default='',options=None,folder=False):
  nonlocal row,slot
  col=0 if folder else slot*2
  var=tk.StringVar(value=default); vals[key]=var; ttk.Label(panel,text=label).grid(row=row,column=col,sticky='w',pady=1); widget=ttk.Combobox(panel,textvariable=var,values=options,state='readonly') if options else ttk.Entry(panel,textvariable=var); widget.grid(row=row,column=col+1,columnspan=2 if folder else 1,sticky='ew',padx=8)
  if folder:
   def choose():
    p=filedialog.askdirectory();
    if p: var.set(p)
   ttk.Button(panel,text='Chọn thư mục',command=choose).grid(row=row,column=3)
  if folder: row+=1
  else:
   slot=1-slot
   if slot==0: row+=1
 ttk.Label(panel,text='AI AUTO CAPCUT V6.8 PRO TURBO',font=('Segoe UI',20,'bold')).grid(row=row,columnspan=4,pady=8); row+=1
 for k,l in [('voice','Voice MP3'),('txt','Kịch bản TXT'),('images','Ảnh (folder 1,2,3...)'),('videos','Video (folder 1,2,3...)'),('out','Nơi xuất')]: field(k,l,folder=True)
 field('draft_root','Nơi lưu dự án CapCut',str(Path(os.environ.get('LOCALAPPDATA',''))/'CapCut/User Data/Projects/com.lveditor.draft'),folder=True); field('sample','Mẫu khác (không bắt buộc)',folder=True); field('name','Tên dự án','New Project'); field('speed','Chế độ AI','Smart',['Fast','Smart','Deep']); field('vn','Số video mỗi chu kỳ','1'); field('an','Số ảnh mỗi chu kỳ','3')
 for k,l in [('video','Video'),('image','Ảnh')]:
  field(k+'mode',l+' - chế độ','Cố định',['Cố định','Random']); field(k+'time',l+' - giây (Random: 5,6,7,8)','5')
 field('background','Hiệu ứng nền','Nền mờ',['Nền đen','Nền mờ']); field('blur','Độ mờ nền (sigma 0-100)','30'); field('transition','Chuyển cảnh','Dissolve',['Không','Dissolve','Fade','Slide Left','Slide Right','Blur','Zoom Transition','Random']); field('transition_time','Chuyển cảnh (giây)','0.5',['0.3','0.5','0.7','1.0']); field('iz','Zoom ảnh tối đa (%)','110'); field('vz','Zoom video (%)','100'); field('res','Độ phân giải','3840x2160',['3840x2160','2560x1440','1920x1080']); field('fps','FPS','30',['24','30','60']); row+=slot; slot=0; gpu=tk.BooleanVar(value=True); ttk.Checkbutton(panel,text='NVIDIA NVENC (CPU dự phòng)',variable=gpu).grid(row=row,columnspan=4,sticky='w'); row+=1
 effects={e:tk.BooleanVar(value=e!='Tĩnh') for e in ['Zoom in','Zoom out','Tĩnh']}; ef=ttk.Frame(panel); ef.grid(row=row,columnspan=4,sticky='w'); row+=1
 for e,v in effects.items(): ttk.Checkbutton(ef,text=e,variable=v).pack(side='left')
 ai=tk.BooleanVar(value=True); align=tk.BooleanVar(value=True); opts=ttk.Frame(panel); opts.grid(row=row,columnspan=4,sticky='w'); row+=1; ttk.Checkbutton(opts,text='AI CLIP offline',variable=ai).pack(side='left'); ttk.Checkbutton(opts,text='Whisper đồng bộ voice',variable=align).pack(side='left')
 bar=ttk.Progressbar(panel); bar.grid(row=row,columnspan=4,sticky='ew',pady=5); row+=1
 status=tk.Text(panel,height=4); status.grid(row=row,columnspan=4,sticky='nsew'); panel.rowconfigure(row,weight=1); row+=1
 buttons=[]; cached={}; queue=[]; busy=False
 def start(mode, job=None):
  nonlocal busy
  c={k:v.get() for k,v in vals.items()}; c.update(ai=ai.get(),align=align.get(),gpu=gpu.get(),effects=[e for e,v in effects.items() if v.get()]);
  if job is not None: c=job
  try:
   if any(not c[k] or not Path(c[k]).is_dir() for k in ['voice','txt','images','videos','out']): raise ValueError('Hãy chọn đủ thư mục')
   if not c['name'] or re.search(r'[<>:"/\\|?*]',c['name']): raise ValueError('Tên dự án không hợp lệ')
   if not 0<=float(c['blur'])<=100: raise ValueError('Độ mờ từ 0 đến 100')
   if any(not 100<=float(c[k])<=150 for k in ['iz','vz']): raise ValueError('Zoom từ 100 đến 150')
  except Exception as e: messagebox.showerror('Lỗi',str(e)); return
  if mode=='render' and (Path(c['out'])/(c['name']+'.mp4')).exists() and not messagebox.askyesno('Ghi đè','Ghi đè MP4?'): return
  if mode in ('queue_mp4','queue_capcut'):
   queue.append((mode.replace('queue_mp4','render').replace('queue_capcut','capcut'),dict(c))); status.insert('end',f'Đã thêm {c["name"]} | Hàng đợi: {len(queue)}\n'); return
  if busy: return
  busy=True
  for b in buttons: b.config(state='disabled')
  bar['value']=0
  def work():
   def log(s):
    with (Path(c['out'])/'run_log.txt').open('a',encoding='utf-8') as f: f.write(s+'\n')
    root.after(0,lambda: (status.insert('end',s+'\n'),status.see('end')))
   try:
    log("=== V6.8 PRO TURBO | bắt đầu phiên mới ===")
    key=json.dumps({k:v for k,v in c.items() if k not in ('out','name','draft_root','sample','gpu','background','blur','transition','transition_time','iz','vz','res')},sort_keys=True)
    if key in cached and mode!='check': parts=cached[key]; log('Dùng timeline đã kiểm tra trong phiên này')
    else: parts=plan(c,log); cached.clear(); cached[key]=parts
    (Path(c['out'])/(c['name']+'.timeline.json')).write_text(json.dumps(parts,ensure_ascii=False,indent=2),encoding='utf-8'); log('Kiểm tra thành công'); root.after(0,lambda:bar.configure(value=100 if mode=="check" else 0))
    if mode=='render': render(c,parts,log,lambda p:root.after(0,lambda:bar.configure(value=p)))
    if mode=='capcut':
     from capcut import export
     export(c,parts,log); root.after(0,lambda:bar.configure(value=100))
    if mode in ('render','capcut'):
     try:
      import winsound
      winsound.Beep(1000,200)
     except Exception: pass
   except Exception as e:
    import traceback
    log('LỖI: '+str(e)); log(traceback.format_exc())
   finally: root.after(0,finish)
  threading.Thread(target=work,daemon=True).start()
 def finish():
  nonlocal busy
  busy=False
  for b in buttons: b.config(state='normal')
  if queue_running[0]: next_job()
 queue_running=[False]
 def next_job():
  if busy:return
  if not queue: queue_running[0]=False; return
  m,c=queue.pop(0); start(m,c)
  if not busy: root.after(0,next_job)
 def run_queue():
  queue_running[0]=True; next_job()
 for j,(l,m) in enumerate([('KIỂM TRA TƯ LIỆU','check'),('XUẤT MP4','render'),('XUẤT CAPCUT','capcut')]):
  b=ttk.Button(panel,text=l,command=lambda m=m:start(m)); b.grid(row=row,column=j,sticky='ew',pady=8); buttons.append(b)
 ttk.Button(panel,text='Mở thư mục xuất',command=lambda:os.startfile(vals['out'].get()) if Path(vals['out'].get()).is_dir() else None).grid(row=row+1,column=2)
 q=ttk.Frame(panel); q.grid(row=row+2,columnspan=4,sticky='ew')
 for label,cmd in [('Thêm MP4',lambda:start('queue_mp4')),('Thêm CapCut',lambda:start('queue_capcut')),('Chạy hàng đợi',run_queue),('Dừng sau job',lambda:queue_running.__setitem__(0,False)),('Xóa hàng đợi',queue.clear)]: ttk.Button(q,text=label,command=cmd).pack(side='left',padx=2)
 root.mainloop()
if __name__=='__main__': main()
