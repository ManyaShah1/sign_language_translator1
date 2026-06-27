@echo off
cd /d "%~dp0"
title Swayam Health - Remote Gateway Server Setup
echo ====================================================
echo      REMOTE GATEWAY ^& INFERENCE TUNNEL SERVER       
echo ====================================================
echo.

:: Check if node is in PATH
node -v >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [✓] Node.js is already installed.
    set NODE_CMD=node
    set NPM_CMD=npm
) else (
    echo [!] Node.js is not found on this system.
    echo.
    echo Preparing to download a portable Node.js environment...
    
    if not exist "%~dp0portable_node\node.exe" (
        echo Downloading portable Node.js v20.11.0 x64...
        powershell -Command "Invoke-WebRequest -Uri 'https://nodejs.org/dist/v20.11.0/node-v20.11.0-win-x64.zip' -OutFile '%~dp0node_portable.zip'"
        
        echo Extracting portable Node.js...
        powershell -Command "Expand-Archive -Path '%~dp0node_portable.zip' -DestinationPath '%~dp0node_portable_temp' -Force"
        
        echo Organizing files...
        xcopy /E /I /Y "%~dp0node_portable_temp\node-v20.11.0-win-x64" "%~dp0portable_node" >nul
        
        echo Cleaning temporary files...
        rd /S /Q "%~dp0node_portable_temp"
        del "%~dp0node_portable.zip"
        echo [✓] Portable Node.js environment ready.
    ) else (
        echo [✓] Existing portable Node.js found.
    )
    
    set NODE_CMD="%~dp0portable_node\node.exe"
    set NPM_CMD="%~dp0portable_node\npm.cmd"
)

:: Run npm install
echo.
echo Installing Node.js gateway dependencies...
call %NPM_CMD% install
if %ERRORLEVEL% neq 0 (
    echo.
    echo [-] Failed to install dependencies. Check your internet connection.
    pause
    exit /b %ERRORLEVEL%
)

:: Start the gateway server
echo.
echo ====================================================
echo Starting Node.js backend server...
echo ====================================================
echo.
call %NODE_CMD% "%~dp0server.js"

pause
