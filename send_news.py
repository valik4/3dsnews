import subprocess
import requests
import time
import os
import re
import json
import schedule
import threading
import telebot
import platform
from telebot import apihelper
from datetime import datetime
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

# Фіксуємо час запуску
start_time = datetime.now()

# --- НАЛАШТУВАННЯ ---
BOT_TOKEN = "8545688226:AAEbYYpkvrDCE_eC2QO1HYpdSUzDY8UHmpA"
CHAT_ID = "-1003704953361"
THREAD_ID = 289
ADMIN_ID = 459954163  

import platform # Не забудь додати імпорт вгорі файлу!
if platform.system() == "Windows":
    EXE_PATH = "./hbnews.exe"
else:
    EXE_PATH = "./hbnews_arm"

JSON_PATH = os.path.join("lists", "list_hb.json")
TAG_MARKER = "#оновлення_софту"

# Твій розклад (можна редагувати)
SCHEDULED_TIMES = ["12:00", "15:00", "18:00", "19:30", "21:00"]

# АКТИВУЄМО MIDDLEWARE ПЕРЕД ІНІЦІАЛІЗАЦІЄЮ
apihelper.ENABLE_MIDDLEWARE = True
bot = telebot.TeleBot(BOT_TOKEN)

# --- MIDDLEWARE ТА ДОПОМІЖНІ ФУНКЦІЇ ---

