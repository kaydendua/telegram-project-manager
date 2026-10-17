import sqlite3
from contextlib import contextmanager
from os import getenv

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = getenv("BOT_TOKEN")
DB_PATH = getenv("DB_PATH", "pinboard.db")

MAX_MESSAGE_LENGTH = 4000  # Telegram's hard limit is 4096

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
/updatetaskstatus <task_id> <status> - Update the status of a task
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


# ---------- Database ----------
@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'todo',
                description TEXT,
                assignee TEXT,
                due TEXT
            );
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                description TEXT
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                content TEXT NOT NULL
            );
            """
        )


# Helpers
def chat_id_of(update: Update) -> int:
    return update.effective_chat.id


def parse_id(args):
    if not args:
        return None
    try:
        return int(args[0].lstrip("#"))
    except ValueError:
        return None

# Send a text message, splitting into several messages if it is too long
async def send(update: Update, text: str):
    chunk = ""
    for line in text.split("\n"):
        line = line[:MAX_MESSAGE_LENGTH]
        if len(chunk) + len(line) + 1 > MAX_MESSAGE_LENGTH:
            await update.message.reply_text(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await update.message.reply_text(chunk)


def tasks_text(chat_id: int) -> str:
    with db() as c:
        rows = c.execute(
            "SELECT * FROM tasks WHERE chat_id = ? AND status != 'done' ORDER BY id", (chat_id,)
        ).fetchall()
    if not rows:
        return "Tasks:\nNo open tasks."
    lines = ["Tasks:"]
    for t in rows:
        lines.append(f"[{t['id']}] {t['name']} - {t['status']}")
        if t["description"]:
            lines.append(f"    {t['description']}")
        details = []
        if t["assignee"]:
            details.append(f"Assigned to: {t['assignee']}")
        if t["due"]:
            details.append(f"Due: {t['due']}")
        if details:
            lines.append("    " + " - ".join(details))
    return "\n".join(lines)


def links_text(chat_id: int) -> str:
    with db() as c:
        rows = c.execute("SELECT * FROM links WHERE chat_id = ? ORDER BY id", (chat_id,)).fetchall()
    if not rows:
        return "Links:\nNo links found."
    lines = ["Links:"]
    for link in rows:
        line = f"[{link['id']}] {link['url']}"
        if link["description"]:
            line += f" - {link['description']}"
        lines.append(line)
    return "\n".join(lines)


def notes_text(chat_id: int) -> str:
    with db() as c:
        rows = c.execute("SELECT * FROM notes WHERE chat_id = ? ORDER BY id", (chat_id,)).fetchall()
    if not rows:
        return "Notes:\nNo notes found."
    return "Notes:\n" + "\n".join(f"[{n['id']}] {n['content']}" for n in rows)


# General commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Pinboard is now running! Use /help to see what I can do.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(help_text)


async def everything(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = chat_id_of(update)
    await send(update, "\n\n".join([tasks_text(chat_id), notes_text(chat_id), links_text(chat_id)]))


# Tasks
async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send(update, tasks_text(chat_id_of(update)))


async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = [p.strip() or None for p in " ".join(context.args).split(";")]
    parts += [None] * (4 - len(parts))
    name, description, assignee, due_date = parts[:4]
    if not name:
        await update.message.reply_text("Usage: /task <task_name> ; <task_description> ; <assignee> ; <due_date>")
        return

    with db() as c:
        cur = c.execute(
            "INSERT INTO tasks (chat_id, name, description, assignee, due) VALUES (?, ?, ?, ?, ?)",
            (chat_id_of(update), name, description, assignee, due_date),
        )
        task_id = cur.lastrowid
    await update.message.reply_text(f"Task added successfully! [{task_id}: {name}]")


async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_id = parse_id(context.args)
    if task_id is None or len(context.args) < 2:
        await update.message.reply_text("Usage: /assigntask <task_id> <assignee>")
        return

    assignee = " ".join(context.args[1:])
    with db() as c:
        cur = c.execute(
            "UPDATE tasks SET assignee = ? WHERE id = ? AND chat_id = ?", (assignee, task_id, chat_id_of(update))
        )
        found = cur.rowcount > 0
    if not found:
        await update.message.reply_text(f"No task found with ID {task_id}.")
        return
    await update.message.reply_text(f"Task [{task_id}] assigned to {assignee}.")


async def update_task_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_id = parse_id(context.args)
    if task_id is None or len(context.args) < 2:
        await update.message.reply_text(f"Usage: /updatetaskstatus <task_id> <status>")
        return

    new_status = context.args[1].lower()
    if new_status not in VALID_STATUSES:
        await update.message.reply_text(f"Status must be one of: {', '.join(VALID_STATUSES)}.")
        return

    with db() as c:
        cur = c.execute(
            "UPDATE tasks SET status = ? WHERE id = ? AND chat_id = ?", (new_status, task_id, chat_id_of(update))
        )
        found = cur.rowcount > 0
    if not found:
        await update.message.reply_text(f"No task found with ID {task_id}.")
        return
    await update.message.reply_text(f"Task [{task_id}] status updated to: {new_status}")


async def complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_id = parse_id(context.args)
    if task_id is None:
        await update.message.reply_text("Usage: /completetask <task_id>")
        return

    with db() as c:
        cur = c.execute(
            "UPDATE tasks SET status = 'done' WHERE id = ? AND chat_id = ?", (task_id, chat_id_of(update))
        )
        found = cur.rowcount > 0
    if not found:
        await update.message.reply_text(f"No task found with ID {task_id}.")
        return
    await update.message.reply_text(f"Task [{task_id}] marked as completed.")


async def delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_id = parse_id(context.args)
    if task_id is None:
        await update.message.reply_text("Usage: /deletetask <task_id>")
        return

    chat_id = chat_id_of(update)
    with db() as c:
        row = c.execute("SELECT name FROM tasks WHERE id = ? AND chat_id = ?", (task_id, chat_id)).fetchone()
        if row:
            c.execute("DELETE FROM tasks WHERE id = ? AND chat_id = ?", (task_id, chat_id))
    if not row:
        await update.message.reply_text(f"No task found with ID {task_id}.")
        return
    await update.message.reply_text(f"Task [{task_id}: {row['name']}] deleted.")


# Links
async def show_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send(update, links_text(chat_id_of(update)))


async def add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /link <url> <description>")
        return

    url = context.args[0]
    description = " ".join(context.args[1:]) or None
    with db() as c:
        cur = c.execute(
            "INSERT INTO links (chat_id, url, description) VALUES (?, ?, ?)", (chat_id_of(update), url, description)
        )
        link_id = cur.lastrowid
    await update.message.reply_text(f"Link added successfully! [{link_id}: {url}]")


async def edit_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link_id = parse_id(context.args)
    if link_id is None or len(context.args) < 2:
        await update.message.reply_text("Usage: /editlink <link_id> <new_description>")
        return

    new_description = " ".join(context.args[1:])
    with db() as c:
        cur = c.execute(
            "UPDATE links SET description = ? WHERE id = ? AND chat_id = ?",
            (new_description, link_id, chat_id_of(update)),
        )
        found = cur.rowcount > 0
    if not found:
        await update.message.reply_text(f"No link found with ID {link_id}.")
        return
    await update.message.reply_text(f"Link [{link_id}] description updated to: {new_description}")


async def delete_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link_id = parse_id(context.args)
    if link_id is None:
        await update.message.reply_text("Usage: /deletelink <link_id>")
        return

    with db() as c:
        cur = c.execute("DELETE FROM links WHERE id = ? AND chat_id = ?", (link_id, chat_id_of(update)))
        found = cur.rowcount > 0
    if not found:
        await update.message.reply_text(f"No link found with ID {link_id}.")
        return
    await update.message.reply_text(f"Link [{link_id}] deleted.")


# Notes
async def show_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send(update, notes_text(chat_id_of(update)))


async def add_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = " ".join(context.args).strip()
    if not content:
        await update.message.reply_text("Usage: /note <note_content>")
        return

    with db() as c:
        cur = c.execute("INSERT INTO notes (chat_id, content) VALUES (?, ?)", (chat_id_of(update), content))
        note_id = cur.lastrowid
    await update.message.reply_text(f"Note added successfully! [ID: {note_id}]")


async def delete_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note_id = parse_id(context.args)
    if note_id is None:
        await update.message.reply_text("Usage: /deletenote <note_id>")
        return

    with db() as c:
        cur = c.execute("DELETE FROM notes WHERE id = ? AND chat_id = ?", (note_id, chat_id_of(update)))
        found = cur.rowcount > 0
    if not found:
        await update.message.reply_text(f"No note found with ID {note_id}.")
        return
    await update.message.reply_text(f"Note [{note_id}] deleted.")


# Main
def main():
    if not BOT_TOKEN:
        raise SystemExit("Set the BOT_TOKEN environment variable (get one from @BotFather).")

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    handlers = {
        "start": start,
        "help": help_command,
        "everything": everything,
        "task": add_task,
        "assigntask": assign_task,
        "completetask": complete_task,
        "deletetask": delete_task,
        "updatetaskstatus": update_task_status,
        "showtasks": show_tasks,
        "link": add_link,
        "editlink": edit_link,
        "deletelink": delete_link,
        "showlinks": show_links,
        "note": add_note,
        "shownotes": show_notes,
        "deletenote": delete_note,
    }
    for command, handler in handlers.items():
        app.add_handler(CommandHandler(command, handler))

    app.run_polling()


if __name__ == "__main__":
    main()