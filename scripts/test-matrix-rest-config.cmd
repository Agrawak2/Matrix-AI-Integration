@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0test-matrix-rest-config.ps1" %*
