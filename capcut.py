"""Editable draft writer based on the supplied dual-timeline schema."""
import json,uuid,copy,time,os,subprocess,shutil
from pathlib import Path

def uid(): return str(uuid.uuid4()).upper()
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,d): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
def export(c,parts,log):
 bundled=Path(__file__).resolve().parent/'template'
 required=('draft_content.json','draft_meta_info.json','Timelines/project.json','timeline_layout.json','draft_virtual_store.json')
 def valid(p): return all((p/f).is_file() for f in required)
 raw=str(c.get('sample','')).strip().strip('"')
 sample=Path(raw) if raw else bundled
 if not valid(sample):
  matches=[x for x in sample.iterdir() if x.is_dir() and valid(x)] if sample.is_dir() else []
  if len(matches)==1: sample=matches[0]
  elif valid(bundled):
   log('Mẫu đã chọn không hợp lệ; dùng mẫu tích hợp: '+str(bundled)); sample=bundled
  else: raise ValueError('Thiếu mẫu tích hợp. Giải nén toàn bộ ZIP, không chạy trực tiếp trong ZIP.')
 log('Mẫu CapCut: '+str(sample))
 d=read(sample/'draft_content.json'); meta=read(sample/'draft_meta_info.json'); project=read(sample/'Timelines/project.json'); layout=read(sample/'timeline_layout.json'); store=read(sample/'draft_virtual_store.json')
 root=Path(str(c.get('draft_root') or Path(os.environ.get('LOCALAPPDATA',''))/'CapCut/User Data/Projects/com.lveditor.draft').strip().strip(chr(34))).expanduser()
 if (root/'Projects/com.lveditor.draft').is_dir(): root=root/'Projects/com.lveditor.draft'
 log('Nơi lưu CapCut: '+str(root))
 if root.is_dir() and (root/'com.lveditor.draft').is_dir(): root=root/'com.lveditor.draft'
 if not root.is_dir(): raise ValueError('Chọn thư mục lưu dự án CapCut thực tế (com.lveditor.draft)')
 orig=d['materials']; templates={}; extras={m['id']:(k,m) for k,ls in orig.items() if isinstance(ls,list) for m in ls if isinstance(m,dict) and 'id' in m}
 for tr in d['tracks']:
  for s in tr['segments']:
   k,m=extras[s['material_id']]; kind='audio' if k=='audios' else 'image' if m['type']=='photo' else 'video'; templates[kind]=(tr,s,m,k)
 if not all(k in templates for k in ('audio','image','video')): raise ValueError('Mẫu thiếu ảnh/video/voice')
 zoom_template=templates['image'][1]['common_keyframes'][0]; mts={k:[] if isinstance(v,list) else copy.deepcopy(v) for k,v in orig.items()}; tracks={}
 for kind in ('video','audio'):
  tracks[kind]=copy.deepcopy(templates[kind][0]); tracks[kind].update(id=uid(),segments=[])
 now=int(time.time()*1e6); tid=uid(); pid=uid(); dest=root/(c['name']+'_'+pid[:8]); dt=dest/'Timelines'/tid; entries=[]; seen={}; probes={}
 def probe(path):
  if path not in probes:
   raw=subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',path],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)); probes[path]=json.loads(raw)
  return probes[path]
 def add(kind,path,start,end,source_start,effect='Tĩnh'):
  path=str(Path(path).resolve()).replace('\\','/'); length=end-start
  if length<=0:return
  _,s,m,k=templates[kind]; s=copy.deepcopy(s); m=copy.deepcopy(m); info=probe(path); streams=info['streams']; visual=next((v for v in streams if v['codec_type']=='video'),{}); width=visual.get('width',0); height=visual.get('height',0); full=10800000000 if kind=='image' else max(source_start+length,round(float(info['format'].get('duration',0))*1e6))
  if (kind,path) not in seen:
   mid=uid(); m.update(id=mid,unique_id=uuid.uuid4().hex,path=path,duration=full)
   if kind!='audio': m.update(width=width,height=height,has_audio=any(v['codec_type']=='audio' for v in streams))
   for field in ('name','material_name'):
    if field in m:m[field]=Path(path).name
   mts[k].append(m); seen[(kind,path)]=mid
   entry=copy.deepcopy(next(x for x in meta['draft_materials'][0]['value'] if x['metetype']=={'audio':'music','image':'photo','video':'video'}[kind])); entry.update(id=uid(),file_Path=path,extra_info=Path(path).name,width=width,height=height,duration=length if kind=='image' else full,create_time=now//1000000,import_time=now//1000000,import_time_ms=now); entry['roughcut_time_range']={'start':-1,'duration':-1} if kind=='image' else {'start':0,'duration':full}; entries.append(entry)
  refs=[]
  for old in s['extra_material_refs']:
   if old not in extras:continue
   ek,em=extras[old]; em=copy.deepcopy(em); em['id']=uid()
   if ek=='canvases':
    if c.get('background')=='Nền mờ':em.update(type='canvas_blur',blur=min(1,max(0,float(c.get('blur',30))/80)))
    else:em.update(type='canvas_color',color='#000000',blur=0)
   mts[ek].append(em); refs.append(em['id'])
  s.update(id=uid(),material_id=seen[(kind,path)],extra_material_refs=refs,common_keyframes=[],keyframe_refs=[],source_timerange={'start':source_start,'duration':length},target_timerange={'start':start,'duration':length},speed=1.,volume=1. if kind=='audio' else 0.)
  if kind!='audio':
   z=float(c['iz'] if kind=='image' else c['vz'])/100; a,b=(1,z) if effect=='Zoom in' else (z,1) if effect=='Zoom out' else (1,1); a,b=(z,z) if kind=='video' else (a,b); s['clip']['scale']={'x':a,'y':a}
   if a!=b:
    key=copy.deepcopy(zoom_template); key['id']=uid(); key['keyframe_list']=[]
    for frac in (0,.25,.5,.75,1):
     import math
     pt=copy.deepcopy(zoom_template['keyframe_list'][0]); pt.update(id=uid(),time_offset=round(frac*length),values=[a+(b-a)*(1-math.cos(math.pi*frac))/2]); key['keyframe_list'].append(pt)
    s['common_keyframes']=[key]
  tracks['audio' if kind=='audio' else 'video']['segments'].append(s)
 intro=c.get('_interview_intro')
 elapsed=0.
 if intro:
  us=round(float(intro['source_start'])*1e6)
  end=round(float(intro['duration'])*1e6)
  add('video',intro['source'],0,end,us,'Tĩnh')
  # CapCut music material needs an audio file, not an MP4 path.
  audio_dir=Path(c['out'])/'_interview_audio'
  audio_dir.mkdir(parents=True,exist_ok=True)
  audio_path=audio_dir/(Path(intro['source']).stem+'_'+str(round(float(intro['source_start'])*1000))+'_'+str(round(float(intro['duration'])*1000))+'.wav')
  if not audio_path.is_file() or audio_path.stat().st_size<1024:
   tmp_audio=audio_path.with_suffix('.tmp.wav')
   cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(intro['source_start']),'-i',str(intro['source']),'-t',str(intro['duration']),'-vn','-ar','48000','-ac','2','-c:a','pcm_s16le',str(tmp_audio)]
   subprocess.run(cmd,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),capture_output=True)
   os.replace(tmp_audio,audio_path)
  add('audio',str(audio_path),0,end,0)
  log('CapCut intro: video + original audio on separate editable tracks')
  elapsed=float(intro['duration'])
 for p in parts:
  begin=round(elapsed*1e6); elapsed+=p['duration']; end=round(elapsed*1e6); add('audio',p['voice'],begin,end,0)
  clips=p['clips']
  for i,s in enumerate(clips):
   start=begin if i==0 else round((s['start']+float(intro['duration']) if intro else s['start'])*1e6); stop=end if i==len(clips)-1 else round((clips[i+1]['start']+float(intro['duration']) if intro else clips[i+1]['start'])*1e6); add(s['type'],s['source'],start,stop,round(s['source_start']*1e6),s['effect'])

 # Add native editable Vietnamese subtitle track using the user-provided CapCut schema.
 subtitle_path=Path(c['out'])/'_vietsub_review'/(c['name']+'.vi.srt')
 if subtitle_path.is_file():
  try:
   import re
   ref=read(Path(__file__).resolve().parent/'capcut_v11_reference.json')
   text_track=copy.deepcopy(ref['text_track']); text_track.update(id=uid(),segments=[])
   def stamp(value):
    h,m,tail=value.replace('.',',').split(':')
    sec,ms=tail.split(',')
    return (int(h)*3600+int(m)*60+int(sec))*1000000+int(ms.ljust(3,'0')[:3])*1000
   raw_srt=subtitle_path.read_text(encoding='utf-8-sig')
   for block in re.split(r'\\n\\s*\\n',raw_srt.strip()):
    lines=block.strip().splitlines()
    times=next((line for line in lines if ' --> ' in line),None)
    if not times:continue
    idx=lines.index(times); start_text,end_text=times.split(' --> ',1)
    start_us=stamp(start_text.strip()); end_us=stamp(end_text.strip().split()[0])
    if end_us<=start_us:continue
    caption='\\n'.join(lines[idx+1:]).strip()
    if not caption:continue
    mat=copy.deepcopy(ref['text_material']); mat['id']=uid()
    mat['name']='VIETSUB KIEM TRA'
    rich=json.loads(mat['content']); rich['text']=caption
    for style in rich.get('styles',[]):
     style['range']=[0,len(caption)]
     style.get('font',{}).pop('path',None)
    mat['content']=json.dumps(rich,ensure_ascii=False)
    mat['base_content']=mat['content']
    mat['recognize_text']=caption
    mat['words']=[]
    mat['current_words']=[]
    mts['texts'].append(mat)
    seg=copy.deepcopy(ref['text_segment']);seg['id']=uid();seg['material_id']=mat['id']
    seg['extra_material_refs']=[]
    seg['target_timerange']={'start':start_us,'duration':end_us-start_us}
    seg['render_index']=14000+len(text_track['segments'])
    text_track['segments'].append(seg)
   if text_track['segments']:
    tracks['vietsub']=text_track
    log('CapCut: đã chèn '+str(len(text_track['segments']))+' đoạn Vietsub native chỉnh sửa được')
  except Exception as exc:
   log('VIETSUB: Không thể chèn text track, giữ SRT để nhập thủ công: '+str(exc))
 # Safe native fade transition. No overlap or time shifts, never on interview.
 if str(c.get('transition','')).lower() not in ('không','none','off','cut','tắt'):
  try:
   ref=read(Path(__file__).resolve().parent/'capcut_v11_reference.json')
   fade=next(t for t in ref['transitions'] if t['name']=='Mờ đen')
   video_segments=tracks['video']['segments']
   video_segments.sort(key=lambda x:x['target_timerange']['start'])
   added=0
   for prev,cur in zip(video_segments,video_segments[1:]):
    left=prev['target_timerange'];right=cur['target_timerange']
    if left['start']+left['duration']!=right['start']:continue
    if min(left['duration'],right['duration'])<1200000:continue
    if intro and right['start']<=round(float(intro['duration'])*1e6):continue
    # Limit effects to every third eligible boundary, avoiding visual overload.
    if added%3!=0:
     added+=1;continue
    transition=copy.deepcopy(fade);transition['id']=uid()
    transition['duration']=min(466666,left['duration']//4,right['duration']//4)
    mts['transitions'].append(transition)
    cur.setdefault('extra_material_refs',[]).append(transition['id'])
    added+=1
   log('CapCut: đã thêm chuyển cảnh native không chồng thời gian tại các điểm phù hợp')
  except Exception as exc:
   log('CapCut: bỏ qua transition chưa tương thích: '+str(exc))
 for track in tracks.values(): track['segments'].sort(key=lambda seg: (seg['target_timerange']['start'],seg['id']))
 w,h=map(int,c['res'].split('x')); d.update(path='',id=tid,name=c['name'],duration=round(elapsed*1e6),fps=float(c['fps']),tracks=list(tracks.values()),materials=mts,create_time=now,update_time=now); d['canvas_config'].update(width=w,height=h,ratio='16:9')
 meta.update(draft_id=pid,draft_name=c['name'],draft_fold_path=dest.as_posix(),draft_root_path=str(root),tm_duration=d['duration'],tm_draft_create=now,tm_draft_modified=now,draft_timeline_materials_size_=sum(Path(p).stat().st_size for _,p in seen)); meta['draft_materials'][0]['value']=entries
 project.update(id=uid(),main_timeline_id=tid,create_time=now,update_time=now); project['timelines'][0].update(id=tid,create_time=now,update_time=now); layout['dockItems'][0]['timelineIds']=[tid]; store['draft_virtual_store'][1]['value']=[{'child_id':e['id'],'parent_id':''} for e in entries]
 # Write matching root and nested timeline, without stale attachment IDs.
 try:
  for folder in (dest,dt):
   for name in ('draft_content.json','draft_content.json.bak','template-2.tmp'):write(folder/name,d)
  write(dt/'template.tmp',d); write(dest/'draft_meta_info.json',meta); write(dest/'Timelines/project.json',project); write(dest/'Timelines/project.json.bak',project); write(dest/'timeline_layout.json',layout); write(dest/'draft_virtual_store.json',store)
  first=next(iter(tracks['video']['segments'])); source=next(x['path'] for x in mts['videos'] if x['id']==first['material_id']); subprocess.run(['ffmpeg','-v','error','-y','-i',source,'-frames:v','1','-vf','scale=480:-2',str(dest/'draft_cover.jpg')],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),capture_output=True)
  if (dest/'draft_cover.jpg').exists():shutil.copyfile(dest/'draft_cover.jpg',dt/'draft_cover.jpg')
 except Exception:
  shutil.rmtree(dest,ignore_errors=True); raise
 log('Đã ghi dự án: '+str(dest)+' | Mở lại CapCut để kiểm tra. Chuyển cảnh và Vietsub native thử nghiệm; kiểm tra CapCut trước khi xuất.'); return dest
