@echo off
echo --- Read new dir first if it's existed.
set "OLD_PATH=.\ASM"
set "NEW_PATH=.\ASM\new"
if exist "%NEW_PATH%" (
    python Script_assembler_re.py "%NEW_PATH%"
) else (
    python Script_assembler_re.py "%OLD_PATH%"
)

pause
