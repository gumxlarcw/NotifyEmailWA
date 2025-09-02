@echo off
setlocal enabledelayedexpansion

REM ====== KONFIGURASI DASAR ======
set "BASE=D:\WISNU\_dev\email_notification"
set "LOGFILE=%BASE%\restart.log"
set "READYFLAG=%BASE%\whatsapp-bot\wa_ready.flag"
set "NODELOG=%BASE%\whatsapp-bot\logs\node_run.log"
set "TIMEOUT_READY=600"

REM ====== NOTIFIKASI BALON (opsional) ======
set "popup=powershell -WindowStyle Hidden -Command Add-Type -AssemblyName System.Windows.Forms; $n=New-Object System.Windows.Forms.NotifyIcon; $n.Icon=[System.Drawing.SystemIcons]::Information; $n.Visible=$true; $n.ShowBalloonTip(5000, 'Email Monitor', '!msg!', [System.Windows.Forms.ToolTipIcon]::Info)"

REM ====== CEK FOLDER ======
if not exist "%BASE%" (
  echo [%date% %time%] ❌ BASE folder tidak ditemukan: %BASE% >> "%LOGFILE%"
  echo BASE folder tidak ditemukan: %BASE%
  goto :eof
)

REM ====== LOG START ======
set "msg=🚀 Email Monitor Started"
echo [%date% %time%] !msg! >> "%LOGFILE%"
%popup%

:loop
REM ====== BERSIHKAN ======
if exist "%READYFLAG%" del /f /q "%READYFLAG%" >nul 2>&1
if exist "%NODELOG%"  del /f /q "%NODELOG%"  >nul 2>&1

REM ====== MULAI WHATSAPP BOT DI JENDELA CMD BARU ======
set "msg=🔄 Starting whatsapp-bot (node index.js)"
echo [%date% %time%] !msg! >> "%LOGFILE%"
%popup%

if not exist "%BASE%\whatsapp-bot\logs" mkdir "%BASE%\whatsapp-bot\logs"

start "WA BOT" /D "%BASE%\whatsapp-bot" cmd /k "node index.js"

REM ====== TUNGGU FILE READY ======
set /a waited=0
:wait_wa_ready
timeout /t 1 /nobreak >nul
set /a waited+=1

if exist "%READYFLAG%" (
  set "msg=✅ WhatsApp Web READY, mulai check_mail.py"
  echo [%date% %time%] !msg! >> "%LOGFILE%"
  %popup%
  goto :start_py
)

if !waited! GEQ %TIMEOUT_READY% (
  set "msg=⏱️ Timeout menunggu READY (%TIMEOUT_READY%s), restart"
  echo [%date% %time%] !msg! >> "%LOGFILE%"
  if exist "%NODELOG%" (
    echo --- node_run.log (timeout) --- >> "%LOGFILE%"
    type "%NODELOG%" >> "%LOGFILE%"
    echo --- end of node_run.log --- >> "%LOGFILE%"
  )
  %popup%
  goto :restart_both
)

REM Log heartbeat ringan (hanya 10s pertama)
if !waited! LEQ 10 (
  echo [%date% %time%] Waiting WA READY... !waited!/!TIMEOUT_READY!s >> "%LOGFILE%"
)
goto :wait_wa_ready

:start_py
set "msg=🔄 Starting check_mail.py (python)"
echo [%date% %time%] !msg! >> "%LOGFILE%"
%popup%
start "" /min cmd /c "cd /d %BASE%\email-checker && python check_mail.py"

:waitloop
timeout /t 10 /nobreak >nul
tasklist /fi "imagename eq python.exe" | findstr /i "python.exe" >nul
set "py=!errorlevel!"

REM Catatan: Tidak lagi cek node.exe karena sudah tidak relevan

if !py! == 0 goto :waitloop

set "msg=⚠️ check_mail.py exited unexpectedly. Restarting all..."
echo [%date% %time%] !msg! >> "%LOGFILE%"
%popup%
goto :restart_both

:restart_both
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im node.exe   >nul 2>&1
if exist "%READYFLAG%" del /f /q "%READYFLAG%" >nul 2>&1

REM Tunggu node.exe benar-benar mati
:wait_node_kill
tasklist /fi "imagename eq node.exe" | findstr /i "node.exe" >nul
if not errorlevel 1 (
  echo [%date% %time%] ⏳ Menunggu node.exe benar-benar mati... >> "%LOGFILE%"
  timeout /t 1 >nul
  goto :wait_node_kill
)

set "msg=🔁 Restarting both in 5 seconds..."
echo [%date% %time%] !msg! >> "%LOGFILE%"
%popup%
timeout /t 5 /nobreak >nul
goto :loop
