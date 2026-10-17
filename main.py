import sqlite3
import re

from os import getenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = getenv("BOT_TOKEN")
DB_PATH = getenv("DB_PATH", "pinboard.db")

# Databse
def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'todo',
                description TEXT,
                assignee TEXT,
                due TEXT
            );
            """
        )

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Project Manager Running.")

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Available commands:\n/start - Start the bot\n/help - Show this help message")

# Tasks

# show incomplete tasks
async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db() as c:
        c.execute("SELECT * FROM tasks WHERE status != 'done'")
        tasks = c.fetchall()

    if not tasks:
        await update.message.reply_text("No tasks found.")
        return

    task_list = "\n".join(
        [f"[{task['id']}] {task['name']} - {task['status']}\n{task['description']}\nAssigned to: {task['assignee']} - Due: {task['due']}" for task in tasks]
    )
    await update.message.reply_text(f"Tasks:\n{task_list}")

# create a new task
async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /addtask <task_name> ; <task_description> ; <assignee> ; <due_date>")
        return

    task_name = " ".join(context.args)
    description = None
    if " ; " in task_name:
        task_name, description = task_name.split(" ; ", 1)

    assignee = None
    due_date = None
    # Parse assignee and due date from the remaining arguments
    if " ; " in description:
        description, assignee = description.split(" ; ", 1)
    if " ; " in assignee:
        assignee, due_date = assignee.split(" ; ", 1)

    m = re.search(r"@\w+", text)
    if m:
        assignee = m.group(0)
        text = (text[: m.start()] + text[m.end():]).strip()
    with db() as c:
        c.execute("INSERT INTO tasks (name, description, assignee, due) VALUES (?, ?, ?, ?)", (task_name, description, assignee, due_date))
        task_id = c.lastrowid
    await update.message.reply_text(f"Task added successfully! [{task_id}: {task_name}]")

# assign a task to a user
async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /assigntask <task_id> <assignee>")
        return

    task_id = context.args[0]
    assignee = " ".join(context.args[1:])
    with db() as c:
        c.execute("UPDATE tasks SET assignee = ? WHERE id = ?", (assignee, task_id))
        if c.rowcount == 0:
            await update.message.reply_text(f"No task found with ID {task_id}.")
            return
    await update.message.reply_text(f"Task [{task_id}] assigned to {assignee}.")

# update the status of a task
async def update_task_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /updatetaskstatus <task_id> <new_task_status>")
        return

    task_id = context.args[0]
    new_task_status = " ".join(context.args[1:])
    with db() as c:
        c.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_task_status, task_id))
        if c.rowcount == 0:
            await update.message.reply_text(f"No task found with ID {task_id}.")
            return
    await update.message.reply_text(f"Task [{task_id}] status updated to: {new_task_status}")

# delete a task
async def delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /deletetask <task_id>")
        return

    task_id = context.args[0]
    with db() as c:
        c.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if c.rowcount == 0:
            await update.message.reply_text(f"No task found with ID {task_id}.")
            return
    await update.message.reply_text(f"Task [{task_id}] deleted.")

# complete a task
async def complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /completetask <task_id>")
        return

    task_id = context.args[0]
    with db() as c:
        c.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))
        if c.rowcount == 0:
            await update.message.reply_text(f"No task found with ID {task_id}.")
            return
    await update.message.reply_text(f"Task [{task_id}] marked as completed.")

if __name__ == "__main__":
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start"  , start))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(CommandHandler("addtask", add_task))
    app.add_handler(CommandHandler("assigntask", assign_task))
    app.add_handler(CommandHandler("completetask", complete_task))
    app.add_handler(CommandHandler("deletetask", delete_task))
    app.add_handler(CommandHandler("updatetaskstatus", update_task_status))
    app.add_handler(CommandHandler("showtasks", show_tasks))