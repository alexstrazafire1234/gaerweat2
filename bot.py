import asyncio
import os
import httpx
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Конфиг из env
BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
TELEMT_API = os.environ.get("TELEMT_API_URL", "http://localhost:9091")
API_TOKEN = os.environ.get("TELEMT_API_TOKEN", "")

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
        [InlineKeyboardButton("👤 По юзерам", callback_data="users")],
        [InlineKeyboardButton("❤️ Здоровье", callback_data="health")],
    ])

@only_owner
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔒 *MTProxy Monitor*\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

@only_owner
async def menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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
    data = query.data

    try:
        if data == "stats":
            resp = await api_get("/v1/stats/runtime")
            d = resp.get("data", {})
            conns = d.get("connections", {})
            text = (
                "📊 *Статистика*\n\n"
                f"🔗 Всего подключений: `{conns.get('total', '?')}`\n"
                f"⚡ Активных сейчас: `{conns.get('current', '?')}`\n"
                f"👥 Юзеров онлайн: `{conns.get('users_online', '?')}`\n"
                f"\n🕐 {datetime.utcnow().strftime('%H:%M:%S UTC')}"
            )

        elif data == "active_ips":
            resp = await api_get("/v1/stats/users/active-ips")
            users = resp.get("data", [])
            if not users:
                text = "🌐 *Активные IP*\n\nНет активных подключений"
            else:
                lines = ["🌐 *Активные IP*\n"]
                for u in users:
                    name = u.get("username", "?")
                    ips = u.get("ips", [])
                    lines.append(f"👤 `{name}` — {len(ips)} IP:")
                    for ip in ips:
                        lines.append(f"  • `{ip}`")
                text = "\n".join(lines)

        elif data == "users":
            resp = await api_get("/v1/stats/runtime")
            d = resp.get("data", {})
            top = d.get("top", {})
            by_conns = top.get("by_connections", [])
            by_bytes = top.get("by_octets", [])

            lines = ["👤 *По юзерам*\n"]
            lines.append("*По подключениям:*")
            for u in by_conns:
                name = u.get("username", "?")
                cur = u.get("current_connections", 0)
                lines.append(f"  `{name}`: {cur} подкл.")

            lines.append("\n*По трафику:*")
            for u in by_bytes:
                name = u.get("username", "?")
                octets = u.get("cumulative_octets", 0)
                mb = octets / 1024 / 1024
                lines.append(f"  `{name}`: {mb:.1f} MB")
            text = "\n".join(lines) if len(lines) > 2 else "👤 Нет данных"

        elif data == "health":
            resp = await api_get("/v1/health")
            d = resp.get("data", {})
            status = d.get("status", "?")
            emoji = "✅" if status == "ok" else "❌"
            text = (
                f"❤️ *Здоровье сервера*\n\n"
                f"{emoji} Статус: `{status}`\n"
                f"📝 Readonly: `{d.get('read_only', '?')}`\n"
                f"\n🕐 {datetime.utcnow().strftime('%H:%M:%S UTC')}"
            )
        else:
            text = "Неизвестная команда"

    except Exception as e:
        text = f"❌ Ошибка запроса к API:\n`{e}`"

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
