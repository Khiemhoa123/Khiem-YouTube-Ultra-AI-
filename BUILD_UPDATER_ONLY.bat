@echo off
cd /d "%~dp0"
title KHIEM YOUTUBE - BUILD UPDATER ONLY
echo BUILD RIENG KHIEMUPDATER.EXE (KHONG BUILD LAI 4GB)
echo.
python -u build_updater_only.py
if errorlevel 1 (
 echo.
 echo BUILD THAT BAI. CHUP ANH GUI CHATGPT.
 pause
 exit /b 1
)
echo.
echo THANH CONG! MO THU MUC PORTABLE.
explorer "%~dp0dist_portable\KhiemYoutube"
pause
