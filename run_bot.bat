@echo off
REM Batch file to run the hybrid Telegram bot with unbuffered output
REM This ensures all print statements appear immediately in the console

echo Starting Telegram Bot with unbuffered output...
echo.

REM Run Python with -u flag for unbuffered output
python -u hybrid_main.py

REM If the script exits, pause so you can see any error messages
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Bot exited with error code: %ERRORLEVEL%
    pause
)
