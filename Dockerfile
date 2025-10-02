# Python 3.10.12 ga asoslangan image, ffmpeg o‘rnatilgan
FROM python:3.10.12-slim

# ffmpeg ni o‘rnatish
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Ishchi katalogni sozlash
WORKDIR /app

# Loyiha fayllarini nusxalash
COPY . .

# Python kutubxonalarni o‘rnatish
RUN pip install --no-cache-dir -r requirements.txt

# Botni ishga tushirish buyrug‘i
CMD ["python", "bot.py"]