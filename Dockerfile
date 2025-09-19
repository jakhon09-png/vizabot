# Python slim imagini ishlatamiz
FROM python:3.11-slim

# Tizim paketlarini o‘rnatamiz, shu jumladan ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Ishlash papkasini belgilaymiz
WORKDIR /app

# Requirements faylini ko‘chirish
COPY requirements.txt .

# Python qaramliklarini o‘rnatish
RUN pip install --no-cache-dir -r requirements.txt

# Loyihaning qolgan qismini ko‘chirish
COPY . .

# Botni ishga tushirish
CMD ["python3", "bot.py"]