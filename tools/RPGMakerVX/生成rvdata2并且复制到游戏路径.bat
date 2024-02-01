@echo off
chcp 65001 > nul

.\rvdata2_import.exe

set source_folder=".\Data"
set destination_folder="游戏路径\Data"

if not exist "%destination_folder%" (
  echo 目标文件夹不存在，请检查目标路径！
  pause
) else (
  robocopy "%source_folder%" "%destination_folder%"
  echo Done.
  @rem pause
)
