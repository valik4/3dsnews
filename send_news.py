import subprocess
import requests
import time
import os
import platform
import json
import schedule
import threading
import telebot
from datetime import datetime
from telebot import apihelper

# --- НАЛАШТУВАННЯ ---
BOT_TOKEN = "8545688226:AAEbYYpkvrDCE_eC2QO1HYpdSUzDY8UHmpA"
CHAT_ID = "-1003704953361"
THREAD_ID = 289
ADMIN_ID = 459954163  

# АВТО-ВИБІР ШЛЯХУ ДО БІНАРНИКА
if platform.system() == "Windows":
    EXE_PATH = "./hbnews.exe"
else:
    # На Raspberry Pi файл має називатися саме так після компиляції
    EXE_PATH = "./hbnews_arm"

JSON_PATH = os.path.join("lists", "list_hb.json")
SCHEDULED_TIMES = ["12:00", "15:00", "18:00", "19:30", "21:00"]

bot = telebot.TeleBot(BOT_TOKEN)

def sync_with_git():
    """Функція для автоматичного пушу оновлених даних на GitHub"""
    try:
        # Перевіряємо, чи ми в репозиторії
        if not os.path.isdir(".git"):
            print("ℹ️ Git не ініціалізовано, пропускаю синхронізацію.")
            return

        # Додаємо зміни
        subprocess.run(["git", "add", "lists/", "history/"], check=True)
        
        # Перевіряємо, чи є що комітити
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            commit_msg = f"Auto-update: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            subprocess.run(["git", "commit", "-m", commit_msg], check=True)
            # Пушимо в main (або master, залежно від гілки)
            subprocess.run(["git", "push"], check=True)
            print("✅ Дані успішно відправлено на GitHub")
        else:
            print("ℹ️ Змін у файлах даних не виявлено.")
    except Exception as e:
        print(f"⚠️ Помилка Git: {e}")

def job():
    print(f"\n--- Запуск перевірки ({datetime.now().strftime('%H:%M:%S')}) ---")
    try:
        # 1. Запуск Go-утиліти
        if os.path.exists(EXE_PATH):
            print(f"Запуск {EXE_PATH}...")
            subprocess.run([EXE_PATH], check=True)
        else:
            print(f"❌ Помилка: Бінарник {EXE_PATH} не знайдено!")
            return

        # 2. Твоя логіка обробки JSON та відправки в Telegram
        # (Тут має бути твій код, який зчитує JSON і шле bot.send_message)
        print("Обробка новин та відправка в Telegram...")
        
        # [МІСЦЕ ДЛЯ ТВОГО ЦИКЛУ ОБРОБКИ JSON]

        # 3. Синхронізація з GitHub після успішної відправки
        sync_with_git()
        
    except Exception as e:
        print(f"❌ Помилка у виконанні завдання: {e}")

def run_bot():
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Помилка бот-полінгу: {e}")
            time.sleep(15)

if __name__ == "__main__":
    print(f"=== Система запущена на {platform.system()} ===")
    
    # Запуск бота в окремому потоці
    threading.Thread(target=run_bot, daemon=True).start()
    
    # Реєстрація розкладу
    for t in SCHEDULED_TIMES:
        schedule.every().day.at(t).do(job)

    while True:
        schedule.run_pending()
        time.sleep(60)