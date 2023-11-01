@echo off
cd /d "%~dp0"

set scriptdir=.\Script
set txtdir=.\Script.txt

python scpacker.py unpack %scriptdir% %txtdir%

