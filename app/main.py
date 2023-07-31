import asyncio
import os
import threading
import requests
import time
import hashlib
from telegram import Bot
from telegram.ext import Updater, CommandHandler, CallbackContext, ApplicationBuilder
from telegram import Bot, Update
import sqlite3
import logging


LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", 60))

DB_FILE = "database/url_change_notify.db"


if LOG_LEVEL.upper() == "DEBUG":
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.DEBUG)
elif LOG_LEVEL.upper() == "INFO":
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO)
elif LOG_LEVEL.upper() == "WARNING":
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.WARNING)
elif LOG_LEVEL.upper() == "ERROR":
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.ERROR)
    


logging.info("Starting bot...")




def get_url_hash(url):
    """Returns the MD5 hash of the content of the given URL."""
    response = requests.get(url)
    response.raise_for_status()
    return hashlib.md5(response.content).hexdigest()

async def send_telegram_notification(bot_token, chat_id, message):
    """Sends a message notification to the specified chat using the given bot token."""
    bot = Bot(token=bot_token)
    await bot.send_message(chat_id=chat_id, text=message)


async def cmd_start(update: Update, _: CallbackContext):
    """Handler for the /start command."""
    chat_id = update.effective_chat.id

    msg = "Hello there! I'm a bot that can monitor a URL for changes and notify you about it."
    msg += "\n\n"
    msg += "To get started, use the /monitor command to start monitoring a URL."
    msg += "\n\n"
    msg += "Use the /help command to see a list of available commands."
    msg += "\n\n"
    msg += f"Your Chat ID is: {chat_id}"

    await update.message.reply_text(msg)


async def cmd_monitor(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    url = context.args[0]

    sql_insert_url = """
        INSERT INTO urls (url, chat_id, hash)
        VALUES (?, ?, ?)
    """

    conn = create_db_connection(DB_FILE)
    conn.execute(sql_insert_url, (url, chat_id, get_url_hash(url)))
    conn.commit()
    conn.close()

    msg = f"Okay, I will monitor the URL {url} for changes and notify you about it."
    await update.message.reply_text(msg)

async def cmd_list(update: Update, _: CallbackContext):
    """Handler for the /list command."""
    chat_id = update.effective_chat.id

    sql_select_urls = """
        SELECT url FROM urls
        WHERE chat_id = ?
    """

    conn = create_db_connection(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(sql_select_urls, (chat_id,))
    urls = cursor.fetchall()
    conn.close()

    msg = "Here are the URLs you are monitoring:"
    msg += "\n\n"

    for url in urls:
        msg += f"- {url[0]}"
        msg += "\n"

    await update.message.reply_text(msg)

async def cmd_stop(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    url = context.args[0]

    sql_delete_url = """
        DELETE FROM urls
        WHERE chat_id = ? AND url = ?
    """

    conn = create_db_connection(DB_FILE)
    conn.execute(sql_delete_url, (chat_id, url))
    conn.commit()
    conn.close()

    msg = f"Okay, I will stop monitoring the URL {url}."
    await update.message.reply_text(msg)

async def cmd_help(update: Update, _: CallbackContext):
    """Handler for the /help command."""
    msg = "Here are the available commands:"
    msg += "\n\n"
    msg += "/start - Starts the bot"
    msg += "\n"
    msg += "/monitor <url> - Starts monitoring the given URL for changes"
    msg += "\n"
    msg += "/list - Lists the URLs you are monitoring"
    msg += "\n"
    msg += "/stop <url> - Stops monitoring the given URL for changes"
    msg += "\n"
    msg += "/help - Shows this help message"

    await update.message.reply_text(msg)

async def cmd_admin_stats(update: Update, _: CallbackContext):
    if str(update.effective_chat.id) != str(ADMIN_CHAT_ID):
        await update.message.reply_text("You are not authorized to use this command.")
        return
    
    sql_select_urls = """
        SELECT url, chat_id, hash FROM urls
    """

    conn = create_db_connection(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(sql_select_urls)
    rows = cursor.fetchall()
    conn.close()

    users = []
    for row in rows:
        chat_id = row[1]
        if chat_id not in users:
            users.append(chat_id)

    msg = f"currently there are {len(rows)} urls monitored"
    msg += "\n\n"
    msg += f"there are {len(users)} users using this bot"

    await update.message.reply_text(msg)



def create_db_connection(db_file):
    """Creates a database connection to the SQLite database specified by db_file."""
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        logging.info(f"Using SQLite version {sqlite3.version}")
        return conn
    except Exception as e:
        logging.error(f"An error occurred: {e}")

    return conn

def create_tables(conn):
    sql_create_table_urls = """
        CREATE TABLE IF NOT EXISTS urls (
            id integer PRIMARY KEY,
            url text NOT NULL,
            chat_id integer NOT NULL,
            hash text
        );
    """

    try:
        conn.execute(sql_create_table_urls)
    except Exception as e:
        logging.error(f"An error occurred: {e}")


async def check_urls_from_database():
    while True:
        logging.debug("Checking URLs from database...")

        sql_select_urls = """
            SELECT url, chat_id, hash FROM urls
        """

        conn = create_db_connection(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(sql_select_urls)
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            url = row[0]
            chat_id = row[1]
            last_hash = row[2]
            current_hash = get_url_hash(url)

            if last_hash != current_hash:
                message = f"The URL {url} has changed!"
                await send_telegram_notification(BOT_TOKEN, chat_id, message)

                sql_update_url = """
                    UPDATE urls
                    SET hash = ?
                    WHERE url = ?
                """

                conn = create_db_connection(DB_FILE)
                conn.execute(sql_update_url, (current_hash, url))
                conn.commit()
                conn.close()

        time.sleep(POLL_INTERVAL)
        
def task_check_urls_from_database():
    asyncio.run(check_urls_from_database())




if __name__ == "__main__":
    conn = create_db_connection(DB_FILE)
    create_tables(conn)
    conn.close()

    t1 = threading.Thread(target=task_check_urls_from_database)
    t1.start()


    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("monitor", cmd_monitor))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("help", cmd_help))

    app.add_handler(CommandHandler("admin_stats", cmd_admin_stats))

    app.run_polling()