@bot.middleware_handler(update_types=['message'])
def log_incoming_messages(bot_instance, message):
    """Логує команди в консоль"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📥 Команда від {message.from_user.id}: {message.text}")

def get_json_count():
    try:
        if os.path.exists(JSON_PATH):
            with open(JSON_PATH, 'r', encoding='utf-8') as f:
                return len(json.load(f))
    except: pass
    return 0

def apply_3ds_context(text):
    if not text: return ""
    
    # Словник замін: Ключ (що шукаємо) -> Значення (на що замінюємо)
    replacements = {
        # Базові теги та виправлення перекладача
        r"3дс": "<b>3DS</b>",
        r"3ds": "<b>3DS</b>",
        r"Nintendo 3DS": "Nintendo <b>3DS</b>",
        r"хоумбрю": "Homebrew",
        r"ЦРУ": "FBI (cia)",
        r"ФБР": "FBI (cia)",
        
        # Технічні терміни 3DS (щоб перекладач їх не чіпав)
        r"прошивка": "Custom Firmware (CFW)",
        r"сутінки": "TWiLight Menu++",  # Перекладач часто перекладає назву меню
        r"перемикач": "Switch",        # Для мультиплатформенних релізів
        r"вприскування": "Injection",  # Для VC (Virtual Console) ін'єкцій
        r"ядро": "Kernel",
        r"сховище": "Repository",
        
        # Файлові системи та шляхи
        r"корінь sd": "SD Root",
        r"завантажувач": "Bootloader",
        r"патч": "Patch",
        
        # Специфічне для хабів
        r"нічний": "Nightly",          # Для нічних збірок
        r"стабільний": "Stable"
    }
    
    for pattern, replacement in replacements.items():
        # flags=re.IGNORECASE дозволяє знаходити і "3дс", і "3ДС"
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
    return text

def format_changelog(text):
    if not text or "Опис відсутній" in text: 
        return "<i>(Опис оновлення відсутній)</i>"
    
    # 0. ВІДСІКАННЯ ТЕХНІЧНОГО СМІТТЯ (щоб не було списку ніків розробників)
    text = text.split("Merged PRs")[0].split("Full Changelog")[0].strip()
    
    # 1. Базова очистка
    text = text.replace("\r", "").strip()
    
    # 2. СКЛЕЮВАННЯ РОЗІРВАНИХ РЕЧЕНЬ (Regex)
    # Якщо рядок починається з маленької літери — це продовження попереднього речення
    text = re.sub(r'\n([a-zа-яієґ])', r' \1', text)
    
    lines = text.splitlines()
    formatted_lines = []
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # 3. ОБРОБКА ДУЖЕ КОРОТКИХ РЯДКІВ (< 3 символи)
        if len(line) < 3 and formatted_lines:
            formatted_lines[-1] = f"{formatted_lines[-1]} {line}"
            continue

        # 4. ВИЗНАЧЕННЯ ЗАГОЛОВКІВ (Жирний шрифт)
        if line.endswith(':') or line.endswith('?') or line.startswith('==='):
            # Додаємо порожній рядок перед заголовком для візуального розділення
            formatted_lines.append(f"\n<b>{line}</b>")
        
        # 5. ФОРМУВАННЯ СПИСКУ
        else:
            # Прибираємо існуючі маркери (*, -, +)
            clean_line = re.sub(r'^[*\-+] +', '', line)
            
            # Перевіряємо, чи це вкладений пункт
            if line.startswith('  ') or line.startswith(' *') or line.startswith(' -'):
                formatted_lines.append(f"    ◦ {clean_line}")
            else:
                formatted_lines.append(f"  • {clean_line}")
    
    # 6. ЗБИРАЄМО ТЕКСТ
    final_text = "\n".join(formatted_lines).strip()
    
    # 7. ЛІМІТ 3000 СИМВОЛІВ + ПРИПИСКА
    if len(final_text) > 3000:
        return final_text[:3000] + "...\n\n<b>Детальніше за посиланням нижче 👇</b>"
    
    return final_text

# --- ОСНОВНА ЛОГІКА ---

def get_github_release_notes(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            release_body = soup.find('div', class_='markdown-body')
            if release_body:
                return release_body.get_text(separator='\n').strip()
    except: pass
    return ""

def translate_and_format(raw_text):
    if not raw_text or TAG_MARKER not in raw_text: return ""
    lines = raw_text.split('\n')
    final_output = []
    
    for line in lines:
        if "https://github.com" in line:
            url_match = re.search(r'https://github\.com/[^\s|]+', line)
            if url_match:
                url = url_match.group(0)
                notes = get_github_release_notes(url)
                if notes:
                    try:
                        # АВТО-ВИЗНАЧЕННЯ МОВИ (для японської тощо)
                        translated = GoogleTranslator(source='auto', target='uk').translate(notes)
                        final_notes = format_changelog(apply_3ds_context(translated))
                    except Exception as e:
                        print(f"Помилка перекладу: {e}")
                        final_notes = f"<i>(Не встиг перекласти, оригінал: {notes[:40]}...)</i>"
                else:
                    final_notes = "<i>(Опис релізу порожній)</i>"
                final_output.append(f"<b>{line}</b>\n\n<b>📝 Що нового:</b>\n{final_notes}\n────────────────────")
        elif "===" in line or "#" in line:
            final_output.append(f"<b>{line}</b>")
            
    return '\n'.join(final_output)

def sync_database():
    DB_URL = "https://db.universal-team.net/data/full.json"
    now_str = datetime.now().strftime('%H:%M:%S')
    print(f"[{now_str}] Перевірка бази Universal-DB...")
    
    try:
        # Встановлюємо таймаут 15 секунд, щоб скрипт не "зависав" при поганому інеті
        res = requests.get(DB_URL, timeout=15)
        
        if res.status_code != 200:
            print(f"Помилка сервера: статус {res.status_code}")
            return False # Повертаємо невдачу
            
        remote_data = res.json()
        
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            local_list = json.load(f)
        
        existing = {item['api_url'].lower() for item in local_list if 'api_url' in item}
        new_count = 0
        
        for app in remote_data:
            if "3DS" not in app.get("systems", []): continue
            path = app.get("github", "")
            if not path: continue
            api_url = f"https://api.github.com/repos/{path}"
            
            if api_url.lower() not in existing:
                try:
                    # Використовуємо перекладач для опису
                    desc_raw = app.get('description', '')
                    desc = GoogleTranslator(source='auto', target='uk').translate(desc_raw)
                except: 
                    desc = app.get('description', '')
                
                local_list.append({
                    "category": "3DS", 
                    "app_name": app.get('title', path),
                    "api_url": api_url, 
                    "html_url": f"https://github.com/{path}/releases/",
                    "comm_date": "2000-01-01T00:00:00Z", 
                    "tag_name": "v0.0.0",
                    "description": desc, 
                    "prefix": ""
                })
                new_count += 1
        
        if new_count > 0:
            with open(JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump(local_list, f, indent=2, ensure_ascii=False)
            print(f"Додано {new_count} нових програм у JSON.")
        else:
            print(f"Нових додатків у базі Universal-DB не знайдено.")
        
        return True # Успішно завершено, можна запускати hbnews

    # Обробка помилок мережі
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.RequestException):
        now_err = datetime.now().strftime('%d.%m %H:%M:%S')
        print(f"[{now_err}] Помилка з'єднання: Мережа недоступна. Сон 30 хвилин...")
        time.sleep(1800) 
        return False

    except Exception as e: 
        print(f"Критична помилка синхронізації: {e}")
        return False

    # Обробка помилок мережі (відсутність інтернету, збій DNS)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.RequestException):
        now_err = datetime.now().strftime('%d.%m %H:%M:%S')
        print(f"[{now_err}] Помилка з'єднання: Мережа недоступна.")
        print(f"[{now_err}] Призупиняємо цикл: сон 30 хвилин...")
        
        # Зупиняємо весь потік на 30 хвилин
        time.sleep(1800)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Спроба відновити роботу...")

    # Обробка всіх інших непередбачуваних помилок
    except Exception as e: 
        print(f"Критична помилка синхронізації: {e}")

def send_to_telegram(text):
    if not text: return
    MAX_LENGTH = 3700
    if len(text) <= MAX_LENGTH:
        bot.send_message(CHAT_ID, text, message_thread_id=THREAD_ID, parse_mode="HTML", disable_web_page_preview=True)
    else:
        parts = text.split("────────────────────")
        current_msg = ""
        for p in parts:
            if len(current_msg) + len(p) < MAX_LENGTH:
                current_msg += p + "────────────────────\n"
            else:
                bot.send_message(CHAT_ID, current_msg, message_thread_id=THREAD_ID, parse_mode="HTML", disable_web_page_preview=True)
                current_msg = p + "────────────────────\n"
                time.sleep(1)
        if current_msg:
            bot.send_message(CHAT_ID, current_msg, message_thread_id=THREAD_ID, parse_mode="HTML", disable_web_page_preview=True)

def run_updater():
    try:
        result = subprocess.run([EXE_PATH], capture_output=True, text=True, encoding='utf-8')
        if TAG_MARKER in result.stdout:
            parts = result.stdout.split(TAG_MARKER)
            return translate_and_format(TAG_MARKER + parts[1])
    except Exception as e: 
        print(f"EXE Error: {e}")
    return ""

def sync_with_git():
    try:
        if not os.path.isdir(".git"): return
        subprocess.run(["git", "add", "lists/", "history/"], check=True)
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            msg = f"Auto-update: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            subprocess.run(["git", "commit", "-m", msg], check=True)
            subprocess.run(["git", "push"], check=True)
            print("✅ Дані синхронізовано з GitHub")
    except Exception as e:
        print(f"⚠️ Git error: {e}")

def job():
    now_str = datetime.now().strftime('%H:%M:%S')
    print(f"\n[ПОЧАТОК ЦИКЛУ] {now_str}")
    
    try:
        # 1. Спроба синхронізації бази
        # Якщо там станеться помилка мережі, функція засне і поверне False
        if not sync_database():
            print(f"[ЗУПИНКА] Цикл перервано. Почнемо знову за розкладом.")
            return # ВИХІД: далі код не піде, поки не запуститься новий job
        
        # 2. Пошук оновлень (виконується тільки якщо sync_database пройшла успішно)
        now_upd = datetime.now().strftime('%H:%M:%S')
        print(f"[{now_upd}] Пошук оновлень через hbnews...")
        
        content = run_updater()
        
        if not content:
            # 3. Повідомлення адміну, якщо нічого не знайдено
            print(f"Оновлень не знайдено.")
            try:
                # Додав перевірку інета і тут, щоб не "срало", якщо інет зник після sync_database
                bot.send_message(ADMIN_ID, f"Моніторинг: оновлень не знайдено.\n{datetime.now().strftime('%H:%M:%S')}")
            except:
                pass
        else:
            # 4. Відправка результату в канал (з нашою новою логікою розбиття)
            send_to_telegram(content)
            
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        # Додатковий захист, якщо інет зник саме під час run_updater
        now_err = datetime.now().strftime('%d.%m %H:%M:%S')
        print(f"[{now_err}] Помилка з'єднання під час виконання циклу.")
        print(f"[{now_err}] Режим очікування: сон 30 хвилини...") # Твій тестовий час
        time.sleep(1800) 
    except Exception as e:
        # Для будь-яких інших критичних помилок
        print(f"Помилка в job(): {e}")

    print(f"[КІНЕЦЬ ЦИКЛУ] Очікування...")

    sync_with_git()

def send_to_telegram(text):
    if not text: return
    MAX_LENGTH = 3700
    try:
        if len(text) <= MAX_LENGTH:
            bot.send_message(CHAT_ID, text, message_thread_id=THREAD_ID, parse_mode="HTML", disable_web_page_preview=True)
            print(f"Надіслано одним повідомленням ({len(text)} симв.)")
        else:
            parts = text.split("────────────────────")
            current_msg = ""
            count = 0
            for p in parts:
                if len(current_msg) + len(p) < MAX_LENGTH:
                    current_msg += p + "────────────────────\n"
                else:
                    bot.send_message(CHAT_ID, current_msg, message_thread_id=THREAD_ID, parse_mode="HTML", disable_web_page_preview=True)
                    current_msg = p + "────────────────────\n"
                    count += 1
                    time.sleep(1)
            if current_msg:
                bot.send_message(CHAT_ID, current_msg, message_thread_id=THREAD_ID, parse_mode="HTML", disable_web_page_preview=True)
                count += 1
            print(f"Надіслано частинами ({count} повідомл.)")
    except Exception as e:
        print(f"Помилка ТГ: {e}")

# --- КОМАНДИ БОТА ---

@bot.message_handler(commands=['status'])
def cmd_status(m):
    """Розширений статус роботи скрипта"""
    if m.from_user.id != ADMIN_ID: return
    
    now = datetime.now()
    up_time = now - start_time
    next_run = schedule.next_run()
    
    # Розрахунок часу до наступного запуску
    time_to_next = "не заплановано"
    if next_run:
        diff = next_run - now
        h, r = divmod(int(diff.total_seconds()), 3600)
        m_left, s_left = divmod(r, 60)
        time_to_next = f"{h:02d}:{m_left:02d}:{s_left:02d} (о {next_run.strftime('%H:%M')})"

    status_text = (
        "<b>✅ Скрипт активний</b>\n\n"
        f"⏱ <b>Час роботи:</b> {str(up_time).split('.')[0]}\n"
        f"📅 <b>Наступний запуск:</b> {time_to_next}\n"
        f"📊 <b>База:</b> {get_json_count()} програм\n"
        f"🕒 <b>Час сервера:</b> {now.strftime('%H:%M:%S')}"
    )
    
    bot.reply_to(m, status_text, parse_mode="HTML")

@bot.message_handler(commands=['getdb'])
def cmd_get_db(m):
    """Надсилає файл бази даних адміну"""
    if m.from_user.id != ADMIN_ID: return
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, 'rb') as doc:
                bot.send_document(m.chat.id, doc, caption=f"📦 Актуальна база від {datetime.now().strftime('%d.%m %H:%M')}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 📤 База надіслана адміну.")
        except Exception as e:
            bot.reply_to(m, f"❌ Помилка при надсиланні файлу: {e}")
    else:
        bot.reply_to(m, "❌ Файл бази не знайдено.")

@bot.message_handler(commands=['add'])
def cmd_add(m):
    if m.from_user.id != ADMIN_ID: return
    try:
        parts = m.text.replace('/add ', '').split('|')
        if len(parts) < 4:
            bot.reply_to(m, "Формат: `/add Категорія | Назва | user/repo | Опис`", parse_mode="Markdown")
            return
        cat, name, repo, desc = [p.strip() for p in parts]
        api_url = f"https://api.github.com/repos/{repo}"
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Оновлення або додавання
        found = False
        for item in data:
            if item.get('api_url', '').lower() == api_url.lower():
                item.update({"category": cat, "app_name": name, "description": desc, "html_url": f"https://github.com/{repo}/releases/"})
                found = True; break
        if not found:
            data.append({"category": cat, "app_name": name, "api_url": api_url, "html_url": f"https://github.com/{repo}/releases/", 
                         "comm_date": "2000-01-01T00:00:00Z", "tag_name": "v0.0.0", "description": desc, "prefix": ""})
        
        with open(JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        bot.reply_to(m, f"✅ {'Оновлено' if found else 'Додано'}: {name}")
    except Exception as e: bot.reply_to(m, f"❌ Помилка: {e}")

# --- ЗАПУСК ---

def run_bot():
    """Запуск бота з режимом 'тихої' помилки та сном на 30 хв"""
    while True:
        try:
            # Чистий старт без зайвого сміття
            bot.polling(none_stop=True, interval=0, timeout=90)
        except Exception:
            # Ми не виводимо 'e' (весь текст помилки), а пишемо коротке повідомлення
            now_err = datetime.now().strftime('%d.%m %H:%M:%S')
            print(f"[{now_err}] Помилка з'єднання з ТГ (сервер недоступний або впав інет).")
            print(f"[{now_err}] Призупиняємо дію: запуск режиму сну на 30 хвилин...")
            
            try:
                bot.stop_polling()
            except:
                pass
                
            # Спимо 30 хвилин, щоб не засирати логи та не їсти пам'ять
            time.sleep(1800)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Спроба відновити роботу...")

if __name__ == "__main__":
    print("=== Система запущена (Режим стабільності: ON) ===")
    
    # 1. Запуск бота у фоновому потоці
    threading.Thread(target=run_bot, daemon=True).start()
    
    # 2. Повідомлення про старт
    try:
        bot.send_message(ADMIN_ID, "🚀 <b>Система моніторингу запущена!</b>\nЛогування: 10 хв. Захист від збоїв: 30 хв.", parse_mode="HTML")
    except:
        print("Повідомлення про запуск не надіслано (немає зв'язку з ТГ).")
    
    # 3. Реєстрація завдань
    for t in SCHEDULED_TIMES:
        schedule.every().day.at(t).do(job)

    last_log = 0
    while True:
        try:
            schedule.run_pending()
        except Exception:
            # Навіть якщо впаде розклад — просто ігноруємо, щоб не було паніки в логах
            pass

        next_run = schedule.next_run()
        if next_run:
            diff = (next_run - datetime.now()).total_seconds()
            
            # Логування в консоль РАЗ НА 30 ХВИЛИН (600 сек) або за хвилину до запуску
            if time.time() - last_log > 1800 or diff < 60:
                h, r = divmod(int(max(0, diff)), 3600)
                m_left, s_left = divmod(r, 60)
                print(f"Очікування... Наступний запуск о {next_run.strftime('%H:%M')} (через {h:02d}:{m_left:02d}:{s_left:02d})")
                last_log = time.time()
            
            time.sleep(min(diff, 30) if diff > 1 else 0.5)
        else:
            time.sleep(60)