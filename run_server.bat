@echo off
cd /d "%~dp0"
python server.py > server.out.log 2> server.err.log
