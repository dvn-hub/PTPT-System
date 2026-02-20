#!/bin/bash

echo "⬇️ Sedang menarik kodingan terbaru dari GitHub..."
cd /opt/patungan_bot
git pull origin main

echo "🔄 Me-restart sistem DivineBlox..."
sudo systemctl restart divineblox

echo "✅ Berhasil, Bang! Panel web udah pakai versi paling baru."
