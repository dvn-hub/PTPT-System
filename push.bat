@echo off
if "%~1"=="" (
    echo [!] Waduh, pesan update-nya kosong, Bang!
    echo [!] Cara pakai yang bener: .\push.bat "Pesan update Abang di sini"
    exit /b 1
)

echo [🚀] Memulai sinkronisasi kodingan Laptop ke GitHub...

git add .
git commit -m "%~1"
git push origin main

echo [✅] Selesai, Bang Isa! Kodingan VS Code udah mendarat di awan.