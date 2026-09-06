FROM python:3.11-slim

WORKDIR /app

# Копируем список библиотек и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все остальные файлы проекта
COPY . .

# Команда для запуска бота
CMD ["python", "bot.py"]