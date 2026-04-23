import os
import httpx
import logging
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import BadRequest, Conflict

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
TELEMT_API = os.environ.get("TELEMT_API_URL", "http://localhost:9091")
API_TOKEN = os.environ.get("API_TOKEN", "")

HEADERS = {"Authorization": API_TOKEN} if API_TOKEN else {}

def only_owner(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER_ID:
            await update.effective_message.reply_text("⛔ Нет доступа")
            return
        return await func(update, ctx)
    return wrapper

async def api_get(path: str):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{TELEMT_API}{path}", headers=HEADERS)
        r.raise_for_status()
        return r.json()

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🌐 Активные IP", callback_data="active_ips")],
        [InlineKeyboardButton("❤️ Здоровье", callback_data="health")],
    ])

@only_owner
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔒 *MTProxy Monitor*\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await query.answer()

    try:
        if query.data == "stats":
            resp = await api_get("/v1/stats/minimal/all")
            d = resp.get("data", {})
            
            # Пробуем разные варианты структуры ответа
            conns = d.get("connections", {})
            if not conns and isinstance(d, dict):
                # Если connections нет, ищем поля напрямую в data
                conns = d
            
            traffic = d.get("traffic", {})
            if not traffic and isinstance(d, dict):
                traffic = d
            
            # Форматируем трафик
            def format_bytes(bytes_val):
                if bytes_val is None or bytes_val == '?' or bytes_val == '':
                    return '?'
                try:
                    bytes_val = int(float(bytes_val))
                    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                        if bytes_val < 1024:
                            return f"{bytes_val:.1f} {unit}"
                        bytes_val /= 1024
                    return f"{bytes_val:.1f} PB"
                except (ValueError, TypeError):
                    return str(bytes_val)
            
            # Получаем значения с резервными вариантами
            current = conns.get('current') or conns.get('active') or conns.get('active_connections') or conns.get('current_connections') or '?'
            total = conns.get('total') or conns.get('total_connections') or conns.get('connections_total') or '?'
            users_online = conns.get('users_online') or conns.get('online_users') or conns.get('users') or current
            
            bytes_in = traffic.get('bytes_in') or traffic.get('received') or traffic.get('traffic_in') or traffic.get('bytes_received') or '?'
            bytes_out = traffic.get('bytes_out') or traffic.get('sent') or traffic.get('traffic_out') or traffic.get('bytes_sent') or '?'
            bytes_total = traffic.get('bytes_total') or traffic.get('total') or traffic.get('total_traffic') or '?'
            
            # Если bytes_total нет, считаем сами
            if bytes_total == '?' and bytes_in != '?' and bytes_out != '?':
                try:
                    bytes_total = int(float(bytes_in)) + int(float(bytes_out))
                except:
                    pass
            
            text = (
                "📊 *Статистика сервера*\n\n"
                f"⚡ Активных сейчас: `{current}`\n"
                f"📈 Всего подключений: `{total}`\n"
                f"👥 Юзеров онлайн: `{users_online}`\n\n"
                f"📥 Получено: `{format_bytes(bytes_in)}`\n"
                f"📤 Отправлено: `{format_bytes(bytes_out)}`\n"
                f"💾 Всего трафика: `{format_bytes(bytes_total)}`\n"
                f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
            )

        elif query.data == "active_ips":
            resp = await api_get("/v1/stats/users/active-ips")
            # Обрабатываем разные форматы ответа
            users = []
            if isinstance(resp, dict):
                users = resp.get("data", []) or resp.get("users", []) or resp.get("ips", [])
            elif isinstance(resp, list):
                users = resp
            
            if not users:
                text = "🌐 *Активные IP*\n\nНет активных подключений"
            else:
                lines = ["🌐 *Активные IP*\n"]
                total_ips = 0
                
                # Если ответ плоский список IP
                if users and isinstance(users[0], str):
                    total_ips = len(users)
                    display_count = min(len(users), 15)
                    for ip in users[:display_count]:
                        lines.append(f"  • `{ip}`")
                    if len(users) > 15:
                        lines.append(f"  ... и ещё {len(users) - 15}")
                else:
                    # Если ответ список объектов пользователей
                    for u in users:
                        if isinstance(u, dict):
                            name = u.get("username", u.get("user", u.get("name", "?")))
                            ips = u.get("ips", u.get("ip", u.get("addresses", [])))
                            if isinstance(ips, str):
                                ips = [ips]
                            if ips:
                                total_ips += len(ips)
                                lines.append(f"👤 `{name}` — {len(ips)} устр.:")
                                # Показываем до 15 IP на пользователя
                                display_count = min(len(ips), 15)
                                for ip in ips[:display_count]:
                                    ip_addr = ip if isinstance(ip, str) else ip.get("ip", ip.get("address", "?"))
                                    lines.append(f"  • `{ip_addr}`")
                                if len(ips) > 15:
                                    lines.append(f"  ... и ещё {len(ips) - 15}")
                        elif isinstance(u, str):
                            total_ips += 1
                            if total_ips <= 15:
                                lines.append(f"  • `{u}`")
                
                if total_ips > 0:
                    lines.insert(1, f"_Всего активных IP: {total_ips}_\n")
                text = "\n".join(lines)

        elif query.data == "health":
            resp = await api_get("/v1/health")
            d = resp.get("data", {}) if isinstance(resp, dict) else resp
            if not d:
                d = resp
            
            status = d.get("status", d.get("state", "?"))
            emoji = "✅" if status in ["ok", "healthy", "up", True] else "❌"
            
            # Добавляем дополнительную информацию о здоровье если доступна
            extra_info = []
            uptime = d.get("uptime", d.get("up_time"))
            if uptime:
                extra_info.append(f"⏱ Аптайм: `{uptime}`")
            version = d.get("version", d.get("ver"))
            if version:
                extra_info.append(f"📦 Версия: `{version}`")
            
            extra_text = "\n".join(extra_info) + "\n" if extra_info else ""
            
            text = (
                f"❤️ *Здоровье сервера*\n\n"
                f"{emoji} Статус: `{status}`\n"
                f"{extra_text}"
                f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
            )
        else:
            text = "Неизвестная команда"

    except Exception as e:
        text = f"❌ Ошибка запроса к API:\n`{e}`"
        logger.error(f"API error: {e}", exc_info=True)

    try:
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.debug("Message content unchanged, skipping edit")
        else:
            logger.error(f"BadRequest: {e}")
    except Conflict as e:
        logger.warning(f"Conflict error (another instance running?): {e}")
    except Exception as e:
        logger.error(f"Error editing message: {e}", exc_info=True)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Добавляем обработчик ошибок
    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if isinstance(context.error, Conflict):
            logger.critical("Бот остановлен: запущен другой инстанс этого бота! Проверьте Railway.")
        else:
            logger.error(f"Update {update} caused error: {context.error}", exc_info=context.error)
    
    app.add_error_handler(error_handler)
    
    print("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
