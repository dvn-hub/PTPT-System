#!/bin/bash

# Mengecek apakah Bang Isa memasukkan pesan commit
if [ -z "$1" ]
then
  echo "⚠️ Waduh, pesan update-nya kosong, Bang!"
  echo "👉 Cara pakai yang bener: ./push.sh \"Pesan update Abang di sini\""
  exit 1
fi

echo "🚀 Memulai sinkronisasi DivineBlox ke GitHub..."

# Mengeksekusi rentetan perintah Git
git add .
git commit -m "$1"
git push origin main

echo "✅ Selesai, Bang! Kodingan terbaru udah mendarat aman di awan."
