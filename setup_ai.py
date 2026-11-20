from pathlib import Path
from huggingface_hub import snapshot_download
root=Path(__file__).parent/'models'
snapshot_download('openai/clip-vit-base-patch32',local_dir=root/'clip',ignore_patterns=['*.h5','*.msgpack','*.ot','*.onnx','tf_*','flax_*'])
snapshot_download('Systran/faster-whisper-base',local_dir=root/'whisper')
print('AI models ready.')
