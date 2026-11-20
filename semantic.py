"""Local semantic ranking. The model scores scenes, not biometric identity."""
import os, json, subprocess, io, re, tempfile
from pathlib import Path
def model_path(kind):
 base=Path(__file__).resolve().parent
 roots=[Path(os.environ['CAPCUT_AI_MODELS'])] if os.environ.get('CAPCUT_AI_MODELS') else []
 roots += [base/'models', *sorted(base.parent.glob('*/models'),reverse=True)]
 roots += list((Path.home() / '.cache/huggingface/hub' / ('models--openai--clip-vit-base-patch32' if kind=='clip' else 'models--Systran--faster-whisper-base') / 'snapshots').glob('*'))
 for root in roots:
  for p in (root/kind,root):
   if not (p/'config.json').is_file(): continue
   if kind=='clip':
    if (p/'preprocessor_config.json').is_file() and ((p/'model.safetensors').is_file() or (p/'pytorch_model.bin').is_file()) and ((p/'tokenizer.json').is_file() or ((p/'vocab.json').is_file() and (p/'merges.txt').is_file())): return p.resolve()
   elif (p/'model.bin').is_file(): return p.resolve()
 raise FileNotFoundError(f'Thiếu model {kind} hợp lệ. Chạy CAI_AI.bat hoặc chép models từ bản cũ.')
class Semantic:
 def __init__(self,log,mode="Smart"):
  import torch
  from transformers import CLIPModel, CLIPProcessor
  from PIL import Image
  self.torch=torch; self.Image=Image; self.log=log; self.cache={}; self.texts={}
  self.mode=mode; self.db=__import__("sqlite3").connect(str(Path(__file__).parent/"ai_cache.sqlite")); self.db.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v BLOB)"); self.device='cuda' if torch.cuda.is_available() else 'cpu'
  root=model_path('clip'); log('CLIP model: '+str(root))
  self.model=CLIPModel.from_pretrained(str(root),local_files_only=True).eval()
  try: self.model=self.model.to(self.device)
  except RuntimeError as e:
   log('CUDA lỗi; dùng CPU: '+str(e)); self.device='cpu'; self.model=self.model.to('cpu')
  self.processor=CLIPProcessor.from_pretrained(str(root),local_files_only=True)
  log('CLIP local: '+self.device)
 def feature(self,kind,path,start):
  step={"Fast":10,"Smart":5,"Deep":2}[self.mode]; start=int(start/step)*step if kind=="video" else 0; st=Path(path).stat(); key=(str(path),kind,start,st.st_size,st.st_mtime_ns,"clip-base-v1"); disk=json.dumps(key)
  hit=self.db.execute("SELECT v FROM cache WHERE k=?",(disk,)).fetchone()
  if hit: return self.torch.tensor(__import__("numpy").frombuffer(hit[0],dtype="float32").copy()).reshape(1,-1)
  if key in self.cache:return self.cache[key]
  try:
   if kind=='image': im=self.Image.open(path).convert('RGB')
   else:
    data=subprocess.check_output(['ffmpeg','-v','error','-ss',str(start),'-i',str(path),'-frames:v','1','-vf','scale=320:-2','-f','image2pipe','-vcodec','png','-'],stderr=subprocess.DEVNULL)
    im=self.Image.open(io.BytesIO(data)).convert('RGB')
   with self.torch.inference_mode():
    v=self.model.get_image_features(**self.processor(images=im,return_tensors='pt').to(self.device)); v=v/v.norm(dim=-1,keepdim=True)
   self.cache[key]=v.cpu().float(); self.db.execute("INSERT OR REPLACE INTO cache VALUES (?,?)",(disk,self.cache[key].numpy().tobytes())); self.db.commit(); return self.cache[key]
  except Exception as e:
   self.log('Không đọc được khung hình: '+str(path)+' '+str(e)); self.cache[key]=None; return None
 def score(self,kind,path,start,length,query):
  query=query.strip() or 'archival documentary footage'
  if query not in self.texts:
   with self.torch.inference_mode():
    v=self.model.get_text_features(**self.processor(text=[query],return_tensors='pt',padding=True,truncation=True,max_length=77).to(self.device)); self.texts[query]=(v/v.norm(dim=-1,keepdim=True)).cpu()
  offsets=[0] if kind=='image' else [length*.5] if self.mode=="Fast" else [length*.2,length*.5,length*.8]
  values=[]
  for offset in offsets:
   v=self.feature(kind,path,start+offset)
   if v is not None:values.append(float((v*self.texts[query]).sum()))
  return sum(values)/len(values) if values else -1
 def transcribe(self,path):
  # Cache complete word-level transcripts; unchanged audio skips Whisper.
  p=Path(path).resolve()
  st=p.stat()
  key=json.dumps(['whisper-base-words-v1',str(p),st.st_size,st.st_mtime_ns])
  self.db.execute('CREATE TABLE IF NOT EXISTS transcripts (k TEXT PRIMARY KEY, v TEXT NOT NULL)')
  hit=self.db.execute('SELECT v FROM transcripts WHERE k=?',(key,)).fetchone()
  if hit:
   try:
    return [tuple(item) for item in json.loads(hit[0])]
   except (ValueError,TypeError):
    pass
  from faster_whisper import WhisperModel
  if not hasattr(self,'whisper'):
   self.whisper=WhisperModel(str(model_path('whisper')),device='cpu',compute_type='int8',local_files_only=True)
  import numpy as np
  raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(p),'-vn','-ac','1','-ar','16000','-f','f32le','-'])
  audio=np.frombuffer(raw,dtype='<f4').copy()
  seg,_=self.whisper.transcribe(audio,beam_size=1,word_timestamps=True)
  result=[(w.start,w.end,w.word) for s in seg for w in (s.words or [])]
  self.db.execute('INSERT OR REPLACE INTO transcripts(k,v) VALUES (?,?)',(key,json.dumps(result)))
  self.db.commit()
  return result

# KHIEM_V71_SMART_RANKING
from smart_v71 import install_smart_ranking
install_smart_ranking(Semantic)
