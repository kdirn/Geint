import os
import sqlite3
import discord
from discord import app_commands
from dotenv import load_dotenv
import aiohttp

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # can be empty or missing

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set in .env file")

DB_NAME = "database.db"

def init_db():
    """Create the database and logs table if they don't exist."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT,
            location TEXT,
            timestamp TEXT,
            finder TEXT,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add columns if they don't exist (for existing databases)
    for column, column_type in [
        ("finder", "TEXT"),
        ("note", "TEXT")
    ]:
        try:
            cursor.execute(f"ALTER TABLE logs ADD COLUMN {column} {column_type}")
        except sqlite3.OperationalError:
            pass  # column already exists

    conn.commit()
    conn.close()


init_db()

class LogBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # Sync slash commands globally
        await self.tree.sync()
        print("Slash commands synced.")


bot = LogBot()


@bot.tree.command(name="log", description="Log an observation with optional details.")
@app_commands.describe(
    location="Location of the observation",
    name="Name of the thing observed",
    image="An image attachment",
    timestamp="A timestamp (any text format)",
    finder="Name of the person who found it",
    note="Additional notes about the logging"
)
async def log_command(
    interaction: discord.Interaction,
    location: str = None,
    name: str = None,
    image: discord.Attachment = None,
    timestamp: str = None,
    finder: str = None,
    note: str = None
):
    
    await interaction.response.defer(ephemeral=False)

    user_id = interaction.user.id
    
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO logs (user_id, name, location, timestamp, finder, note) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, location, timestamp, finder, note)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database error: {e}")
        await interaction.followup.send(
            "Failed to save log to database.",
            ephemeral=True
        )
        return

    webhook_sent = False

    if WEBHOOK_URL and WEBHOOK_URL.strip():
        try:
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)

                embed = discord.Embed(
                    title="New Log Entry",
                    color=discord.Color.blue()
                )

                if name:
                    embed.add_field(name="Name", value=name, inline=True)

                if location:
                    embed.add_field(name="Location", value=location, inline=True)

                if finder:
                    embed.add_field(name="Finder", value=finder, inline=True)

                if timestamp:
                    embed.add_field(name="Timestamp", value=timestamp, inline=True)

                if note:
                    embed.add_field(name="Note", value=note, inline=False)

                embed.set_footer(
                    text=f"Logged by {interaction.user} (ID: {user_id})"
                )

                if image and image.content_type and image.content_type.startswith("image/"):
                    embed.set_image(url=image.url)

                await webhook.send(embed=embed)
                webhook_sent = True

        except Exception as e:
            print(f"Webhook error: {e}")

    message = "Log saved successfully"

    if webhook_sent:
        message += " and forwarded to webhook."
    else:
        if WEBHOOK_URL:
            message += ". (Webhook could not be sent – check the console for errors)"
        else:
            message += ". (No webhook configured)"

    await interaction.followup.send(message, ephemeral=True)


if __name__ == "__main__":
    bot.run(TOKEN)
