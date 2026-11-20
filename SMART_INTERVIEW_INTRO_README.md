# SMART INTERVIEW INTRO, integrated preview

The main `khiem_ui.py` now has an opt-in interview folder and checkbox. When enabled for MP4 or CapCut export, it scans interview videos with faster-whisper, compares speech against the earliest numbered opening TXT, exports the highest ranked candidate with original interview audio, prepends it to the ordinary parts list, and offsets later scene timestamps. Interview duration never exceeds 30 seconds. Existing app.py and capcut.py were not overwritten.

Install dependencies on Windows: `pip install faster-whisper`; FFmpeg and FFprobe must be available on PATH. First Whisper model use may download a model.

**Limitations:** This is an unverified integrated preview. Ranking uses transcript word overlap, not identity recognition or deep semantic matching. The AI voice MP3 is not used in selection. No automatic logo cropping or face-aware framing. The MP4 and CapCut export paths have not been tested with an actual interview video; CapCut audio handling for video-backed audio requires validation. Existing voice narration is retained after the intro. If no sufficiently relevant speech is found, the export fails safely instead of silently choosing a random interview.

Do not claim interview footage is licensed or that synthesized narration is authentic celebrity speech. Confirm speaker identity, editorial context and rights before publishing.
