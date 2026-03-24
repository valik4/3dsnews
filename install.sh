#!/bin/bash

# Кольори для красивого виводу
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}--- Початок встановлення 3DS News Bot ---${NC}"

# 1. Оновлення системи та встановлення системних залежностей
echo -e "${GREEN}[1/4] Встановлення Python, Go та Git...${NC}"
sudo apt update
sudo apt install -y python3-venv golang-go git

# 2. Налаштування Python віртуального середовища
echo -e "${GREEN}[2/4] Налаштування Python середовища...${NC}"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Компіляція Go-модуля під архітектуру Raspberry Pi
echo -e "${GREEN}[3/4] Компіляція Go-модуля (hbnews_arm)...${NC}"
# Компілюємо з підтримкою ARM (стандарт для Raspberry Pi)
go build -o hbnews_arm main.go homebrew_update.go
chmod +x hbnews_arm

# 4. Створення папок, якщо їх немає
mkdir -p lists history

echo -e "${BLUE}--- Встановлення завершено успішно! ---${NC}"
echo -e "Для запуску вручну: ${GREEN}source venv/bin/activate && python3 send_news.py${NC}"