# Rassylka bot

Бот рассылок по группам (aiogram 3).

## Команды (в админской группе)
- `/new` — ответом на сообщение: создать рассылку (есть «✅ Выбрать все / ⬜ Снять все»)
- `/list` — список рассылок, у каждой: выбрать/убрать группы, интервал, переименовать, удалить
- `/groups` — группы: список по страницам, проверка, переименование, удаление, удаление всех нерабочих, добавление по ID

## Установка
```bash
git clone https://github.com/dalmatinec/rassylka ~/rassylka
cd ~/rassylka
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env          # токен, админы, группа, туннель
cp rassylka.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now rassylka
```

## Управление
```bash
systemctl restart rassylka      # перезапуск
systemctl status rassylka       # статус
journalctl -u rassylka -f       # логи вживую
cd ~/rassylka && git pull && systemctl restart rassylka   # обновить код
```
