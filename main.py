import sqlite3
import re

from os import getenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = getenv("BOT_TOKEN")
DB_PATH = getenv("DB_PATH", "pinboard.db")

help_text = """
Pinboard is a simple project management bot that helps organise key information!

Available commands:
/start - Start the bot
/help - Show this help message
/everything - Show all tasks, notes, and links

Tasks: manage your tasks
/task <task_name> ; <task_description> ; <assignee> ; <due_date> - Add a new task
/assigntask <task_id> <assignee> - Assign a task to a user
/completetask <task_id> - Mark a task as completed
/deletetask <task_id> - Delete a task
/updatetaskstatus <task_id> <new_task_status> - Update the status of a task
/showtasks - Show all incomplete tasks

Links: store links to external resources and documents
/link <url> <description> - Add a new link
/editlink <link_id> <new_description> - Edit the description of a link
/deletelink <link_id> - Delete a link
/showlinks - Show all links

Notes: save bits of key information and ideas
/note <note_content> - Add a new note
/shownotes - Show all notes
/deletenote <note_id> - Delete a note
"""

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
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                description TEXT
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL
            );
            """
        )

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Project Manager Running.")

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(help_text)

async def everything(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_tasks(update, context)
    await show_notes(update, context)
    await show_links(update, context)

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
        await update.message.reply_text("Usage: /task <task_name> ; <task_description> ; <assignee> ; <due_date>")
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
    task_name = None
    with db() as c:
        c.execute("SELECT name FROM tasks WHERE id = ?", (task_id,))
        row = c.fetchone()
        if row:
            task_name = row["name"]
        c.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if c.rowcount == 0:
            await update.message.reply_text(f"No task found with ID {task_id}.")
            return
        
    await update.message.reply_text(f"Task [{task_id}: {task_name}] deleted.")

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

# Links

# show all links
async def show_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db() as c:
        c.execute("SELECT * FROM links")
        links = c.fetchall()

    if not links:
        await update.message.reply_text("No links found.")
        return

    link_list = "\n".join(
        [f"[{link['id']}] {link['url']} - {link['description']}" for link in links]
    )
    await update.message.reply_text(f"Links:\n{link_list}")

# add a new link
async def add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /link <url> <description>")
        return

    url = context.args[0]
    description = " ".join(context.args[1:]) if len(context.args) > 1 else None
    with db() as c:
        c.execute("INSERT INTO links (url, description) VALUES (?, ?)", (url, description))
        link_id = c.lastrowid
    await update.message.reply_text(f"Link added successfully! [{link_id}: {url}]")

# edit the description of a link
async def edit_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /editlink <link_id> <new_description>")
        return

    link_id = context.args[0]
    new_description = " ".join(context.args[1:])
    with db() as c:
        c.execute("UPDATE links SET description = ? WHERE id = ?", (new_description, link_id))
        if c.rowcount == 0:
            await update.message.reply_text(f"No link found with ID {link_id}.")
            return
    await update.message.reply_text(f"Link [{link_id}] description updated to: {new_description}")

# delete a link
async def delete_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /deletelink <link_id>")
        return

    link_id = context.args[0]
    with db() as c:
        c.execute("DELETE FROM links WHERE id = ?", (link_id,))
        if c.rowcount == 0:
            await update.message.reply_text(f"No link found with ID {link_id}.")
            return
    await update.message.reply_text(f"Link [{link_id}] deleted.")

# Notes

# show all notes
async def show_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db() as c:
        c.execute("SELECT * FROM notes")
        notes = c.fetchall()

    if not notes:
        await update.message.reply_text("No notes found.")
        return

    note_list = "\n".join(
        [f"[{note['id']}]:\n{note['content']}" for note in notes]
    )
    await update.message.reply_text(f"Notes:\n{note_list}")

# add a new note
async def add_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /addnote <note_content>")
        return

    content = " ".join(context.args)
    with db() as c:
        c.execute("INSERT INTO notes (content) VALUES (?)", (content,))
        note_id = c.lastrowid
    await update.message.reply_text(f"Note added successfully! [ID: {note_id}]")

# delete a note
async def delete_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /deletenote <note_id>")
        return

    note_id = context.args[0]
    with db() as c:
        c.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        if c.rowcount == 0:
            await update.message.reply_text(f"No note found with ID {note_id}.")
            return
    await update.message.reply_text(f"Note [{note_id}] deleted.")


# Main
if __name__ == "__main__":
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start"  , start))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(CommandHandler("task", add_task))
    app.add_handler(CommandHandler("assigntask", assign_task))
    app.add_handler(CommandHandler("completetask", complete_task))
    app.add_handler(CommandHandler("deletetask", delete_task))
    app.add_handler(CommandHandler("updatetaskstatus", update_task_status))
    app.add_handler(CommandHandler("showtasks", show_tasks))
    app.add_handler(CommandHandler("link", add_link))
    app.add_handler(CommandHandler("editlink", edit_link))
    app.add_handler(CommandHandler("deletelink", delete_link))
    app.add_handler(CommandHandler("showlinks", show_links))
    app.add_handler(CommandHandler("note", add_note))
    app.add_handler(CommandHandler("shownotes", show_notes))
    app.add_handler(CommandHandler("deletenote", delete_note))