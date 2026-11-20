Khiem YouTube AUTO UPDATE V1

This is a manual, opt-in updater for the private GitHub repository.

FIRST INSTALL:
1. Install Git for Windows and authenticate with GitHub Credential Manager or GitHub Desktop.
2. Copy khiem_auto_update.py into the running app folder beside app.py.
3. Run: python khiem_auto_update.py
4. Click Check updates, review list, close the editor, then Install update.
5. Use Restore backup if needed.

SAFETY:
Updates existing root-level Python files only. Never updates itself, settings, media, databases or models. Checks Python syntax. Backs up before replacing files. Requires private repository read credentials. Only install reviewed changes from main. Does not verify signatures or guarantee app compatibility. New modules and dependencies require manual reviewed installation. No unattended updates.
