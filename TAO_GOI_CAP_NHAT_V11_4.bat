@echo off
setlocal
cd /d "%~dp0"
title KHIEM YOUTUBE - TAO GOI CAP NHAT V11.4
echo ==========================================
echo     TAO LAI GOI UPDATE V11.4 TU DAU
echo ==========================================
echo.
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -u "%~dp0make_portable_release.py"
) else (
  python -u "%~dp0make_portable_release.py"
)
if errorlevel 1 (
  echo.
  echo CO LOI! Chup anh cua so nay gui ChatGPT.
  pause
  exit /b 1
)
echo.
echo DA HOAN TAT. Mo thu muc chua ZIP va JSON...
explorer "%~dp0portable_release_assets"
pause
