import os
import json
from datetime import datetime, timedelta
import dateparser

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)
from apscheduler.schedulers.background import BackgroundScheduler

# ========== Globals ==========
TASKS_FILE = "tasks.json"
tasks = []
scheduler = BackgroundScheduler(timezone="UTC")
scheduler.start()

# ========== Helpers ==========
def load_tasks():
    global tasks
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r") as f:
            tasks = json.load(f)
    else:
        tasks = []

def save_tasks():
    with open(TASKS_FILE, "w") as f:
        json.dump(tasks, f, indent=2, default=str)

def fmt_time(dt_str: str | None):
    """Format ISO datetime string -> 'Mon 06 Oct 16:00'."""
    if not dt_str:
        return ""
    dt = datetime.fromisoformat(dt_str)
    return dt.strftime("%a %d %b %H:%M")

def schedule_job_for_task(app, task, chat_id):
    """Register APScheduler job for this task."""
    if task.get("scheduled_at"):
        dt = datetime.fromisoformat(task["scheduled_at"])
        if dt > datetime.now():
            scheduler.add_job(
                send_reminder,
                "date",
                run_date=dt,
                args=[app, chat_id, task],
                id=f"task-{task['id']}",
                replace_existing=True
            )

async def send_reminder(app, chat_id, task):
    """Send reminder when scheduled job fires."""
    msg = f"⏰ Reminder: {task['text']}"
    if task.get("list"):
        msg += f" (📂 {task['list']})"
    await app.bot.send_message(chat_id=chat_id, text=msg)

def next_repeat_date(task):
    """Compute next occurrence for recurring tasks."""
    if not task.get("repeat") or not task.get("scheduled_at"):
        return None
    current = datetime.fromisoformat(task["scheduled_at"])
    repeat = task["repeat"].lower()

    if repeat == "daily":
        return current + timedelta(days=1)
    if repeat == "weekly":
        return current + timedelta(weeks=1)
    if repeat == "hourly":
        return current + timedelta(hours=1)
    return None

# ========== Commands ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hi! Use /add to add a task.\nExample:\n`/add [Work] Finish report Monday 4pm`",
                                    parse_mode="Markdown")

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a new task: /add [List] text [time/day] [repeat=daily/weekly] [priority=high]"""
    chat_id = update.message.chat_id
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage:\n`/add [List] Task description day/time repeat=daily priority=high`",
                                        parse_mode="Markdown")
        return

    # Parse [List]
    list_name = "General"
    if text.startswith("[") and "]" in text:
        list_name = text[1:text.index("]")]
        text = text[text.index("]") + 1:].strip()

    # Extract repeat/priority
    repeat = None
    priority = "normal"
    words = text.split()
    clean_words = []
    for w in words:
        if w.lower().startswith("repeat="):
            repeat = w.split("=")[1]
        elif w.lower().startswith("priority="):
            priority = w.split("=")[1].upper()
        else:
            clean_words.append(w)
    clean_text = " ".join(clean_words)

    # Parse datetime
    parsed_dt = dateparser.parse(clean_text)
    scheduled_at = None
    task_text = clean_text
    if parsed_dt:
        scheduled_at = parsed_dt.isoformat()
        task_text = clean_text

    # Build task
    task = {
        "id": len(tasks) + 1,
        "list": list_name,
        "text": task_text,
        "scheduled_at": scheduled_at,
        "repeat": repeat,
        "priority": priority
    }
    tasks.append(task)
    save_tasks()

    # Schedule reminder
    schedule_job_for_task(context.application, task, chat_id)

    when = fmt_time(scheduled_at) if scheduled_at else "No time"
    reply = f"✅ Added task:\n📂 {list_name} — {task_text}\n🕒 {when}"
    if repeat:
        reply += f"\n🔁 Repeats: {repeat}"
    if priority.upper() != "NORMAL":
        reply += f"\n⚡ Priority: {priority.upper()}"
    await update.message.reply_text(reply)

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all tasks grouped by list."""
    if not tasks:
        await update.message.reply_text("📭 No tasks yet.")
        return
    out = "📝 *Your Tasks:*\n"
    grouped = {}
    for t in tasks:
        grouped.setdefault(t["list"], []).append(t)

    for lst, lst_tasks in grouped.items():
        out += f"\n📂 *{lst}*\n"
        for i, t in enumerate(lst_tasks, 1):
            when = fmt_time(t.get("scheduled_at"))
            extra = ""
            if t.get("repeat"):
                extra += f" 🔁{t['repeat']}"
            if t.get("priority") and t["priority"].upper() != "NORMAL":
                extra += f" ⚡{t['priority'].upper()}"
            out += f"{i}. {t['text']} — {when}{extra}\n"
    await update.message.reply_text(out, parse_mode="Markdown")

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show only today’s tasks grouped by list."""
    today = datetime.now().date()
    todays_tasks = [t for t in tasks if t.get("scheduled_at") and datetime.fromisoformat(t["scheduled_at"]).date() == today]

    if not todays_tasks:
        await update.message.reply_text("✅ No tasks scheduled for today!")
        return

    out = f"🗓️ *Summary for {today.strftime('%A %d %B')}*\n"
    grouped = {}
    for t in todays_tasks:
        grouped.setdefault(t["list"], []).append(t)

    for lst, lst_tasks in grouped.items():
        out += f"\n📂 *{lst}*\n"
        for t in lst_tasks:
            when = fmt_time(t.get("scheduled_at"))
            extra = ""
            if t.get("repeat"):
                extra += f" 🔁{t['repeat']}"
            if t.get("priority") and t["priority"].upper() != "NORMAL":
                extra += f" ⚡{t['priority'].upper()}"
            out += f"- {t['text']} — {when}{extra}\n"

    await update.message.reply_text(out, parse_mode="Markdown")

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mark a task as done (by ID in /list order)."""
    if not context.args:
        await update.message.reply_text("Usage: /done <task-id>")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid task ID.")
        return
    found = None
    for t in tasks:
        if t["id"] == task_id:
            found = t
            break
    if not found:
        await update.message.reply_text("Task not found.")
        return

    # Reschedule if repeating
    if found.get("repeat"):
        nxt = next_repeat_date(found)
        if nxt:
            found["scheduled_at"] = nxt.isoformat()
            schedule_job_for_task(context.application, found, update.message.chat_id)
            save_tasks()
            await update.message.reply_text(f"✅ Task rescheduled for {fmt_time(found['scheduled_at'])}")
            return

    tasks.remove(found)
    save_tasks()
    await update.message.reply_text("✅ Task completed and removed.")

# ========== Main ==========
def main():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        print("❌ BOT_TOKEN not set")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("done", done))

    load_tasks()

    print("🤖 Bot is running with day+time + /summary support...")
    app.run_polling()

if __name__ == "__main__":
    main()
