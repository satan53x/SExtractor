@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Assemble all *.asm.txt files in a directory back to *.SDT without the .rebuild suffix.
rem Usage:
rem   assemble_all.bat              rem assemble .\new\*.asm.txt
rem   assemble_all.bat path\to\dir  rem assemble that directory
rem   set PYTHON=py -3              rem optional: override Python command

cd /d "%~dp0"

set "TARGET_DIR=%~1"
if "%TARGET_DIR%"=="" set "TARGET_DIR=new"

set "PY_CMD=%PYTHON%"
if "%PY_CMD%"=="" set "PY_CMD=python"

if not exist "%TARGET_DIR%\" (
    echo [ERROR] Directory not found: "%TARGET_DIR%"
    exit /b 1
)

if not exist "assembler.py" (
    echo [ERROR] assembler.py not found next to this batch file.
    exit /b 1
)

set /a COUNT=0
set /a FAIL=0

for %%F in ("%TARGET_DIR%\*.asm.txt") do (
    if exist "%%~fF" (
        set "NAME=%%~nxF"
        set "BASE=!NAME:.asm.txt=!"
        set "OUT=%%~dpF!BASE!.SDT"
        %PY_CMD% "assembler.py" "%%~fF" -o "!OUT!"
        if errorlevel 1 (
            echo [FAIL] %%~fF
            set /a FAIL+=1
        ) else (
            set /a COUNT+=1
        )
    )
)

echo Assembled: %COUNT%
echo Failed: %FAIL%

if %COUNT% EQU 0 (
    echo [WARN] No *.asm.txt files found in "%TARGET_DIR%".
)

if %FAIL% NEQ 0 exit /b 1
exit /b 0
