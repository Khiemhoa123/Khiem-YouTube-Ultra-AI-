@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   KHIEM YOUTUBE - TAO GOI UPDATE V11.4
echo ==========================================
python make_portable_release.py
if errorlevel 1 (
  echo.
  echo TAO GOI THAT BAI. Chup anh cua so nay gui ChatGPT.
  pause
  exit /b 1
)
echo.
echo Mo thu muc portable_release_assets de tai 2 file len GitHub.
explorer "%~dp0portable_release_assets"
pause
