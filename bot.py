#!/usr/bin/env python3
import os
import logging
import asyncio
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
import httpx

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
API_URL = os.getenv("TELEMT_API_URL", "http://gaerweat.railway.internal:9091")

if not TOKEN:
    logger.error("BOT_TOKEN not found! Проверьте переменные окружения на Railway.")
    exit(1)

# --- Функции получения данных ---

async def get_stats():
    """Получает статистику с сервера telemt"""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # Пытаемся получить общую статистику
            resp = await client.get(f"{API_URL}/stats/minimal")
            if resp.status_code == 200:
                data = resp.json()
                logger.info(f"Raw stats data: {data}")
                
                # Обработка структуры: {'ok': True, 'data': {...}}
                if isinstance(data, dict) and data.get('ok'):
                    data = data.get('data', data)
                
                # Пытаемся извлечь данные из разных возможных форматов
                active = 0
                total_conn = 0
                users_online = 0
                recv_bytes = 0
                sent_bytes = 0
                
                if isinstance(data, dict):
                    # Прямые поля
                    active = data.get('active_connections') or data.get('active') or data.get('current_connections') or data.get('active_now')
                    total_conn = data.get('total_connections') or data.get('total') or data.get('connections_total')
                    users_online = data.get('users_online') or data.get('unique_users') or data.get('active_users')
                    recv_bytes = data.get('bytes_received') or data.get('traffic_in') or data.get('received') or data.get('rx_bytes')
                    sent_bytes = data.get('bytes_sent') or data.get('traffic_out') or data.get('sent') or data.get('tx_bytes')
                    
                    # Если данные вложены в подсловарь 'data' (структура telemt)
                    if active is None and 'data' in data:
                        sub = data['data']
                        if isinstance(sub, dict):
                            active = sub.get('active_connections') or sub.get('active') or sub.get('current_connections')
                            total_conn = sub.get('total_connections') or sub.get('total')
                            users_online = sub.get('users_online') or sub.get('unique_users')
                            recv_bytes = sub.get('bytes_received') or sub.get('traffic_in') or sub.get('received')
                            sent_bytes = sub.get('bytes_sent') or sub.get('traffic_out') or sub.get('sent')
                    
                    # Если данные вложены в другие ключи
                    if active is None:
                        for key in ['stats', 'result', 'payload']:
                            if key in data and isinstance(data[key], dict):
                                sub = data[key]
                                active = sub.get('active_connections') or sub.get('active') or sub.get('current_connections')
                                total_conn = sub.get('total_connections') or sub.get('total')
                                users_online = sub.get('users_online') or sub.get('unique_users')
                                recv_bytes = sub.get('bytes_received') or sub.get('traffic_in') or sub.get('received')
                                sent_bytes = sub.get('bytes_sent') or sub.get('traffic_out') or sub.get('sent')
                                break
                
                # Конвертация трафика в человекочитаемый формат
                def format_traffic(bytes_val):
                    try:
                        b = int(bytes_val) if bytes_val is not None else 0
                        if b > 1024**3: return f"{b / (1024**3):.2f} GB"
                        if b > 1024**2: return f"{b / (1024**2):.2f} MB"
                        if b > 1024: return f"{b / 1024:.2f} KB"
                        return f"{b} B"
                    except: return "0 B"

                return {
                    'active': int(active) if active is not None else 0,
                    'total': int(total_conn) if total_conn is not None else 0,
                    'users': int(users_online) if users_online is not None else 0,
                    'recv': format_traffic(recv_bytes),
                    'sent': format_traffic(sent_bytes),
                    'total_traffic': format_traffic((int(recv_bytes) if recv_bytes else 0) + (int(sent_bytes) if sent_bytes else 0))
                }
            else:
                logger.warning(f"Stats API error: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"Error fetching stats: {e}")
        
        # Заглушка, если ничего не получилось
        return {'active': 0, 'total': 0, 'users': 0, 'recv': '0 B', 'sent': '0 B', 'total_traffic': '0 B'}

async def get_active_ips(limit=15):
    """Получает список активных IP"""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(f"{API_URL}/stats/users")
            if resp.status_code == 200:
                data = resp.json()
                logger.info(f"Raw IPs data: {data}")
                
                ips = []
                # Обработка структуры: {'ok': True, 'data': [...]}
                if isinstance(data, dict) and data.get('ok'):
                    data = data.get('data', data)
                
                # Обработка разных форматов ответа
                if isinstance(data, list):
                    ips = data
                elif isinstance(data, dict):
                    # Ищем список в常见 ключах
                    for key in ['ips', 'addresses', 'users', 'data', 'active_ips', 'clients', 'peers']:
                        if key in data:
                            val = data[key]
                            if isinstance(val, list):
                                ips = val
                                break
                            elif isinstance(val, dict):
                                # Если значения словаря - это IP или содержат IP
                                ips = list(val.keys())
                                break
                    # Если сам словарь содержит IP как ключи
                    if not ips:
                        ips = list(data.keys())
                
                # Фильтрация и ограничение
                valid_ips = [str(ip) for ip in ips if ip and str(ip).strip()]
                return valid_ips[:limit]
        except Exception as e:
            logger.error(f"Error fetching IPs: {e}")
    return []

# --- Обработчики команд ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🌐 Активные IP", callback_data="ips")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Привет! Я бот для мониторинга MTProxy.\nВыберите действие:",
        reply_markup=reply_markup
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    now = datetime.now(timezone.utc).strftime('%H:%M:%S UTC')
    
    if query.data == "stats":
        stats = await get_stats()
        text = (
            f"📊 *Статистика сервера*\n\n"
            f"⚡️ Активных сейчас: `{stats['active']}`\n"
            f"📈 Всего подключений: `{stats['total']}`\n"
            f"👥 Юзеров онлайн: `{stats['users']}`\n\n"
            f"📥 Получено: `{stats['recv']}`\n"
            f"📤 Отправлено: `{stats['sent']}`\n"
            f"💾 Всего трафика: `{stats['total_traffic']}`\n\n"
            f"🕐 {now}"
        )
        keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="stats")]]
        
    elif query.data == "ips":
        ips = await get_active_ips(15)
        if not ips:
            text = f"🌐 *Активные IP*\n\nНет активных подключений прямо сейчас.\n\n🕐 {now}"
        else:
            ip_list = "\n".join([f"• {ip}" for ip in ips])
            if len(ips) == 15:
                ip_list += "\n_... и еще_"
            text = f"🌐 *Активные IP (до 15)*\n\n{ip_list}\n\n🕐 {now}"
        keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="ips")]]
    
    else:
        return

    try:
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        err_str = str(e)
        if "not modified" in err_str.lower():
            pass # Игнорируем ошибку, если контент не изменился
        else:
            logger.error(f"Edit message error: {e}")
            # Фоллбэк: отправляем новое сообщение, если редактирование не удалось
            try:
                await query.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            except:
                pass

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    logger.info("Бот запущен...")
    # drop_pending_updates=True ensures that if another instance was running,
    # it gets terminated and pending updates are cleared to avoid conflicts
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()
