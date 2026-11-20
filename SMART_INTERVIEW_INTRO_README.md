# SMART INTERVIEW INTRO, first release

Run: `python smart_interview_intro.py`.

Requires `ffmpeg`, `ffprobe` on PATH and `pip install faster-whisper`. First Whisper model download requires internet; later runs can use cached model. Choose interview video folder and opening TXT. Click Analyze, inspect ranked candidates and export a selected MP4. Video and original interview audio are preserved. Hard maximum 30 seconds. No input videos are modified.

**Current limitations:** English transcription only, CPU inference can take time; uses lexical similarity to opening TXT, not deep semantic understanding. Does not yet read AI voice MP3, confirm celebrity identity, crop logos, concatenate with AI narration, or insert into CapCut project. Human review is essential. This is a separate tool, not an integrated feature of the main app. Do not present voiceover as authentic celebrity speech. Only use footage with appropriate rights.

Do not merge until you are ready to try the new standalone feature. Existing app.py, capcut.py and khiem_ui.py remain unchanged in this PR.
