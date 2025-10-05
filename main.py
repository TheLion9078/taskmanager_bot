import json
import os
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# === CONFIGURATION ===
BOT_TOKEN = "8476888943:AAGwK6mz9MRHtKqVkO5z0Yelpyxm1bi9_GU"
CHAT_ID = "6033369627"
TASK_FILE = "tasks.json"

# === UTILITIES ===
def load_tasks():
    if os.path.exists(TASK_FILE):
        with open(TASK_FILE, "r") as f:
            return json.load(f)
    return {"pending": [], "done": []}

def save_tasks(tasks):
    with open(TASK_FILE, "w") as f:
        json.dump(tasks, f, indent=4)

# === REMINDERS ===
async def send_reminder(task):
    message = f"⏰ Reminder: {task['name']}"
    if task.get("time"):
        message += f" — {task['time']}"
    if task.get("repeat"):
        message += f" (repeats: {task['repeat']})"
    await bot_instance.send_message(chat_id=CHAT_ID, text=message)

# === SCHEDULER ===
scheduler = AsyncIOScheduler(timezone="US/Eastern")

def schedule_task(task):
    if not task.get("time"):  # no time set, skip scheduling
        return

    hour, minute = map(int, task["time"].split(":"))

    if task.get("repeat") == "daily":
        scheduler.add_job(
            send_reminder, "cron",
            args=[task], hour=hour, minute=minute,
            id=task["name"], replace_existing=True
        )
    elif task.get("repeat") in [
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
    ]:
        scheduler.add_job(
            send_reminder, "cron",
            args=[task], hour=hour, minute=minute,
            day_of_week=task["repeat"],
            id=task["name"], replace_existing=True
        )
    else:
        scheduler.add_job(
            send_reminder, "cron",
            args=[task], hour=hour, minute=minute,
            id=task["name"], replace_existing=True
        )

def reschedule_all():
    scheduler.remove_all_jobs()
    tasks = load_tasks()
    now = datetime.now()
    missed = []

    for task in tasks["pending"]:
        if not task.get("time"):
            continue

        try:
            task_time = datetime.strptime(task["time"], "%H:%M").replace(
                year=now.year, month=now.month, day=now.day
            )
        except ValueError:
            continue

        if task_time < now and not task.get("repeat"):
            missed.append(task)
        else:
            schedule_task(task)

    return missed

# === TELEGRAM COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Assalamu Alaikum!\nI’m your Task Reminder Bot.\n\nCommands:\n"
        "/add <task> [time] [repeat]\n"
        "/list — show tasks\n"
        "/done <task name> — mark as done\n"
        "/history — show completed tasks\n"
        "/remove <task name> — delete permanently\n"
        "/clear — remove ALL tasks\n"
        "/next — show next reminder"
    )

async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /add <task> [time] [repeat]")
        return

    name_parts = []
    time_str, repeat = None, None

    for arg in context.args:
        if ":" in arg:
            time_str = arg
        elif arg.lower() in [
            "daily", "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday"
        ]:
            repeat = arg.lower()
        else:
            name_parts.append(arg)

    name = " ".join(name_parts)

    if not name:
        await update.message.reply_text("⚠️ Please provide a task name.")
        return

    if time_str:
        try:
            datetime.strptime(time_str, "%H:%M")
        except ValueError:
            await update.message.reply_text("⚠️ Invalid time format. Use HH:MM (24-hour).")
            return

    tasks = load_tasks()
    task = {"name": name, "time": time_str, "repeat": repeat}
    tasks["pending"].append(task)
    save_tasks(tasks)
    schedule_task(task)

    msg = f"✅ Task added: {name}"
    if time_str:
        msg += f" at {time_str}"
    if repeat:
        msg += f" ({repeat})"
    await update.message.reply_text(msg)

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = load_tasks()
    msg = "🗓️ *Your Tasks:*\n"

    if tasks["pending"]:
        msg += "\n🔵 Pending:\n"
        for i, t in enumerate(tasks["pending"], start=1):
            line = f"{i}. {t['name']}"
            if t.get("time"):
                line += f" — {t['time']}"
            if t.get("repeat"):
                line += f" ({t['repeat']})"
            msg += line + "\n"
    else:
        msg += "\nNo pending tasks.\n"

    if tasks["done"]:
        msg += "\n✅ Completed:\n"
        for i, t in enumerate(tasks["done"], start=1):
            msg += f"{i}. {t['name']} (done)\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def done_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /done <task name>")
        return

    name = " ".join(context.args)
    tasks = load_tasks()
    found = None

    for t in tasks["pending"]:
        if t["name"].lower() == name.lower():
            found = t
            break

    if not found:
        await update.message.reply_text("⚠️ Task not found in pending.")
        return

    tasks["pending"].remove(found)
    tasks["done"].append(found)
    save_tasks(tasks)

    try:
        scheduler.remove_job(found["name"])
    except:
        pass

    await update.message.reply_text(f"✅ Marked as done: {found['name']}")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = load_tasks()
    if not tasks["done"]:
        await update.message.reply_text("No completed tasks yet.")
        return

    msg = "📜 *Completed Tasks:*\n"
    for i, t in enumerate(tasks["done"], start=1):
        msg += f"{i}. {t['name']}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def remove_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /remove <task name>")
        return

    name = " ".join(context.args)
    tasks = load_tasks()
    filtered_pending = [t for t in tasks["pending"] if t["name"].lower() != name.lower()]
    filtered_done = [t for t in tasks["done"] if t["name"].lower() != name.lower()]

    if len(filtered_pending) == len(tasks["pending"]) and len(filtered_done) == len(tasks["done"]):
        await update.message.reply_text("⚠️ Task not found.")
    else:
        tasks["pending"] = filtered_pending
        tasks["done"] = filtered_done
        save_tasks(tasks)
        try:
            scheduler.remove_job(name)
        except:
            pass
        await update.message.reply_text(f"🗑️ Permanently removed: {name}")

async def clear_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_tasks({"pending": [], "done": []})
    scheduler.remove_all_jobs()
    await update.message.reply_text("🧹 All tasks cleared!")

async def next_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = load_tasks()
    now = datetime.now()
    upcoming = []

    for t in tasks["pending"]:
        if not t.get("time"):
            continue
        try:
            t_time = datetime.strptime(t["time"], "%H:%M").replace(
                year=now.year, month=now.month, day=now.day
            )
            if t_time > now:
                upcoming.append((t["name"], t_time, t.get("repeat")))
        except:
            continue

    if not upcoming:
        await update.message.reply_text("No upcoming tasks for today.")
    else:
        next_task = min(upcoming, key=lambda x: x[1])
        repeat_text = f" ({next_task[2]})" if next_task[2] else ""
        await update.message.reply_text(
            f"🔜 Next task: {next_task[0]} at {next_task[1].strftime('%H:%M')}{repeat_text}"
        )

# === MAIN FUNCTION ===
def main():
    global bot_instance
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    bot_instance = Bot(token=BOT_TOKEN)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_task))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(CommandHandler("done", done_task))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("remove", remove_task))
    app.add_handler(CommandHandler("clear", clear_tasks))
    app.add_handler(CommandHandler("next", next_task))

    missed = reschedule_all()
    scheduler.start()

    print("✅ Bot is running and reminders are active.")

    if missed:
        missed_msg = "⚠️ Missed reminders while offline:\n"
        for m in missed:
            missed_msg += f"- {m['name']} at {m['time']}\n"
        app.bot.send_message(chat_id=CHAT_ID, text=missed_msg)

    app.run_polling()

if __name__ == "__main__":
    main()
