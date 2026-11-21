# SMART VIETSUB V11

This update creates Vietnamese review subtitles for narrated Voice tracks and
the original-audio interview intro. It does not burn subtitles into exported MP4.

## Windows setup
1. Update `khiem_ui.py` and add `smart_vietsub_v11.py` via GitHub updater.
   Choose FULL mode to include the new module.
2. Install optional dependencies in the same Python environment:
   `python -m pip install faster-whisper deep-translator`
3. Translation via deep-translator uses an online service and needs Internet.
4. Export a CapCut project. Subtitles appear at:
   `OUTPUT/_vietsub_review/PROJECT.vi.srt`
   and `CapCutDraft/VIETSUB_KIEM_TRA.srt`.
5. Import `VIETSUB_KIEM_TRA.srt` in CapCut captions. Native automatic
   insertion of editable text tracks is NOT yet implemented.
6. MP4 rendering is unchanged and does not include these subtitles.

## Limitations
- Recognition and translation can make mistakes; compare original SRT.
- Only narration and intro interview audio are transcribed. Audio from
  archival footage/cutaways is not included in this version.
- CapCut's internal JSON text-track schema needs a verified template
  before safely injecting an editable track.
- Run a short project before batch export.
