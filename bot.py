
import discord
from discord import app_commands
from discord.ext import commands, tasks
import requests
import asyncio
from collections import defaultdict, deque
import time
from discord import ui, Interaction, ButtonStyle, PermissionOverwrite
import json
import os
import io
import urllib.parse
import re
import google.generativeai as genai
import datetime
from datetime import timedelta
import random
import string
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
try:
    import psutil
    import platform
    import socket
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil not installed. Host statistics will not be available.")
    print("Install with: pip install psutil")


# ----------------- BOT SETUP -----------------
# Define the necessary intents.
# Privileged Intents (members, message_content) have been re-enabled.
# You MUST enable them in your bot's settings on the Discord Developer Portal
# for the bot to start and for related features to work.
intents = discord.Intents.default()
intents.members = True # ENABLED - Required for welcome messages, join/leave logs, and /dms command.
intents.message_content = True # ENABLED - Required for anti-link and reading message content.
intents.guilds = True # Required for audit log events and invite tracking
intents.invites = True # Required for invite tracking
bot = commands.Bot(command_prefix="!", intents=intents)

# Global check: only administrators can use any slash command
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ You need to be an administrator to use this command.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ An error occurred: {str(error)}", ephemeral=True)

async def is_admin(interaction: discord.Interaction) -> bool:
    if not interaction.user.guild_permissions.administrator:
        raise app_commands.CheckFailure()
    return True

bot.tree.interaction_check = is_admin

# ----------------- GLOBAL VARIABLES & CONSTANTS -----------------
VIRUSTOTAL_API_KEY = "fae4c31b938d6409163c24d2715590c5d21e4c278d9797e1f30091f11ebd2936"
user_message_times = defaultdict(lambda: deque(maxlen=15))
GEMINI_API_KEY = None
active_ai_chats = {} # {thread_id: genai.ChatSession}
AUTHORIZED_ADMINS = {838411101645045821}

# --- Persistence ---
LOG_CHANNELS_FILE = "log_channels.json"
WELCOME_FILE = "welcome_channel.json"
GOODBYE_FILE = "goodbye_channel.json"
WHITELIST_FILE = "whitelist.json"
AUTOROLE_FILE = "autorole.json"
GEMINI_API_KEY_FILE = "gemini_api_key.json"
STATUS_CHANNELS_FILE = "status_channels.json"
SPAM_SETTINGS_FILE = "spam_settings.json"
DOMAIN_BLACKLIST_FILE = "domain_blacklist.json"
ANTI_NUKE_SETTINGS_FILE = "anti_nuke_settings.json"
INVITES_FILE = "invites.json"
INVITE_LEADERBOARD_FILE = "invite_leaderboard.json"
GLOBAL_BANS_FILE = "global_bans.json"
BOT_ANNOUNCEMENT_CHANNELS_FILE = "bot_announcement_channels.json"
TICKET_CATEGORIES_FILE = "ticket_categories.json"
SUGGESTIONS_CHANNEL_FILE = "suggestions_channel.json"
VERIFICATION_FILE = "verification.json"
TICKET_LOGS_FILE = "ticket_logs.json"
TICKET_COUNTERS_FILE = "ticket_counters.json"
TICKET_FEEDBACK_CHANNEL_ID = 1502647012431101992

# --- Ticket Auto-Close (Idle) ---
AUTO_CLOSE_WARNING_AFTER_HOURS = 12
AUTO_CLOSE_GRACE_MINUTES = 30
AUTO_CLOSE_CHECK_EVERY_MINUTES = 5

ticket_last_activity = {}  # {channel_id: datetime}
ticket_warned_at = {}      # {channel_id: datetime}
ticket_counters = {        # {ticket_type: counter_number}
    'purchase': 0,
    'support': 0,
    'media_apply': 0,
    'investor': 0
}


def is_ticket_channel(channel: discord.abc.GuildChannel) -> bool:
    try:
        name = (channel.name or "").lower()
        if name.startswith(("purchase-", "support-", "media-apply-", "investor-", "report-")):
            return True
        if getattr(channel, "category", None) and (channel.category.name or "").lower() == "active tickets":
            return True
    except Exception:
        return False
    return False


async def close_ticket_no_interaction(channel, guild: discord.Guild, reason: str):
    """Close a ticket channel/thread without an interaction (auto-close)."""
    # Create transcript before deleting
    transcript_messages = []
    try:
        async for message in channel.history(limit=None, oldest_first=True):
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            author = (
                f"{message.author.name}#{message.author.discriminator}"
                if getattr(message.author, "discriminator", "0") != "0"
                else message.author.name
            )
            content = message.content if message.content else "[No text content]"

            if message.attachments:
                attachments_info = "\n".join([f"  📎 {att.filename} ({att.url})" for att in message.attachments])
                content += f"\n{attachments_info}"

            if message.embeds:
                content += f"\n  [Message contains {len(message.embeds)} embed(s)]"

            transcript_messages.append(f"[{timestamp}] {author}: {content}")
    except Exception as e:
        print(f"Error creating transcript (auto-close): {e}")

    # Send transcript to logs channel if configured
    if ticket_logs_channel_id and transcript_messages:
        logs_channel = guild.get_channel(ticket_logs_channel_id)
        if logs_channel:
            transcript_text = "\n".join(transcript_messages)
            transcript_file = discord.File(
                io.StringIO(transcript_text),
                filename=f"ticket-{channel.name}-{int(time.time())}.txt"
            )
            transcript_embed = discord.Embed(
                title="🎫 Ticket Transcript",
                description=(
                    f"**Ticket:** {channel.mention if not isinstance(channel, discord.Thread) else channel.name}\n"
                    f"**Closed by:** {bot.user.mention if bot.user else 'Bot'}\n"
                    f"**Reason:** {reason}\n"
                    f"**Messages:** {len(transcript_messages)}"
                ),
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            if guild.icon:
                transcript_embed.set_thumbnail(url=guild.icon.url)
            try:
                await logs_channel.send(embed=transcript_embed, file=transcript_file)
            except Exception as e:
                print(f"Error sending transcript (auto-close): {e}")

    # DM feedback panel to ticket owner (best-effort)
    try:
        ticket_owner = await get_ticket_owner_user(channel, guild)
        if ticket_owner:
            fb_embed = discord.Embed(
                title="How was your support?",
                description=(
                    "This ticket has been automatically closed due to inactivity. "
                    "If you have a moment, use the button below to rate your experience and leave a short message."
                ),
                color=discord.Color.blurple(),
            )
            if guild.icon:
                fb_embed.set_thumbnail(url=guild.icon.url)
            fb_embed.set_footer(text=guild.name)
            try:
                await ticket_owner.send(
                    embed=fb_embed,
                    view=TicketFeedbackPanelView(guild.id, guild.name),
                )
            except discord.Forbidden:
                pass
            except Exception as e:
                print(f"Ticket feedback DM failed (auto-close): {e}")
    except Exception as e:
        print(f"Error preparing feedback DM (auto-close): {e}")

    # Log + delete
    try:
        close_embed = discord.Embed(
            title="Ticket Closed (Auto)",
            description=f"Ticket `{channel.name}` was auto-closed due to inactivity.\n**Reason:** {reason}",
            color=discord.Color.dark_red()
        )
        await send_log(guild, "moderation", close_embed)
    except Exception:
        pass

    try:
        await channel.delete(reason=reason)
    except Exception as e:
        print(f"Error deleting ticket channel (auto-close): {e}")


welcome_channel_id = None
goodbye_channel_id = None
verification_config = {} # {guild_id: {'channel_id': int, 'role_id': int, 'message_id': int}}
autorole_id = None
suggestions_channel_id = None
ticket_logs_channel_id = None
suggestion_cooldowns = {} # In-memory: {user_id: timestamp}
log_channels = {
    "member": None,
    "message": None,
    "voice": None,
    "moderation": None,
    "security": None,
    "file": None,
    "server": None
}
status_channels = {
    "category": None,
    "total": None,
    "online": None,
    "boosts": None,
    "roles": None,
    "channels": None
}
whitelisted_users = set()
blacklisted_domains = set()
spam_settings = {'enabled': False, 'message_count': 7, 'time_window': 5, 'action': 'warn', 'timeout_duration': 10}
anti_nuke_settings = {
    'enabled': True,
    'max_channels_per_minute': 3,
    'max_roles_per_minute': 5,
    'max_bans_per_minute': 5,
    'max_kicks_per_minute': 10,
    'protect_channels': True,
    'protect_roles': True,
    'protect_members': True,
    'auto_ban': False,  # If True, bans instead of kicks
    'log_actions': True
}
globally_banned_users = {} # {user_id_str: reason_str}
bot_announcement_channels = {} # {guild_id: channel_id}
ticket_categories = defaultdict(list) # {guild_id: [category_name, ...]}

# Anti-nuke action tracking
user_actions = defaultdict(lambda: defaultdict(list))  # {user_id: {action_type: [timestamps]}}
ANTI_NUKE_ACTIONS = {
    'channel_create': 'max_channels_per_minute',
    'channel_delete': 'max_channels_per_minute', 
    'role_create': 'max_roles_per_minute',
    'role_delete': 'max_roles_per_minute',
    'ban': 'max_bans_per_minute',
    'kick': 'max_kicks_per_minute'
}

# --- Invite Tracker Data ---
# guild_id -> user_id -> {'regular': 0, 'left': 0, 'fake': 0}
invites_data = defaultdict(lambda: defaultdict(lambda: {'regular': 0, 'left': 0, 'fake': 0}))
# guild_id -> invited_member_id -> inviter_id
invite_map = defaultdict(dict)
# guild_id -> {'channel_id': int, 'message_id': int}
invite_leaderboard_config = {}
# In-memory cache: guild_id -> {code: {'uses': int, 'inviter_id': int}}
guild_invites_cache = {}

# --- Support Call System ---
support_channels = {}  # {guild_id: channel_id}
active_support_calls = {}  # {user_id: {'temp_channel': channel_id, 'original_channel': channel_id}}
SUPPORT_CHANNELS_FILE = "support_channels.json"

# --- Auto-refresh Host Stats ---
auto_refresh_host_stats = {}  # {message_id: {'channel': channel, 'message': message}}

# --- VC Stay Tracking ---
vc_stay_channels = {}  # {guild_id: voice_channel_id} — channels the bot should stay in


# ----------------- PERSISTENCE FUNCTIONS -----------------
def save_log_channels():
    with open(LOG_CHANNELS_FILE, "w") as f:
        json.dump(log_channels, f, indent=4)

def load_log_channels():
    global log_channels
    if os.path.exists(LOG_CHANNELS_FILE):
        try:
            with open(LOG_CHANNELS_FILE, "r") as f:
                data = json.load(f)
                # Ensure all keys exist, defaulting to None if not in file
                for key in log_channels:
                    log_channels[key] = data.get(key)
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {LOG_CHANNELS_FILE}.")

def save_welcome_channel():
    with open(WELCOME_FILE, "w") as f:
        json.dump({"welcome_channel_id": welcome_channel_id}, f)

def load_welcome_channel():
    global welcome_channel_id
    if os.path.exists(WELCOME_FILE):
        try:
            with open(WELCOME_FILE, "r") as f:
                data = json.load(f)
                welcome_channel_id = data.get("welcome_channel_id")
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {WELCOME_FILE}.")

def save_goodbye_channel():
    with open(GOODBYE_FILE, "w") as f:
        json.dump({"goodbye_channel_id": goodbye_channel_id}, f)

def load_goodbye_channel():
    global goodbye_channel_id
    if os.path.exists(GOODBYE_FILE):
        try:
            with open(GOODBYE_FILE, "r") as f:
                data = json.load(f)
                goodbye_channel_id = data.get("goodbye_channel_id")
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {GOODBYE_FILE}.")

def save_whitelist():
    with open(WHITELIST_FILE, "w") as f:
        json.dump(list(whitelisted_users), f)

def load_whitelist():
    global whitelisted_users
    if os.path.exists(WHITELIST_FILE):
        try:
            with open(WHITELIST_FILE, "r") as f:
                whitelisted_users = set(json.load(f))
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {WHITELIST_FILE}.")

def save_autorole():
    with open(AUTOROLE_FILE, 'w') as f:
        json.dump({'autorole_id': autorole_id}, f)

def load_autorole():
    global autorole_id
    if os.path.exists(AUTOROLE_FILE):
        try:
            with open(AUTOROLE_FILE, 'r') as f:
                data = json.load(f)
                autorole_id = data.get('autorole_id')
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {AUTOROLE_FILE}.")

def save_gemini_key():
    with open(GEMINI_API_KEY_FILE, 'w') as f:
        json.dump({'api_key': GEMINI_API_KEY}, f)

def load_gemini_key():
    global GEMINI_API_KEY
    if os.path.exists(GEMINI_API_KEY_FILE):
        try:
            with open(GEMINI_API_KEY_FILE, 'r') as f:
                data = json.load(f)
                GEMINI_API_KEY = data.get('api_key')
                if GEMINI_API_KEY:
                    genai.configure(api_key=GEMINI_API_KEY)
                    print("Gemini API key loaded and configured.")
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {GEMINI_API_KEY_FILE}.")

def save_status_channels():
    with open(STATUS_CHANNELS_FILE, 'w') as f:
        json.dump(status_channels, f, indent=4)

def load_status_channels():
    global status_channels
    if os.path.exists(STATUS_CHANNELS_FILE):
        try:
            with open(STATUS_CHANNELS_FILE, 'r') as f:
                data = json.load(f)
                # Ensure all keys exist, defaulting to None if not in file
                for key in status_channels:
                    status_channels[key] = data.get(key)
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {STATUS_CHANNELS_FILE}.")

def save_spam_settings():
    with open(SPAM_SETTINGS_FILE, 'w') as f:
        json.dump(spam_settings, f, indent=4)

def load_spam_settings():
    global spam_settings
    if os.path.exists(SPAM_SETTINGS_FILE):
        try:
            with open(SPAM_SETTINGS_FILE, 'r') as f:
                spam_settings.update(json.load(f))
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {SPAM_SETTINGS_FILE}.")

def save_domain_blacklist():
    with open(DOMAIN_BLACKLIST_FILE, 'w') as f:
        json.dump(list(blacklisted_domains), f)

def load_domain_blacklist():
    global blacklisted_domains
    if os.path.exists(DOMAIN_BLACKLIST_FILE):
        try:
            with open(DOMAIN_BLACKLIST_FILE, 'r') as f:
                blacklisted_domains = set(json.load(f))
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {DOMAIN_BLACKLIST_FILE}.")

def save_anti_nuke_settings():
    with open(ANTI_NUKE_SETTINGS_FILE, 'w') as f:
        json.dump(anti_nuke_settings, f, indent=4)

def load_anti_nuke_settings():
    global anti_nuke_settings
    if os.path.exists(ANTI_NUKE_SETTINGS_FILE):
        try:
            with open(ANTI_NUKE_SETTINGS_FILE, 'r') as f:
                anti_nuke_settings.update(json.load(f))
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {ANTI_NUKE_SETTINGS_FILE}.")

def save_invites_data():
    # Convert defaultdicts to regular dicts for JSON serialization
    regular_invites_data = {
        str(guild_id): {
            str(user_id): stats for user_id, stats in users.items()
        } for guild_id, users in invites_data.items()
    }
    regular_invite_map = {
        str(guild_id): {
            str(invited_id): inviter_id for invited_id, inviter_id in mapping.items()
        } for guild_id, mapping in invite_map.items()
    }
    with open(INVITES_FILE, 'w') as f:
        json.dump({'invites_data': regular_invites_data, 'invite_map': regular_invite_map}, f, indent=4)

def load_invites_data():
    global invites_data, invite_map
    if os.path.exists(INVITES_FILE):
        try:
            with open(INVITES_FILE, 'r') as f:
                data = json.load(f)
                
                loaded_data = data.get('invites_data', {})
                for guild_id_str, users in loaded_data.items():
                    for user_id_str, stats in users.items():
                        invites_data[int(guild_id_str)][int(user_id_str)] = stats
                        
                loaded_map = data.get('invite_map', {})
                for guild_id_str, mapping in loaded_map.items():
                    for invited_id_str, inviter_id in mapping.items():
                        invite_map[int(guild_id_str)][int(invited_id_str)] = inviter_id

        except (json.JSONDecodeError, TypeError, KeyError) as e:
            print(f"Warning: Could not load or parse {INVITES_FILE}. Error: {e}")

def save_invite_leaderboard_config():
    with open(INVITE_LEADERBOARD_FILE, 'w') as f:
        json.dump(invite_leaderboard_config, f, indent=4)

def load_invite_leaderboard_config():
    global invite_leaderboard_config
    if os.path.exists(INVITE_LEADERBOARD_FILE):
        try:
            with open(INVITE_LEADERBOARD_FILE, 'r') as f:
                data = json.load(f)
                invite_leaderboard_config = {int(k): v for k, v in data.items()}
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {INVITE_LEADERBOARD_FILE}.")

def save_global_bans():
    with open(GLOBAL_BANS_FILE, 'w') as f:
        json.dump(globally_banned_users, f, indent=4)

def load_global_bans():
    global globally_banned_users
    if os.path.exists(GLOBAL_BANS_FILE):
        try:
            with open(GLOBAL_BANS_FILE, 'r') as f:
                globally_banned_users = json.load(f)
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {GLOBAL_BANS_FILE}.")

def save_bot_announcement_channels():
    with open(BOT_ANNOUNCEMENT_CHANNELS_FILE, 'w') as f:
        # Convert int keys to str for JSON
        json.dump({str(k): v for k, v in bot_announcement_channels.items()}, f, indent=4)

def load_bot_announcement_channels():
    global bot_announcement_channels
    if os.path.exists(BOT_ANNOUNCEMENT_CHANNELS_FILE):
        try:
            with open(BOT_ANNOUNCEMENT_CHANNELS_FILE, 'r') as f:
                data = json.load(f)
                # Convert str keys back to int
                bot_announcement_channels = {int(k): v for k, v in data.items()}
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {BOT_ANNOUNCEMENT_CHANNELS_FILE}.")

def save_ticket_categories():
    with open(TICKET_CATEGORIES_FILE, 'w') as f:
        json.dump(ticket_categories, f, indent=4)

def load_ticket_categories():
    global ticket_categories
    if os.path.exists(TICKET_CATEGORIES_FILE):
        try:
            with open(TICKET_CATEGORIES_FILE, 'r') as f:
                data = json.load(f)
                # Convert string keys from JSON back to integers for guild IDs
                loaded_data = {int(k): v for k, v in data.items()}
                ticket_categories = defaultdict(list, loaded_data)
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {TICKET_CATEGORIES_FILE}.")

def save_suggestions_channel():
    with open(SUGGESTIONS_CHANNEL_FILE, 'w') as f:
        json.dump({'suggestions_channel_id': suggestions_channel_id}, f)

def load_suggestions_channel():
    global suggestions_channel_id
    if os.path.exists(SUGGESTIONS_CHANNEL_FILE):
        try:
            with open(SUGGESTIONS_CHANNEL_FILE, 'r') as f:
                data = json.load(f)
                suggestions_channel_id = data.get('suggestions_channel_id')
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {SUGGESTIONS_CHANNEL_FILE}.")

def save_ticket_logs_channel():
    with open(TICKET_LOGS_FILE, 'w') as f:
        json.dump({'ticket_logs_channel_id': ticket_logs_channel_id}, f)

def load_ticket_logs_channel():
    global ticket_logs_channel_id
    if os.path.exists(TICKET_LOGS_FILE):
        try:
            with open(TICKET_LOGS_FILE, 'r') as f:
                data = json.load(f)
                ticket_logs_channel_id = data.get('ticket_logs_channel_id')
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {TICKET_LOGS_FILE}.")

def save_ticket_counters():
    with open(TICKET_COUNTERS_FILE, 'w') as f:
        json.dump(ticket_counters, f, indent=4)

def load_ticket_counters():
    global ticket_counters
    if os.path.exists(TICKET_COUNTERS_FILE):
        try:
            with open(TICKET_COUNTERS_FILE, 'r') as f:
                data = json.load(f)
                # Ensure all keys exist, defaulting to 0 if not in file
                for key in ticket_counters:
                    ticket_counters[key] = data.get(key, 0)
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {TICKET_COUNTERS_FILE}.")

def save_support_channels():
    with open(SUPPORT_CHANNELS_FILE, 'w') as f:
        json.dump(support_channels, f, indent=4)

def load_support_channels():
    global support_channels
    if os.path.exists(SUPPORT_CHANNELS_FILE):
        try:
            with open(SUPPORT_CHANNELS_FILE, 'r') as f:
                data = json.load(f)
                support_channels = {int(k): v for k, v in data.items()}
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {SUPPORT_CHANNELS_FILE}.")

def save_verification_config():
    with open(VERIFICATION_FILE, 'w') as f:
        json.dump({str(k): v for k, v in verification_config.items()}, f, indent=4)

def load_verification_config():
    global verification_config
    if os.path.exists(VERIFICATION_FILE):
        try:
            with open(VERIFICATION_FILE, 'r') as f:
                data = json.load(f)
                verification_config = {int(k): v for k, v in data.items()}
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not load or parse {VERIFICATION_FILE}.")


# ----------------- HELPER FUNCTIONS -----------------
async def send_log(guild, channel_key, embed):
    channel_id = log_channels.get(channel_key)
    if channel_id:
        log_channel = guild.get_channel(channel_id)
        if log_channel:
            # Add robust error handling for permissions issues
            try:
                await log_channel.send(embed=embed)
            except discord.Forbidden:
                print(f"ERROR: Missing Permissions to send log in #{log_channel.name} ({log_channel.id}).")
                print("Please ensure the bot has 'View Channel' and 'Send Messages' permissions in the log channel and its category.")
            except Exception as e:
                print(f"An unexpected error occurred while sending a log message to channel {channel_id}: {e}")
        else:
            print(f"Log channel not found for key '{channel_key}' with ID {channel_id}. It might have been deleted.")

def get_progress_bar(percentage: float, length: int = 20) -> str:
    """Create a beautiful progress bar with Unicode characters."""
    filled = int(length * percentage / 100)
    empty = length - filled
    
    # Beautiful Unicode progress bar characters
    bar = "█" * filled + "░" * empty
    return f"[{bar}] {percentage:.1f}%"

def get_size_format(bytes_size: int) -> str:
    """Convert bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"

async def get_host_stats_embed() -> discord.Embed:
    """Generate a beautiful host statistics embed."""
    if not PSUTIL_AVAILABLE:
        error_embed = discord.Embed(
            title="❌ Host Statistics Unavailable",
            description="The `psutil` module is not installed. Please install it with:\n```\npip install psutil\n```",
            color=discord.Color.red()
        )
        return error_embed
    
    try:
        # System Information
        system_info = platform.uname()
        hostname = socket.gethostname()
        
        # Get IP Address
        try:
            # Get local IP address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            local_ip = "Unable to detect"
        
        # CPU Information
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count(logical=False)
        cpu_count_logical = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq()
        
        # Memory Information
        memory = psutil.virtual_memory()
        memory_used = memory.used
        memory_total = memory.total
        memory_percent = memory.percent
        
        # Disk Information
        disk = psutil.disk_usage('/')
        disk_used = disk.used
        disk_total = disk.total
        disk_percent = (disk_used / disk_total) * 100
        
        # Network Information
        network = psutil.net_io_counters()
        bytes_sent = network.bytes_sent
        bytes_recv = network.bytes_recv
        
        # Boot time
        boot_time = psutil.boot_time()
        boot_time_dt = datetime.datetime.fromtimestamp(boot_time, tz=datetime.timezone.utc)
        
        # Create beautiful embed
        embed = discord.Embed(
            title="🖥️ Host System Statistics",
            description="Real-time server performance metrics",
            color=discord.Color.from_rgb(0, 255, 127),  # Spring green
            timestamp=discord.utils.utcnow()
        )
        
        # System Info Field
        system_value = (
            f"**OS:** {system_info.system} {system_info.release}\n"
            f"**Hostname:** `{hostname}`\n"
            f"**IP Address:** `{local_ip}`\n"
            f"**Architecture:** {system_info.machine}\n"
            f"**Boot Time:** {discord.utils.format_dt(boot_time_dt, style='R')}"
        )
        embed.add_field(name="💻 System Information", value=system_value, inline=False)
        
        # CPU Field with progress bar
        cpu_bar = get_progress_bar(cpu_percent)
        cpu_color = "🟢" if cpu_percent < 50 else "🟡" if cpu_percent < 80 else "🔴"
        cpu_value = (
            f"{cpu_color} **Usage:** {cpu_bar}\n"
            f"**Cores:** {cpu_count} Physical, {cpu_count_logical} Logical\n"
        )
        if cpu_freq:
            cpu_value += f"**Frequency:** {cpu_freq.current:.0f} MHz"
        embed.add_field(name="⚡ CPU Performance", value=cpu_value, inline=True)
        
        # Memory Field with progress bar
        memory_bar = get_progress_bar(memory_percent)
        memory_color = "🟢" if memory_percent < 60 else "🟡" if memory_percent < 85 else "🔴"
        memory_value = (
            f"{memory_color} **Usage:** {memory_bar}\n"
            f"**Used:** {get_size_format(memory_used)}\n"
            f"**Total:** {get_size_format(memory_total)}"
        )
        embed.add_field(name="🧠 Memory Usage", value=memory_value, inline=True)
        
        # Disk Field with progress bar
        disk_bar = get_progress_bar(disk_percent)
        disk_color = "🟢" if disk_percent < 70 else "🟡" if disk_percent < 90 else "🔴"
        disk_value = (
            f"{disk_color} **Usage:** {disk_bar}\n"
            f"**Used:** {get_size_format(disk_used)}\n"
            f"**Total:** {get_size_format(disk_total)}"
        )
        embed.add_field(name="💾 Disk Usage", value=disk_value, inline=True)
        
        # Network Field
        network_value = (
            f"📤 **Sent:** {get_size_format(bytes_sent)}\n"
            f"📥 **Received:** {get_size_format(bytes_recv)}\n"
            f"📊 **Total:** {get_size_format(bytes_sent + bytes_recv)}"
        )
        embed.add_field(name="🌐 Network Statistics", value=network_value, inline=True)
        
        # Process Information
        process_count = len(psutil.pids())
        embed.add_field(name="🔧 Process Count", value=f"**Active Processes:** {process_count}", inline=True)
        
        # Bot specific info
        bot_process = psutil.Process()
        bot_memory = bot_process.memory_info()
        bot_cpu = bot_process.cpu_percent()
        
        bot_value = (
            f"**CPU:** {bot_cpu:.1f}%\n"
            f"**Memory:** {get_size_format(bot_memory.rss)}\n"
            f"**Threads:** {bot_process.num_threads()}"
        )
        embed.add_field(name="🤖 Bot Performance", value=bot_value, inline=True)
        
        # Footer with beautiful styling
        embed.set_footer(
            text="📈 Statistics updated in real-time • Powered by psutil",
            icon_url="https://cdn.discordapp.com/emojis/741090906693935185.png"
        )
        
        return embed
        
    except Exception as e:
        # Fallback embed in case of error
        error_embed = discord.Embed(
            title="❌ Host Statistics Error",
            description=f"Could not retrieve system statistics: {str(e)}",
            color=discord.Color.red()
        )
        return error_embed

def check_anti_nuke_violation(user_id: int, action_type: str) -> bool:
    """Check if a user has exceeded anti-nuke limits for a specific action."""
    if not anti_nuke_settings.get('enabled', False):
        return False
    
    if user_id in whitelisted_users:
        return False
    
    if action_type not in ANTI_NUKE_ACTIONS:
        return False
    
    limit_key = ANTI_NUKE_ACTIONS[action_type]
    max_actions = anti_nuke_settings.get(limit_key, 999)
    
    current_time = time.time()
    minute_ago = current_time - 60
    
    # Clean old timestamps
    user_actions[user_id][action_type] = [
        timestamp for timestamp in user_actions[user_id][action_type] 
        if timestamp > minute_ago
    ]
    
    # Add current action
    user_actions[user_id][action_type].append(current_time)
    
    # Check if limit exceeded
    return len(user_actions[user_id][action_type]) > max_actions

async def handle_anti_nuke_violation(guild: discord.Guild, user: discord.Member, action_type: str, target_name: str = None):
    """Handle anti-nuke violation by taking appropriate action."""
    try:
        action_verb = "banned" if anti_nuke_settings.get('auto_ban', False) else "kicked"
        
        if anti_nuke_settings.get('auto_ban', False):
            await user.ban(reason=f"Anti-nuke: Exceeded {action_type} limit")
        else:
            await user.kick(reason=f"Anti-nuke: Exceeded {action_type} limit")
        
        embed = discord.Embed(
            title="🚨 ANTI-NUKE ACTION 🚨",
            description=f"User **{user.mention}** was **{action_verb}** for exceeding {action_type} limits.",
            color=discord.Color.dark_red()
        )
        embed.add_field(name="Action Type", value=action_type.replace('_', ' ').title(), inline=True)
        embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
        if target_name:
            embed.add_field(name="Target", value=target_name, inline=True)
        embed.timestamp = discord.utils.utcnow()
        
        await send_log(guild, "security", embed)
        
    except discord.Forbidden:
        embed = discord.Embed(
            title="🚨 ANTI-NUKE FAILED 🚨",
            description=f"Could not {action_verb} **{user.mention}** - insufficient permissions.",
            color=discord.Color.red()
        )
        embed.add_field(name="Action Type", value=action_type.replace('_', ' ').title(), inline=True)
        embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
        await send_log(guild, "security", embed)
    except Exception as e:
        print(f"Anti-nuke error: {e}")


async def get_userinfo_embed(user: discord.Member | discord.User, requester: discord.User = None):
    # Use the user's top role color for the embed, or a default purple if not available.
    color = user.color if isinstance(user, discord.Member) and user.color != discord.Color.default() else discord.Color.purple()

    embed = discord.Embed(description=f"Information for {user.mention}", color=color)

    embed.set_author(name=str(user), icon_url=user.display_avatar.url)
    embed.set_thumbnail(url=user.display_avatar.url)

    # Main details
    embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
    embed.add_field(name="Is Bot?", value="✅ Yes" if user.bot else "❌ No", inline=True)

    # Display status and activity if it's a member
    if isinstance(user, discord.Member):
        if user.status != discord.Status.offline:
            # Add a status emoji
            status_emoji = {
                discord.Status.online: "🟢 Online",
                discord.Status.idle: "🟡 Idle",
                discord.Status.dnd: "🔴 Do Not Disturb",
            }.get(user.status, "⚫ Offline")
            embed.add_field(name="Status", value=status_emoji, inline=True)

        if user.activity:
            try:
                activity_type = user.activity.type.name.replace("_", " ").title()
                embed.add_field(name="Activity", value=f"**{activity_type}:** {user.activity.name}", inline=False)
            except:
                 pass # Some custom activities might not have a name

    # Timestamps
    embed.add_field(
        name="Account Created",
        value=f"{discord.utils.format_dt(user.created_at, style='F')} ({discord.utils.format_dt(user.created_at, style='R')})",
        inline=False
    )
    if isinstance(user, discord.Member) and user.joined_at:
        embed.add_field(
            name="Joined Server",
            value=f"{discord.utils.format_dt(user.joined_at, style='F')} ({discord.utils.format_dt(user.joined_at, style='R')})",
            inline=False
        )

    # Roles
    if isinstance(user, discord.Member):
        # Reversed so highest roles appear first
        roles = [role.mention for role in reversed(user.roles) if role.name != "@everyone"]
        role_count = len(roles)
        roles_str = ", ".join(roles) if roles else "No Roles"

        # Discord embed fields have a 1024 character limit.
        if len(roles_str) > 1024:
            roles_str = roles_str[:1020] + "..."

        embed.add_field(name=f"Roles [{role_count}]", value=roles_str, inline=False)
        embed.add_field(name="Highest Role", value=user.top_role.mention, inline=True)
        embed.add_field(name="Administrator?", value="✅ Yes" if user.guild_permissions.administrator else "❌ No", inline=True)

    # User Banner
    # Fetch user object to get banner, as it's not always on the member object
    try:
        # Check if we need to fetch the user object. Member objects sometimes don't have banner.
        user_obj = user
        if not getattr(user, 'banner', None):
           user_obj = await bot.fetch_user(user.id)
        if user_obj.banner:
            embed.set_image(url=user_obj.banner.url)
    except Exception as e:
        print(f"Could not fetch user banner for {user.id}: {e}")

    if requester:
        embed.set_footer(text=f"Requested by {requester.display_name}", icon_url=requester.display_avatar.url)

    return embed

async def _update_leaderboard_message(guild: discord.Guild):
    """Fetches data and updates the leaderboard message for a specific guild."""
    config = invite_leaderboard_config.get(guild.id)
    if not guild or not config:
        return

    try:
        channel = guild.get_channel(config['channel_id'])
        if not channel:
            print(f"Leaderboard channel {config['channel_id']} not found for guild {guild.id}. Removing from config.")
            del invite_leaderboard_config[guild.id]
            save_invite_leaderboard_config()
            return

        message = await channel.fetch_message(config['message_id'])
        if not message:
            print(f"Leaderboard message {config['message_id']} not found for guild {guild.id}. Removing from config.")
            del invite_leaderboard_config[guild.id]
            save_invite_leaderboard_config()
            return

        guild_invites_stats = invites_data.get(guild.id, {})
        sorted_inviters = sorted(
            guild_invites_stats.items(),
            key=lambda item: item[1].get('regular', 0),
            reverse=True
        )

        embed = discord.Embed(
            title=f"🏆 Invite Leaderboard for {guild.name}",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )

        description_lines = []
        rank_emojis = {1: "🥇", 2: "🥈", 3: "🥉"}

        for i, (user_id, stats) in enumerate(sorted_inviters[:10], 1):
            # Ensure user_id is an integer for lookup
            user = guild.get_member(int(user_id))
            user_display = user.mention if user else f"User ID: {user_id}"

            regular = stats.get('regular', 0)
            left = stats.get('left', 0)
            total = regular + left

            rank = rank_emojis.get(i, f"`#{i}`")

            description_lines.append(
                f"{rank} **{user_display}** - **{regular}** invites (`{total}` total, `{left}` left)"
            )

        if not description_lines:
            embed.description = "No one has any invites yet. Start inviting people!"
        else:
            embed.description = "\n".join(description_lines)

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text="Updates automatically every 1 minute.")

        await message.edit(embed=embed)

    except discord.NotFound:
        print(f"Leaderboard channel or message not found for guild {guild.id}. Removing from config.")
        if guild.id in invite_leaderboard_config:
            del invite_leaderboard_config[guild.id]
            save_invite_leaderboard_config()
    except discord.Forbidden:
        print(f"Missing permissions to edit leaderboard message in guild {guild.id}.")
    except Exception as e:
        print(f"Error updating leaderboard for guild {guild.id}: {e}")

async def _update_status_channels(guild: discord.Guild):
    """Helper function to update the Aether logs voice channels."""
    if not guild:
        return # Not in a guild, do nothing.

    # Fetch stats
    total_members = guild.member_count
    online_members = sum(1 for m in guild.members if m.status != discord.Status.offline)
    boosts = guild.premium_subscription_count
    total_roles = len(guild.roles) - 1  # Exclude @everyone role
    total_channels = len(guild.channels)

    # Channel Names
    channel_names = {
        "total": f"� MEMOBERS: {total_members}",
        "online": f"🟢 ONLINE: {online_members}",
        "boosts": f"🚀 BOOSTS: {boosts}",
        "roles": f"🎭 ROLES: {total_roles}",
        "channels": f"📺 CHANNELS: {total_channels}"
    }

    # Update channels
    for key, name in channel_names.items():
        channel_id = status_channels.get(key)
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    if channel.name != name:
                        await channel.edit(name=name, reason="Automated status update")
                except Exception as e:
                    print(f"Failed to update status channel {channel.id}: {e}")
            else:
                print(f"Status channel with ID {channel_id} for key '{key}' not found.")

async def _create_backup_file(guild: discord.Guild) -> discord.File:
    """Generates a backup file for the given guild."""
    backup_data = {
        "guild_id": guild.id,
        "guild_name": guild.name,
        "roles": [],
        "categories": []
    }

    # Backup Roles
    for role in sorted(guild.roles, key=lambda r: r.position):
        backup_data["roles"].append({
            "name": role.name,
            "permissions": role.permissions.value,
            "color": role.color.value,
            "hoist": role.hoist,
            "mentionable": role.mentionable,
            "is_everyone": role.is_default(),
            "is_bot_role": role.is_bot_managed()
        })

    # Backup Channels
    for category, channels in guild.by_category():
        if category is not None:
            cat_data = {
                "name": category.name,
                "position": category.position,
                "overwrites": [],
                "channels": []
            }
            for target, overwrite in category.overwrites.items():
                if isinstance(target, discord.Role):
                    allow, deny = overwrite.pair()
                    cat_data["overwrites"].append({
                        "role_name": target.name,
                        "allow": allow.value,
                        "deny": deny.value
                    })
            
            for channel in sorted(channels, key=lambda c: c.position):
                chan_data = {
                    "name": channel.name,
                    "type": str(channel.type),
                    "position": channel.position,
                    "topic": getattr(channel, 'topic', None),
                    "overwrites": []
                }
                for target, overwrite in channel.overwrites.items():
                    if isinstance(target, discord.Role):
                        allow, deny = overwrite.pair()
                        chan_data["overwrites"].append({
                            "role_name": target.name,
                            "allow": allow.value,
                            "deny": deny.value
                        })
                cat_data["channels"].append(chan_data)
            backup_data["categories"].append(cat_data)

    backup_json = json.dumps(backup_data, indent=4)
    return discord.File(io.StringIO(backup_json), filename=f"backup-{guild.id}-{int(time.time())}.json")

# ----------------- AI CHAT HELPERS -----------------
async def _start_ai_chat_logic(interaction: Interaction):
    """The core logic for starting an AI chat session."""
    if not GEMINI_API_KEY:
        await interaction.response.send_message("The AI feature is not configured. An administrator must set an API key first.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        thread_name = f"AI Chat - {interaction.user.display_name}"
        if not isinstance(interaction.channel, (discord.TextChannel, discord.ForumChannel)):
             await interaction.followup.send("AI Chats can only be started in regular text channels.", ephemeral=True)
             return

        thread = await interaction.channel.create_thread(
            name=thread_name,
            auto_archive_duration=60,
            type=discord.ChannelType.private_thread,
            reason=f"AI Chat for {interaction.user.name}"
        )
        
        # Add the user who started the chat to the thread so they can see it.
        await thread.add_user(interaction.user)
        
        model = genai.GenerativeModel('gemini-2.5-flash')
        chat_session = model.start_chat(history=[])
        active_ai_chats[thread.id] = chat_session

        welcome_embed = discord.Embed(
            title="🤖 Gemini AI Chat",
            description=f"Hello {interaction.user.mention}! I'm ready to assist you. Ask me anything!",
            color=discord.Color.purple()
        )
        welcome_embed.add_field(
            name="How it works",
            value="Just type your message below. I'll remember our conversation in this thread.",
            inline=False
        )
        welcome_embed.add_field(
            name="Session Timeout",
            value="This private chat will automatically archive after **60 minutes** of inactivity.",
            inline=False
        )
        welcome_embed.set_footer(text="Your privacy is respected. This chat is only visible to you and server staff.")
        
        await thread.send(embed=welcome_embed, view=AIChatActionsView())
        await interaction.followup.send(f"Your private AI chat has been created: {thread.mention}", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send("I don't have permission to create a thread or add members to it. Please check my permissions.", ephemeral=True)
    except Exception as e:
        print(f"Error starting AI chat: {e}")
        await interaction.followup.send(f"An unexpected error occurred while starting the chat: {e}", ephemeral=True)

# ----------------- UI VIEWS (BUTTONS) -----------------
class ConfirmCloseAIView(ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @ui.button(label="Confirm Close", style=ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: Interaction, button: ui.Button):
        thread_id = interaction.channel.id
        if thread_id in active_ai_chats:
            del active_ai_chats[thread_id]
            print(f"Cleaned up AI chat session for closed thread {thread_id}")
        # This will fail if the channel is already deleted, which is fine.
        try:
            await interaction.channel.delete(reason=f"AI Chat closed by {interaction.user}")
        except discord.NotFound:
            pass # Channel was already deleted, no action needed.
        except Exception as e:
            print(f"Error deleting AI thread {thread_id}: {e}")


    @ui.button(label="Cancel", style=ButtonStyle.secondary)
    async def cancel(self, interaction: Interaction, button: ui.Button):
        await interaction.message.delete()
        await interaction.response.send_message("Closure cancelled.", ephemeral=True, delete_after=5)

class AIChatActionsView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Close Chat", style=ButtonStyle.danger, emoji="🔒", custom_id="close_ai_chat")
    async def close_chat(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_message(
            "Are you sure you want to close and delete this AI chat thread?",
            view=ConfirmCloseAIView(),
            ephemeral=True
        )

class AIStartChatOnlyView(ui.View):
    """A view that ONLY shows the 'Start AI Chat' button."""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Start AI Chat", style=ButtonStyle.primary, emoji="💬", custom_id="start_ai_chat_direct")
    async def start_chat(self, interaction: Interaction, button: ui.Button):
        await _start_ai_chat_logic(interaction)

class APIKeyModal(ui.Modal, title='Set Gemini API Key'):
    api_key = ui.TextInput(
        label='Google Gemini API Key',
        placeholder='Enter your API key here...',
        style=discord.TextStyle.short,
        required=True
    )

    async def on_submit(self, interaction: Interaction):
        global GEMINI_API_KEY
        GEMINI_API_KEY = self.api_key.value
        save_gemini_key()
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            
            # Create the new "key is set" panel
            ready_embed = discord.Embed(
                title="🤖 AI Chat Hub",
                description=(
                    "Welcome to the AI Chat Hub! The bot is configured and ready for conversations.\n\n"
                    "Click the **`Start AI Chat`** button to open a private thread with the Gemini AI."
                ),
                color=discord.Color.green()
            )
            ready_embed.add_field(name="How does it work?", value="A new, private thread will be created for your conversation. It's only visible to you and server staff.", inline=False)
            ready_embed.set_footer(text="Powered by Google Gemini.")
            
            # Edit the original panel message to remove the "Set Key" button
            await interaction.message.edit(embed=ready_embed, view=AIStartChatOnlyView())
            
            await interaction.response.send_message('✅ Gemini API key has been set and verified successfully!', ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f'❌ An error occurred while configuring the API key: {e}', ephemeral=True)

class AISetupView(ui.View):
    """The initial AI setup view with both buttons."""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Set API Key", style=ButtonStyle.danger, emoji="🔑", custom_id="set_api_key")
    async def set_key(self, interaction: Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You must be an administrator to set the API key.", ephemeral=True)
            return
        await interaction.response.send_modal(APIKeyModal())

    @ui.button(label="Start AI Chat", style=ButtonStyle.primary, emoji="💬", custom_id="start_ai_chat_from_setup")
    async def start_chat(self, interaction: Interaction, button: ui.Button):
        await _start_ai_chat_logic(interaction)


async def get_ticket_owner_user(channel, guild: discord.Guild):
    """Resolve the ticket opener: member-specific overwrites first, then embed User ID."""
    sources = [channel]
    if isinstance(channel, discord.Thread) and channel.parent:
        sources.append(channel.parent)
    for source in sources:
        try:
            for target, _ow in source.overwrites.items():
                if isinstance(target, discord.Member) and not target.bot:
                    return target
        except Exception:
            pass
    try:
        async for msg in channel.history(limit=50, oldest_first=True):
            for emb in msg.embeds:
                for f in emb.fields:
                    if f.name and f.name.strip() == "User ID":
                        digits = re.sub(r"\D", "", f.value or "")
                        if digits:
                            uid = int(digits)
                            m = guild.get_member(uid)
                            if m:
                                return m
                            try:
                                return await bot.fetch_user(uid)
                            except discord.NotFound:
                                return None
    except Exception:
        pass
    return None


class TicketFeedbackModal(ui.Modal, title="Ticket feedback"):
    def __init__(self, rating: int, guild_id: int, guild_name: str):
        super().__init__()
        self.rating = rating
        self.guild_id = guild_id
        self.guild_name = guild_name
        self.feedback_input = ui.TextInput(
            label="Your feedback",
            style=discord.TextStyle.paragraph,
            placeholder="How was your experience? (optional)",
            required=False,
            max_length=2000,
        )
        self.add_item(self.feedback_input)

    async def on_submit(self, interaction: Interaction):
        use_ephemeral = interaction.guild is not None
        await interaction.response.send_message(
            "Thank you for your feedback!", ephemeral=use_ephemeral
        )
        text = (self.feedback_input.value or "").strip()
        stars = "⭐" * self.rating
        log_ch = bot.get_channel(ticket_logs_channel_id) if ticket_logs_channel_id else None
        if log_ch and isinstance(log_ch, discord.TextChannel):
            log_embed = discord.Embed(
                title="Ticket feedback received",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow(),
            )
            log_embed.add_field(name="Rating", value=f"{stars} ({self.rating}/5)", inline=True)
            log_embed.add_field(name="Server", value=self.guild_name or f"`{self.guild_id}`", inline=True)
            log_embed.add_field(name="From", value=f"{interaction.user} ({interaction.user.id})", inline=False)
            if text:
                log_embed.add_field(name="Message", value=text[:1024] or "—", inline=False)
            try:
                await log_ch.send(embed=log_embed)
            except Exception as e:
                print(f"Could not post ticket feedback to logs channel: {e}")

        # Also post feedback to the dedicated feedback channel.
        feedback_channel = bot.get_channel(TICKET_FEEDBACK_CHANNEL_ID)
        if feedback_channel is None:
            try:
                feedback_channel = await bot.fetch_channel(TICKET_FEEDBACK_CHANNEL_ID)
            except Exception:
                feedback_channel = None

        if feedback_channel and hasattr(feedback_channel, "send"):
            feedback_embed = discord.Embed(
                title="New Ticket Feedback",
                color=discord.Color.blurple(),
                timestamp=discord.utils.utcnow(),
            )
            feedback_embed.add_field(name="Stars", value=f"{stars} ({self.rating}/5)", inline=True)
            feedback_embed.add_field(name="User", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
            feedback_embed.add_field(name="Server", value=self.guild_name or f"`{self.guild_id}`", inline=False)
            feedback_embed.add_field(name="Message", value=text if text else "No message provided.", inline=False)
            try:
                await feedback_channel.send(embed=feedback_embed)
            except Exception as e:
                print(f"Could not send feedback embed to fixed channel: {e}")


class TicketRatingSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1 — Poor", value="1", emoji="⭐"),
            discord.SelectOption(label="2", value="2", emoji="⭐"),
            discord.SelectOption(label="3 — Okay", value="3", emoji="⭐"),
            discord.SelectOption(label="4", value="4", emoji="⭐"),
            discord.SelectOption(label="5 — Excellent", value="5", emoji="⭐"),
        ]
        super().__init__(
            placeholder="Rate from 1 to 5 stars…",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_feedback_rating_select",
        )


class StarPickView(ui.View):
    def __init__(self, guild_id: int, guild_name: str):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.guild_name = guild_name
        self.add_item(TicketRatingSelect())

    @ui.button(label="Continue", style=ButtonStyle.primary, row=1)
    async def continue_feedback(self, interaction: Interaction, button: ui.Button):
        select = discord.utils.get(self.children, custom_id="ticket_feedback_rating_select")
        if not select or not select.values:
            await interaction.response.send_message(
                "Please choose a star rating first.",
                ephemeral=interaction.guild is not None,
            )
            return
        rating = int(select.values[0])
        await interaction.response.send_modal(
            TicketFeedbackModal(rating, self.guild_id, self.guild_name)
        )


class TicketFeedbackPanelView(ui.View):
    def __init__(self, guild_id: int, guild_name: str):
        super().__init__(timeout=604800)
        self.guild_id = guild_id
        self.guild_name = guild_name

    @ui.button(label="Leave Feedback", style=ButtonStyle.primary, emoji="✍️")
    async def leave_feedback(self, interaction: Interaction, button: ui.Button):
        use_ephemeral = interaction.guild is not None
        await interaction.response.send_message(
            "Choose **1–5 stars** from the menu, then click **Continue** to write your feedback.",
            view=StarPickView(self.guild_id, self.guild_name),
            ephemeral=use_ephemeral,
        )


class CloseTicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Confirm Close", style=ButtonStyle.danger, emoji="🗑️")
    async def confirm_close(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        channel = interaction.channel
        guild = interaction.guild
        
        ticket_owner = await get_ticket_owner_user(channel, guild)
        if ticket_owner and interaction.user != ticket_owner and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(
                "❌ Only the ticket owner or an administrator can close this ticket.",
                ephemeral=True
            )
            return
        
        # Create transcript before closing
        transcript_messages = []
        try:
            async for message in channel.history(limit=None, oldest_first=True):
                timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                author = f"{message.author.name}#{message.author.discriminator}" if message.author.discriminator != "0" else message.author.name
                content = message.content if message.content else "[No text content]"
                
                if message.attachments:
                    attachments_info = "\n".join([f"  📎 {att.filename} ({att.url})" for att in message.attachments])
                    content += f"\n{attachments_info}"
                if message.embeds:
                    content += f"\n  [Message contains {len(message.embeds)} embed(s)]"
                transcript_messages.append(f"[{timestamp}] {author}: {content}")
        except Exception as e:
            print(f"Error creating transcript: {e}")
        
        # Send transcript to logs channel if configured
        if ticket_logs_channel_id and transcript_messages:
            logs_channel = guild.get_channel(ticket_logs_channel_id)
            if logs_channel:
                transcript_text = "\n".join(transcript_messages)
                transcript_file = discord.File(
                    io.StringIO(transcript_text),
                    filename=f"ticket-{channel.name}-{int(time.time())}.txt"
                )
                transcript_embed = discord.Embed(
                    title="🎫 Ticket Transcript",
                    description=f"**Ticket:** {channel.mention if not isinstance(channel, discord.Thread) else channel.name}\n**Closed by:** {interaction.user.mention}\n**Messages:** {len(transcript_messages)}",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
                if guild.icon:
                    transcript_embed.set_thumbnail(url=guild.icon.url)
                try:
                    await logs_channel.send(embed=transcript_embed, file=transcript_file)
                except Exception as e:
                    print(f"Error sending transcript: {e}")
        
        if ticket_owner:
            fb_embed = discord.Embed(
                title="How was your support?",
                description=(
                    "This ticket has been closed. If you have a moment, use the button below "
                    "to rate your experience and leave a short message."
                ),
                color=discord.Color.blurple(),
            )
            if guild.icon:
                fb_embed.set_thumbnail(url=guild.icon.url)
            fb_embed.set_footer(text=guild.name)
            try:
                await ticket_owner.send(
                    embed=fb_embed,
                    view=TicketFeedbackPanelView(guild.id, guild.name),
                )
            except discord.Forbidden:
                pass
            except Exception as e:
                print(f"Ticket feedback DM failed: {e}")
        
        # Preserve the ticket number from the existing name
        original_name = channel.name or ""
        match = re.search(r"(\d{4})$", original_name)
        ticket_number = match.group(1) if match else "0001"
        closed_name = f"closed-{ticket_number}"
        
        # Hide the ticket owner from the channel
        if ticket_owner and isinstance(ticket_owner, discord.Member):
            try:
                await channel.set_permissions(ticket_owner, view_channel=False, send_messages=False, read_message_history=False)
            except Exception as e:
                print(f"Error hiding ticket owner from channel: {e}")
        
        category_target = guild.get_channel(1504940494277312633)
        try:
            if category_target and isinstance(category_target, discord.CategoryChannel):
                await channel.edit(name=closed_name, category=category_target, reason=f"Ticket closed by {interaction.user}")
            else:
                await channel.edit(name=closed_name, reason=f"Ticket closed by {interaction.user}")
        except Exception as e:
            print(f"Error moving/renaming closed ticket: {e}")
            await interaction.followup.send(
                "❌ Could not move or rename the ticket channel. Please make sure the category exists and I have channel management permissions.",
                ephemeral=True
            )
            return
        
        close_embed = discord.Embed(
            title="Ticket Closed",
            description=f"Ticket channel `{closed_name}` was closed by {interaction.user.mention} and moved to the archive category.",
            color=discord.Color.dark_red()
        )
        await send_log(guild, "moderation", close_embed)
        await interaction.followup.send(
            f"✅ Ticket has been closed and moved to the archive category as `{closed_name}`.",
            ephemeral=True
        )

    @ui.button(label="Cancel", style=ButtonStyle.secondary, emoji="❌")
    async def cancel_close(self, interaction: Interaction, button: ui.Button):
        await interaction.message.delete()
        await interaction.channel.send("Ticket closure has been cancelled.", delete_after=10)

class TicketActions(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.claimed_by = None

    @ui.button(label="Claim Ticket", style=ButtonStyle.success, emoji="🙋", custom_id="claim_ticket")
    async def claim(self, interaction: Interaction, button: ui.Button):
        staff_role = discord.utils.get(interaction.guild.roles, name="Staff")
        if staff_role is None or staff_role not in interaction.user.roles:
            await interaction.response.send_message("Only staff members can claim tickets.", ephemeral=True)
            return

        if self.claimed_by:
            await interaction.response.send_message(f"This ticket has already been claimed by {self.claimed_by.mention}.", ephemeral=True)
            return

        self.claimed_by = interaction.user
        button.disabled = True
        button.label = f"Claimed by {interaction.user.display_name}"

        await interaction.message.edit(view=self)

        claim_embed = discord.Embed(
            description=f"✅ Ticket claimed by {interaction.user.mention}",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=claim_embed)

    @ui.button(label="Close", style=ButtonStyle.danger, emoji="🔒", custom_id="close_ticket")
    async def close(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_message(
            "Are you sure you want to close this ticket? This action cannot be undone.",
            view=CloseTicketView(),
            ephemeral=True
        )

class TicketDropdown(ui.Select):
    def __init__(self):
        # Custom emojis for dropdown
        CUSTOM_EMOJIS = {
            "purchase": "🛍",
            "support": "🏷",
        }
        
        # Predefined ticket categories with custom emojis
        options = [
            discord.SelectOption(
                label="Purchase",
                description="Place An Order",
                emoji=CUSTOM_EMOJIS["purchase"]
            ),
            discord.SelectOption(
                label="Support", 
                description="Ask For Support",
                emoji=CUSTOM_EMOJIS["support"]
            ),
        ]
        super().__init__(
            placeholder="≡ Select a ticket type...", 
            options=options, 
            custom_id="ticket_dropdown"
        )

    async def callback(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        user = interaction.user
        category_name = self.values[0]

        # Check if user already has ANY open ticket channel (limit 1 per user total)
        user_tickets = []
        
        # Check all text channels in the guild for existing tickets
        for channel in guild.text_channels:
            if channel.name.startswith(('💸purchase-', '📞support-', '🎥media-apply-', '💼investor-', '❓report-')):
                overwrites = channel.overwrites_for(user)
                if overwrites.view_channel:
                    user_tickets.append(channel)
        
        # If user has any open ticket, prevent creating a new one
        if user_tickets:
            existing_ticket = user_tickets[0]
            await interaction.followup.send(
                f"❌ **Ticket Limit Reached**\n"
                f"You already have an open ticket: {existing_ticket.mention}\n"
                f"Please close your current ticket before opening a new one.",
                ephemeral=True
            )
            return

        # Create channel name with emoji and counter
        # Format: support📞0001 / purchase💸0001
        category_emojis_for_name = {
            "Purchase": "💸",
            "Support": "📞",
            "Media Apply": "🎥",
            "Investor": "💼",
            "Report": "❓"
        }
        
        category_name_prefix = {
            "Purchase": "purchase",
            "Support": "support",
            "Media Apply": "media-apply",
            "Investor": "investor",
            "Report": "report"
        }
        
        # Map category to counter key
        category_to_counter = {
            "Purchase": "purchase",
            "Support": "support",
            "Media Apply": "media_apply",
            "Investor": "investor"
        }
        
        # Get and increment counter for this ticket type
        counter_key = category_to_counter.get(category_name)
        if counter_key:
            ticket_counters[counter_key] += 1
            counter_num = ticket_counters[counter_key]
            save_ticket_counters()
        else:
            counter_num = 1
        
        # Create channel name without emoji, just name-number format (e.g., support-0001)
        name_prefix = category_name_prefix.get(category_name, "ticket")
        channel_name = f"{name_prefix}-{counter_num:04d}"

        try:
            # Get staff role
            staff_role = discord.utils.get(guild.roles, name="Staff")
            
            # Find the "Active Tickets" category
            support_category = discord.utils.get(guild.categories, name="Active Tickets")
            if not support_category:
                await interaction.followup.send("❌ Could not find the 'Active Tickets' category. Please create it first.", ephemeral=True)
                return
            
            # Set up channel permissions
            overwrites = {
                guild.default_role: PermissionOverwrite(view_channel=False),  # Hide from @everyone
                user: PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),  # Allow ticket creator
                guild.me: PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)  # Allow bot
            }
            
            # Add staff role permissions if it exists
            if staff_role:
                overwrites[staff_role] = PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            
            # Add special role access for support and media tickets
            support_media_role = discord.utils.get(guild.roles, id=1482165881315524688)
            if support_media_role and category_name in ["Support", "Media Apply"]:
                overwrites[support_media_role] = PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            
            # Add administrator permissions
            for role in guild.roles:
                if role.permissions.administrator:
                    overwrites[role] = PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            
            # Create the ticket channel in the Active Tickets category
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                category=support_category,
                reason=f"Ticket created by {user.display_name}"
            )
            
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to create channels. Please contact an administrator.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"An error occurred while creating your ticket: {str(e)}", ephemeral=True)
            return

        # Fixed custom emojis (same as dropdown and setup)
        category_emojis = {
            "Purchase": "💸",
            "Support": "🔖",
            "Media Apply": "🎥",
            "Investor": "💼",
            "Report": "❓"
        }
        
        ticket_embed = discord.Embed(
            title=f"{category_emojis.get(category_name, '🎫')} {category_name}",
            description=(
                f"Welcome, {user.mention}!\n\n"
                "A staff member will be with you shortly. Please describe your issue in detail.\n"
                "To close this ticket, click the 'Close' button below."
            ),
            color=discord.Color.green()
        )
        ticket_embed.add_field(name="Ticket Owner", value=user.mention, inline=True)
        ticket_embed.add_field(name="Type", value=f"{category_emojis.get(category_name, '🎫')} {category_name}", inline=True)
        ticket_embed.add_field(name="Ticket Number", value=f"{category_emojis.get(category_name, '🎫')}-{counter_num:04d}", inline=True)
        ticket_embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)

        if guild.icon:
            ticket_embed.set_footer(text=f"Server: {guild.name}", icon_url=guild.icon.url)
        else:
            ticket_embed.set_footer(text=f"Server: {guild.name}")

        staff_mention = staff_role.mention if staff_role and staff_role.mentionable else ""

        await ticket_channel.send(
            content=f"👋 {user.mention} {staff_mention}",
            embed=ticket_embed,
            view=TicketActions()
        )

        # Init idle tracking for auto-close
        ticket_last_activity[ticket_channel.id] = discord.utils.utcnow()
        ticket_warned_at.pop(ticket_channel.id, None)

        await interaction.followup.send(f"✅ Your {category_name.lower()} ticket channel has been created: {ticket_channel.mention}", ephemeral=True)

class TicketPanel(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())

class CreateTicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Create Ticket", style=ButtonStyle.secondary, emoji=discord.PartialEmoji(name="fusetickets", id=1486309386388508754), custom_id="create_ticket_btn")
    async def create_ticket(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_message(
            "Please select a ticket type:",
            view=TicketPanel(),
            ephemeral=True
        )

class BanListView(ui.View):
    def __init__(self, bans):
        super().__init__(timeout=60)
        for ban in bans:
            self.add_item(BanUserButton(ban.user, ban.reason))

class BanUserButton(ui.Button):
    def __init__(self, user, reason):
        label = f"{user} | ID: {user.id}"
        if reason:
            label += f" | Reason: {reason[:30]}..." if len(reason) > 30 else f" | Reason: {reason}"
        super().__init__(label=label, style=ButtonStyle.gray)
        self.user = user

    async def callback(self, interaction: Interaction):
        await interaction.response.send_message(
            embed=discord.Embed(
                title=f"Unban {self.user}",
                description=f"Username: {self.user}\nID: {self.user.id}",
                color=discord.Color.red()
            ),
            view=UnbanButton(self.user),
            ephemeral=True
        )

class UnbanButton(ui.View):
    def __init__(self, user):
        super().__init__(timeout=30)
        self.user = user

    @ui.button(label="Unban", style=ButtonStyle.green)
    async def unban(self, interaction: Interaction, button: ui.Button):
        try:
            await interaction.guild.unban(self.user)
            await interaction.response.edit_message(content=f"User {self.user} was unbanned.", view=None, embed=None)

            embed = discord.Embed(
                title="User Unbanned",
                description=f"**User:** {self.user} ({self.user.id})\n**Moderator:** {interaction.user.mention}",
                color=discord.Color.green()
            )
            await send_log(interaction.guild, "moderation", embed)

        except Exception as e:
            await interaction.response.edit_message(content=f"Unban failed: {e}", view=None, embed=None)

class AnnouncementModal(ui.Modal, title='Create Server Announcement'):
    announcement_text = ui.TextInput(
        label='Announcement Content',
        placeholder='Type your announcement here... Supports markdown!',
        style=discord.TextStyle.long,
        required=True
    )

    async def on_submit(self, interaction: Interaction):
        announcement_channel = discord.utils.get(interaction.guild.text_channels, name='announcements')
        if not announcement_channel:
            await interaction.response.send_message("❌ **Error:** Could not find a channel named `#announcements`. Please create it first.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📢 Server Announcement",
            description=self.announcement_text.value,
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"From the desk of {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        try:
            await announcement_channel.send(embed=embed)
            await interaction.response.send_message(f"✅ Your announcement has been posted in {announcement_channel.mention}!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"❌ **Error:** I don't have permission to send messages in {announcement_channel.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An unexpected error occurred: {e}", ephemeral=True)

class MemberActionControlView(ui.View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=300)
        self.member = member

    async def interaction_check(self, interaction: Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need to be an administrator to use these controls.", ephemeral=True)
            return False
        return True

    @ui.button(label="Kick", style=ButtonStyle.danger, emoji="👢")
    async def kick_member(self, interaction: Interaction, button: ui.Button):
        try:
            await self.member.kick(reason=f"Kicked by {interaction.user} from Admin Panel.")
            await interaction.response.edit_message(content=f"✅ Successfully kicked {self.member.mention}.", view=None)
        except discord.Forbidden:
            await interaction.response.edit_message(content=f"❌ I don't have permissions to kick {self.member.mention}.", view=None)
        except Exception as e:
            await interaction.response.edit_message(content=f"An error occurred: {e}", view=None)

    @ui.button(label="Ban", style=ButtonStyle.danger, emoji="🔨")
    async def ban_member(self, interaction: Interaction, button: ui.Button):
        try:
            await self.member.ban(reason=f"Banned by {interaction.user} from Admin Panel.")
            await interaction.response.edit_message(content=f"✅ Successfully banned {self.member.mention}.", view=None)
        except discord.Forbidden:
            await interaction.response.edit_message(content=f"❌ I don't have permissions to ban {self.member.mention}.", view=None)
        except Exception as e:
            await interaction.response.edit_message(content=f"An error occurred: {e}", view=None)

    @ui.button(label="Timeout", style=ButtonStyle.secondary, emoji="⏳")
    async def timeout_member(self, interaction: Interaction, button: ui.Button):
        # A simple modal to ask for duration
        class TimeoutModal(ui.Modal, title="Timeout Member"):
            duration = ui.TextInput(label="Duration in minutes", placeholder="e.g., 60 for 1 hour", required=True)
            reason = ui.TextInput(label="Reason", placeholder="Optional reason for the timeout", required=False, style=discord.TextStyle.short)

            async def on_submit(self, modal_interaction: Interaction):
                try:
                    minutes = int(self.duration.value)
                    timeout_duration = timedelta(minutes=minutes)
                    await member.timeout(timeout_duration, reason=self.reason.value or f"Timed out by {modal_interaction.user}")
                    await modal_interaction.response.send_message(f"✅ Successfully timed out {member.mention} for {minutes} minutes.", ephemeral=True)
                except ValueError:
                    await modal_interaction.response.send_message("Invalid duration. Please enter a number.", ephemeral=True)
                except Exception as e:
                    await modal_interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

        member = self.member
        await interaction.response.send_modal(TimeoutModal())

class MemberSelectView(ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @ui.select(cls=ui.UserSelect, placeholder="Select a member to manage...")
    async def select_user(self, interaction: Interaction, select: ui.UserSelect):
        member = select.values[0]
        if not member or not isinstance(member, discord.Member):
            await interaction.response.send_message("Could not fetch member details. They might have left the server.", ephemeral=True)
            return

        embed = await get_userinfo_embed(member, interaction.user)
        embed.title = f"Managing Member: {member.display_name}"
        await interaction.response.send_message(
            embed=embed,
            view=MemberActionControlView(member),
            ephemeral=True
        )
        # Clear the original select message
        await interaction.edit_original_response(content="Member selected. See the new message below.", view=None)

# --- SECURITY UI & MODALS ---

class SpamSettingsModal(ui.Modal, title="Configure Anti-Spam"):
    enabled = ui.TextInput(label="Enable Anti-Spam (true/false)", default=str(spam_settings['enabled']).lower(), min_length=4, max_length=5)
    message_count = ui.TextInput(label="Message Count", default=str(spam_settings['message_count']), placeholder="e.g., 7")
    time_window = ui.TextInput(label="Time Window (seconds)", default=str(spam_settings['time_window']), placeholder="e.g., 5")
    action = ui.TextInput(label="Action (warn/timeout)", default=spam_settings['action'], placeholder="warn or timeout")
    timeout_duration = ui.TextInput(label="Timeout Duration (minutes)", default=str(spam_settings['timeout_duration']), placeholder="e.g., 10")

    async def on_submit(self, interaction: Interaction):
        try:
            spam_settings['enabled'] = self.enabled.value.lower() == 'true'
            spam_settings['message_count'] = int(self.message_count.value)
            spam_settings['time_window'] = int(self.time_window.value)
            action_val = self.action.value.lower()
            if action_val not in ['warn', 'timeout']:
                raise ValueError("Action must be 'warn' or 'timeout'")
            spam_settings['action'] = action_val
            spam_settings['timeout_duration'] = int(self.timeout_duration.value)
            save_spam_settings()
            await interaction.response.send_message("✅ Anti-Spam settings updated successfully!", ephemeral=True)
        except ValueError as e:
            await interaction.response.send_message(f"❌ Invalid input: {e}. Please use correct formats (e.g., numbers for counts).", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An unexpected error occurred: {e}", ephemeral=True)

class AddDomainModal(ui.Modal, title="Add Blacklisted Domain"):
    domain = ui.TextInput(label="Domain to blacklist", placeholder="e.g., example.com", required=True)

class SetupImplementationView(ui.View):
    def __init__(self, setup_plan: str, guild: discord.Guild):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.setup_plan = setup_plan
        self.guild = guild
    
    @ui.button(label="✅ Εφαρμογή", style=ButtonStyle.success)
    async def implement_button(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Parse the AI response and create everything
            result = await self.implement_setup(interaction)
            
            # Disable buttons after implementation
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
            
            await interaction.followup.send(result, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Error implementing setup: {str(e)}", ephemeral=True)
    
    @ui.button(label="❌ Ακύρωση", style=ButtonStyle.danger)
    async def cancel_button(self, interaction: Interaction, button: ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("❌ Setup cancelled.", ephemeral=True)
    
    async def implement_setup(self, interaction: Interaction):
        """Parse AI response and create roles, categories, and channels"""
        guild = self.guild
        created_items = {"roles": [], "categories": [], "channels": []}
        
        # Extract roles with colors
        roles_to_create = self.parse_roles(self.setup_plan)
        for role_data in roles_to_create:
            try:
                role = await guild.create_role(
                    name=role_data['name'],
                    color=role_data['color'],
                    reason="AI Discord Setup"
                )
                created_items['roles'].append(role.name)
            except Exception as e:
                print(f"Error creating role {role_data['name']}: {e}")
        
        # Extract and create categories with channels
        categories_data = self.parse_categories_and_channels(self.setup_plan)
        for cat_data in categories_data:
            try:
                category = await guild.create_category(
                    name=cat_data['name'],
                    reason="AI Discord Setup"
                )
                created_items['categories'].append(category.name)
                
                # Create channels in this category
                for channel_data in cat_data['channels']:
                    try:
                        if channel_data['type'] == 'text':
                            channel = await guild.create_text_channel(
                                name=channel_data['name'],
                                category=category,
                                reason="AI Discord Setup"
                            )
                        else:  # voice
                            channel = await guild.create_voice_channel(
                                name=channel_data['name'],
                                category=category,
                                reason="AI Discord Setup"
                            )
                        created_items['channels'].append(f"{channel.name} ({channel_data['type']})")
                    except Exception as e:
                        print(f"Error creating channel {channel_data['name']}: {e}")
                        
            except Exception as e:
                print(f"Error creating category {cat_data['name']}: {e}")
        
        # Build result message
        result = "✅ **Setup Implementation Complete!**\n\n"
        
        if created_items['roles']:
            result += f"**Roles Created ({len(created_items['roles'])}):**\n"
            result += ", ".join(created_items['roles'][:10])
            if len(created_items['roles']) > 10:
                result += f" and {len(created_items['roles']) - 10} more..."
            result += "\n\n"
        
        if created_items['categories']:
            result += f"**Categories Created ({len(created_items['categories'])}):**\n"
            result += ", ".join(created_items['categories'])
            result += "\n\n"
        
        if created_items['channels']:
            result += f"**Channels Created ({len(created_items['channels'])}):**\n"
            result += ", ".join(created_items['channels'][:15])
            if len(created_items['channels']) > 15:
                result += f" and {len(created_items['channels']) - 15} more..."
        
        return result if (created_items['roles'] or created_items['categories'] or created_items['channels']) else "⚠️ No items were created. The AI response might not have been in the expected format."
    
    def parse_roles(self, text: str):
        """Extract role names and colors from AI response"""
        roles = []
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            # Look for role patterns like "**Owner**" or "1. **Owner**"
            if '**' in line and ('Description:' in lines[i+1] if i+1 < len(lines) else False):
                role_name = line.split('**')[1] if '**' in line else None
                if role_name and role_name not in ['Roles to Create', 'Setup Plan']:
                    # Look for color in next few lines
                    color = discord.Color.default()
                    for j in range(i, min(i+5, len(lines))):
                        if 'Color:' in lines[j] or '#' in lines[j]:
                            # Extract hex color
                            hex_match = re.search(r'#([0-9A-Fa-f]{6})', lines[j])
                            if hex_match:
                                try:
                                    color = discord.Color(int(hex_match.group(1), 16))
                                except:
                                    pass
                            break
                    
                    roles.append({'name': role_name, 'color': color})
        
        return roles
    
    def parse_categories_and_channels(self, text: str):
        """Extract categories and their channels from AI response"""
        categories = []
        lines = text.split('\n')
        current_category = None
        
        for line in lines:
            # Look for category patterns like "#### Category: Welcome" or "**Category: Welcome**"
            if 'Category:' in line or 'CATEGORY:' in line.upper():
                cat_name = line.split('Category:')[-1].strip()
                cat_name = cat_name.replace('*', '').replace('#', '').strip()
                if cat_name:
                    current_category = {'name': cat_name, 'channels': []}
                    categories.append(current_category)
            
            # Look for channel patterns like "#〡welcome" or "#welcome"
            elif current_category and line.strip().startswith('#'):
                channel_name = line.strip().split()[0].replace('#', '').replace('〡', '').strip()
                # Determine if voice or text (voice channels usually have keywords)
                channel_type = 'voice' if any(word in line.lower() for word in ['voice', 'vc', 'call', 'talk']) else 'text'
                
                if channel_name:
                    current_category['channels'].append({
                        'name': channel_name,
                        'type': channel_type
                    })
        
        return categories


class AIDiscordSetupModal(ui.Modal, title="AI Discord Setup"):
    setup_request = ui.TextInput(
        label="Describe what you want to create",
        placeholder="e.g., Create gaming channels with roles for different games, voice channels for teams, etc.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Use Gemini AI to generate Discord setup plan
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            prompt = f"""
You are a Discord server setup assistant. Based on the user's request, create a detailed plan for setting up Discord channels, roles, and permissions.

User Request: {self.setup_request.value}

Please provide a structured response with:
1. **Roles to create** (with brief descriptions and colors in hex format like #FFD700)
2. **Categories and channels to create** (with purposes)
3. **Permission settings** (who can access what)

Keep it practical and organized. Focus on commonly used Discord features.
Format your response clearly with headers and bullet points.

IMPORTANT: Use this exact format for roles:
**RoleName**
Description: Brief description
Color: #HEXCODE

IMPORTANT: Use this exact format for categories and channels:
#### Category: CategoryName
#channel-name (Text Channel)
Purpose: Channel purpose
"""
            
            # Run the blocking API call in a thread executor to avoid blocking the event loop
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, model.generate_content, prompt)
            
            # Create embed with AI response
            embed = discord.Embed(
                title="🤖 AI Discord Setup Plan",
                color=discord.Color.purple()
            )
            
            # Discord embed field limit is 1024 characters
            # Use description for longer text (up to 4096 chars)
            response_text = response.text
            if len(response_text) > 4000:
                response_text = response_text[:4000] + "..."
            
            embed.description = response_text
            embed.add_field(
                name="⚠️ Important Note", 
                value="Click '✅ Εφαρμογή' to automatically create these roles, categories, and channels, or '❌ Ακύρωση' to cancel.",
                inline=False
            )
            embed.set_footer(text="Generated by Gemini AI")
            
            # Create view with implementation buttons
            view = SetupImplementationView(response_text, interaction.guild)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Error generating setup plan: {str(e)}", ephemeral=True)

# Add the missing on_submit for AddDomainModal
AddDomainModal.on_submit = lambda self, interaction: self._add_domain_submit(interaction)

async def _add_domain_submit(self, interaction: Interaction):
    domain_to_add = self.domain.value.lower().strip()
    if domain_to_add:
        blacklisted_domains.add(domain_to_add)
        save_domain_blacklist()
        await interaction.response.send_message(f"✅ Domain `{domain_to_add}` added to the blacklist.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Domain cannot be empty.", ephemeral=True)

AddDomainModal._add_domain_submit = _add_domain_submit

class AntiNukeLimitsModal(ui.Modal, title="Configure Anti-Nuke Limits"):
    channels_limit = ui.TextInput(
        label="Max Channels per Minute",
        placeholder="e.g., 3",
        default=str(anti_nuke_settings.get('max_channels_per_minute', 3)),
        required=True
    )
    roles_limit = ui.TextInput(
        label="Max Roles per Minute", 
        placeholder="e.g., 5",
        default=str(anti_nuke_settings.get('max_roles_per_minute', 5)),
        required=True
    )
    bans_limit = ui.TextInput(
        label="Max Bans per Minute",
        placeholder="e.g., 5", 
        default=str(anti_nuke_settings.get('max_bans_per_minute', 5)),
        required=True
    )
    kicks_limit = ui.TextInput(
        label="Max Kicks per Minute",
        placeholder="e.g., 10",
        default=str(anti_nuke_settings.get('max_kicks_per_minute', 10)),
        required=True
    )

    async def on_submit(self, interaction: Interaction):
        try:
            anti_nuke_settings['max_channels_per_minute'] = int(self.channels_limit.value)
            anti_nuke_settings['max_roles_per_minute'] = int(self.roles_limit.value)
            anti_nuke_settings['max_bans_per_minute'] = int(self.bans_limit.value)
            anti_nuke_settings['max_kicks_per_minute'] = int(self.kicks_limit.value)
            save_anti_nuke_settings()
            await interaction.response.send_message("✅ Anti-nuke limits updated successfully!", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Please enter valid numbers for all limits.", ephemeral=True)

class DomainBlacklistView(ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.update_components()

    def get_embed(self):
        embed = discord.Embed(title="🔗 Link Blacklist Settings", color=discord.Color.gold())
        status = "Enabled" if spam_settings.get('link_blacklist_enabled', True) else "Disabled"
        embed.description = f"Current Status: **{status}**\nManage which domains are forbidden on this server."
        
        domain_list = "\n".join(f"- `{d}`" for d in sorted(list(blacklisted_domains))) if blacklisted_domains else "No domains blacklisted."
        if len(domain_list) > 1024:
             domain_list = domain_list[:1020] + "..."
        embed.add_field(name="Blacklisted Domains", value=domain_list, inline=False)
        return embed
    
    def update_components(self):
        self.clear_items()
        self.add_item(ui.Button(label="Add Domain", style=ButtonStyle.success, custom_id="add_domain_btn"))
        if blacklisted_domains:
            self.add_item(DomainRemoveSelect())
        self.add_item(ui.Button(label="Refresh", style=ButtonStyle.primary, custom_id="refresh_domain_btn"))
        self.add_item(ui.Button(label="Close Panel", style=ButtonStyle.secondary, custom_id="close_domain_panel_btn"))

    async def callback(self, interaction: Interaction):
        custom_id = interaction.data.get("custom_id")
        if custom_id == "add_domain_btn":
            await interaction.response.send_modal(AddDomainModal())
        elif custom_id == "refresh_domain_btn":
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        elif custom_id == "close_domain_panel_btn":
            await interaction.message.delete()

class DomainRemoveSelect(ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=d, value=d) for d in sorted(list(blacklisted_domains))[:25]]
        super().__init__(placeholder="Select a domain to remove...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        domain_to_remove = self.values[0]
        if domain_to_remove in blacklisted_domains:
            blacklisted_domains.remove(domain_to_remove)
            save_domain_blacklist()
        await interaction.response.send_message(f"✅ Domain `{domain_to_remove}` removed from the blacklist.", ephemeral=True)
        # Refresh the main view
        new_view = DomainBlacklistView()
        await interaction.message.edit(embed=new_view.get_embed(), view=new_view)

class AntiNukeSettingsView(ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.update_components()

    def get_embed(self):
        embed = discord.Embed(title="🛡️ Enhanced Anti-Nuke Settings", color=0x2b2d31)
        status = "Enabled" if anti_nuke_settings['enabled'] else "Disabled"
        embed.description = f"Current Status: **{status}**\nAdvanced protection against server raids and malicious actions."
        
        # Protection settings
        protections = []
        if anti_nuke_settings.get('protect_channels', True):
            protections.append(f"📺 Channels: {anti_nuke_settings.get('max_channels_per_minute', 3)}/min")
        if anti_nuke_settings.get('protect_roles', True):
            protections.append(f"🎭 Roles: {anti_nuke_settings.get('max_roles_per_minute', 5)}/min")
        if anti_nuke_settings.get('protect_members', True):
            protections.append(f"👤 Bans: {anti_nuke_settings.get('max_bans_per_minute', 5)}/min")
            protections.append(f"🦶 Kicks: {anti_nuke_settings.get('max_kicks_per_minute', 10)}/min")
        
        embed.add_field(name="Rate Limits", value="\n".join(protections) if protections else "No limits set", inline=False)
        
        action_type = "Auto-Ban" if anti_nuke_settings.get('auto_ban', False) else "Auto-Kick"
        embed.add_field(name="Punishment", value=action_type, inline=True)
        
        log_status = "Enabled" if anti_nuke_settings.get('log_actions', True) else "Disabled"
        embed.add_field(name="Logging", value=log_status, inline=True)
        
        whitelist_mentions = [f"<@{uid}>" for uid in whitelisted_users]
        whitelist_text = ", ".join(whitelist_mentions) if whitelist_mentions else "No users whitelisted."
        if len(whitelist_text) > 1024:
            whitelist_text = "Too many users to display."
        embed.add_field(name="Whitelisted Users", value=whitelist_text, inline=False)
        return embed
    
    def update_components(self):
        self.clear_items()
        label = "Disable Anti-Nuke" if anti_nuke_settings['enabled'] else "Enable Anti-Nuke"
        style = ButtonStyle.danger if anti_nuke_settings['enabled'] else ButtonStyle.success
        self.add_item(ui.Button(label=label, style=style, custom_id="toggle_anti_nuke"))
        
        # Toggle punishment type
        punishment_label = "Switch to Kick" if anti_nuke_settings.get('auto_ban', False) else "Switch to Ban"
        self.add_item(ui.Button(label=punishment_label, style=ButtonStyle.secondary, custom_id="toggle_punishment"))
        
        # Configure limits
        self.add_item(ui.Button(label="Configure Limits", style=ButtonStyle.primary, custom_id="configure_limits"))
        
        self.add_item(ui.UserSelect(placeholder="Add user to whitelist", custom_id="add_user_whitelist"))
        if whitelisted_users:
            self.add_item(ui.UserSelect(placeholder="Remove user from whitelist", custom_id="remove_user_whitelist"))
        self.add_item(ui.Button(label="Close Panel", style=ButtonStyle.secondary, custom_id="close_nuke_panel"))

    async def handle_interaction(self, interaction: Interaction):
        custom_id = interaction.data["custom_id"]
        
        if custom_id == "toggle_anti_nuke":
            anti_nuke_settings['enabled'] = not anti_nuke_settings['enabled']
            save_anti_nuke_settings()
            await interaction.response.send_message(f"✅ Anti-nuke system is now **{'Enabled' if anti_nuke_settings['enabled'] else 'Disabled'}**.", ephemeral=True)
        elif custom_id == "add_user_whitelist":
            user = interaction.data["values"][0]
            whitelisted_users.add(int(user))
            save_whitelist()
            await interaction.response.send_message(f"✅ <@{user}> added to the whitelist.", ephemeral=True)
        elif custom_id == "toggle_punishment":
            anti_nuke_settings['auto_ban'] = not anti_nuke_settings.get('auto_ban', False)
            save_anti_nuke_settings()
            action = "Ban" if anti_nuke_settings['auto_ban'] else "Kick"
            await interaction.response.send_message(f"✅ Anti-nuke punishment changed to **{action}**.", ephemeral=True)
        elif custom_id == "configure_limits":
            await interaction.response.send_modal(AntiNukeLimitsModal())
            return
        elif custom_id == "add_user_whitelist":
            user = interaction.data["values"][0]
            whitelisted_users.add(int(user))
            save_whitelist()
            await interaction.response.send_message(f"✅ <@{user}> added to the whitelist.", ephemeral=True)
        elif custom_id == "remove_user_whitelist":
            user_id = int(interaction.data["values"][0])
            if user_id in whitelisted_users:
                whitelisted_users.remove(user_id)
                save_whitelist()
                await interaction.response.send_message(f"✅ <@{user_id}> removed from the whitelist.", ephemeral=True)
            else:
                 await interaction.response.send_message("User was not on the whitelist.", ephemeral=True)
        elif custom_id == "close_nuke_panel":
            await interaction.message.delete()
            return
            
        self.update_components()
        await interaction.message.edit(embed=self.get_embed(), view=self)

    async def interaction_check(self, interaction: Interaction) -> bool:
        await self.handle_interaction(interaction)
        return False # We handled it, stop further processing

class AdminPanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You must be an administrator to use this panel.", ephemeral=True)
            return False
        return True

    async def _get_lock_state(self, guild: discord.Guild) -> bool:
        """Checks if the server is currently locked by checking a reference channel."""
        public_channel = next((c for c in guild.text_channels if c.permissions_for(guild.default_role).view_channel), None)
        if public_channel:
            perms = public_channel.overwrites_for(guild.default_role)
            return perms.send_messages is False
        return False # Default to unlocked

    @ui.button(label="Lockdown Server", style=ButtonStyle.danger, emoji="🚨", custom_id="admin_lockdown")
    async def lockdown(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        is_currently_locked = await self._get_lock_state(guild)
        
        should_lock_now = not is_currently_locked
        action_verb = "Locking" if should_lock_now else "Unlocking"
        action_done_verb = "Locked" if should_lock_now else "Unlocked"

        progress_embed = discord.Embed(title=f"Server Lockdown in Progress...", description=f"Now **{action_verb.lower()}** all text channels. Please wait.", color=discord.Color.orange())
        await interaction.followup.send(embed=progress_embed, ephemeral=True)

        for channel in guild.text_channels:
            try:
                overwrites = channel.overwrites_for(guild.default_role)
                overwrites.send_messages = False if should_lock_now else None
                await channel.set_permissions(guild.default_role, overwrite=overwrites, reason=f"Admin Panel Lockdown by {interaction.user}")
            except Exception as e:
                print(f"Error processing channel {channel.name}: {e}")

        if should_lock_now:
            button.style = ButtonStyle.success
            button.label = "Unlock Server"
            button.emoji = "🔓"
        else:
            button.style = ButtonStyle.danger
            button.label = "Lockdown Server"
            button.emoji = "🚨"

        await interaction.message.edit(view=self)

        final_embed = discord.Embed(
            title=f"✅ Server {action_done_verb}",
            description=f"All channels have been **{action_done_verb.lower()}** for `@everyone`.",
            color=discord.Color.red() if should_lock_now else discord.Color.green()
        )
        await interaction.edit_original_response(embed=final_embed)

    @ui.button(label="Manage Bans", style=ButtonStyle.secondary, emoji="🔨", custom_id="admin_ban_panel")
    async def ban_panel_button(self, interaction: Interaction, button: ui.Button):
        bans = [ban async for ban in interaction.guild.bans(limit=25)]
        if not bans:
            await interaction.response.send_message("No banned users.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=discord.Embed(title="Banned Users", description="Click a user for info and unban.", color=discord.Color.red()),
            view=BanListView(bans),
            ephemeral=True
        )

    @ui.button(label="Manage Member", style=ButtonStyle.primary, emoji="👤", custom_id="admin_member_manage")
    async def manage_member(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_message("Please select a member from the dropdown below to manage.", view=MemberSelectView(), ephemeral=True)


    @ui.button(label="Aether Stats", style=ButtonStyle.secondary, emoji="📊", custom_id="admin_server_stats")
    async def server_stats(self, interaction: Interaction, button: ui.Button):
        guild = interaction.guild
        embed = discord.Embed(title=f"📊 Statistics for {guild.name}", color=discord.Color.blue(), timestamp=discord.utils.utcnow())
        
        total_members = guild.member_count
        bots = sum(1 for member in guild.members if member.bot)
        humans = total_members - bots

        online_members = sum(1 for m in guild.members if m.status != discord.Status.offline)

        embed.add_field(name="👥 Members", value=f"**Total:** {total_members}\n**Humans:** {humans}\n**Bots:** {bots}\n**Online:** {online_members}", inline=True)

        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        embed.add_field(name="💬 Channels", value=f"**Total:** {text_channels + voice_channels}\n**Text:** {text_channels}\n**Voice:** {voice_channels}\n**Categories:** {categories}", inline=True)

        embed.add_field(name="📋 Other", value=f"**Roles:** {len(guild.roles)}\n**Emojis:** {len(guild.emojis)}", inline=True)

        embed.add_field(name="📅 Server Created", value=discord.utils.format_dt(guild.created_at, style='F'), inline=False)
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.owner:
            embed.set_footer(text=f"Owner: {guild.owner}", icon_url=guild.owner.display_avatar.url)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Make Announcement", style=ButtonStyle.primary, emoji="📢", custom_id="admin_announcement")
    async def make_announcement(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_modal(AnnouncementModal())
    
    @ui.button(label="Anti-Spam Settings", style=ButtonStyle.secondary, emoji="🚫", row=2, custom_id="admin_spam_settings")
    async def spam_settings_button(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_modal(SpamSettingsModal())

    @ui.button(label="Link Blacklist", style=ButtonStyle.secondary, emoji="🔗", row=2, custom_id="admin_link_blacklist")
    async def link_blacklist_button(self, interaction: Interaction, button: ui.Button):
        view = DomainBlacklistView()
        await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)

    @ui.button(label="Anti-Nuke Settings", style=ButtonStyle.secondary, emoji="🛡", row=2, custom_id="admin_anti_nuke")
    async def anti_nuke_button(self, interaction: Interaction, button: ui.Button):
        view = AntiNukeSettingsView()
        await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)

    @ui.button(label="AI Discord Setup", style=ButtonStyle.primary, emoji="🤖", row=3, custom_id="admin_ai_setup")
    async def ai_discord_setup(self, interaction: Interaction, button: ui.Button):
        if not GEMINI_API_KEY:
            await interaction.response.send_message("❌ AI feature is not configured. Please set up the Gemini API key first using `/ai_setup`.", ephemeral=True)
            return
        await interaction.response.send_modal(AIDiscordSetupModal())

    @ui.button(label="Host Stats", style=ButtonStyle.secondary, emoji="📊", row=3, custom_id="admin_host_stats")
    async def host_stats_button(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        embed = await get_host_stats_embed()
        
        # Update footer to show auto-refresh info
        embed.set_footer(
            text="📈 Auto-refreshing every 30 seconds • Powered by psutil",
            icon_url="https://cdn.discordapp.com/emojis/741090906693935185.png"
        )
        
        message = await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Add to auto-refresh tracking
        auto_refresh_host_stats[message.id] = {
            'channel': interaction.channel,
            'message': message
        }

    @ui.button(label="Create Backup", style=ButtonStyle.success, emoji="💾", row=3, custom_id="admin_create_backup")
    async def create_backup(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        backup_file = await _create_backup_file(interaction.guild)
        await interaction.followup.send("✅ Here is your server backup file.", file=backup_file, ephemeral=True)

class ConfirmLoadBackupView(ui.View):
    def __init__(self, file: discord.Attachment):
        super().__init__(timeout=120)
        self.file = file
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(content="Backup load confirmation expired.", view=self, embed=None)
            except discord.NotFound:
                pass # Message was likely dismissed

    @ui.button(label="Confirm Load Backup", style=ButtonStyle.danger, emoji="🔥")
    async def confirm(self, interaction: Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You are not an administrator.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        
        try:
            # Step 1: Read and parse the backup file
            file_bytes = await self.file.read()
            backup_data = json.loads(file_bytes)

            if 'guild_id' not in backup_data or 'roles' not in backup_data:
                await interaction.followup.send("❌ Invalid backup file format.", ephemeral=True)
                return

            await interaction.followup.send("✅ Backup validated. Starting restoration process. This will take a while. The server will be unavailable during this process.", ephemeral=True)
            
            # --- DELETION PHASE ---
            for channel in guild.channels:
                try: await channel.delete(reason="Backup Restoration")
                except: pass
            
            for role in guild.roles:
                if role.is_default() or role.managed or role.position >= guild.me.top_role.position:
                    continue
                try: await role.delete(reason="Backup Restoration")
                except: pass

            # --- CREATION PHASE ---
            role_map = {}
            
            everyone_data = next((r for r in backup_data['roles'] if r['is_everyone']), None)
            if everyone_data:
                 everyone_role = guild.default_role
                 await everyone_role.edit(permissions=discord.Permissions(everyone_data['permissions']), reason="Backup Restoration")
                 role_map['@everyone'] = everyone_role

            for role_data in reversed([r for r in backup_data['roles'] if not r['is_everyone'] and not r['is_bot_role']]):
                new_role = await guild.create_role(
                    name=role_data['name'],
                    permissions=discord.Permissions(role_data['permissions']),
                    color=discord.Color(role_data['color']),
                    hoist=role_data['hoist'],
                    mentionable=role_data['mentionable'],
                    reason="Backup Restoration"
                )
                role_map[role_data['name']] = new_role
            
            for category_data in backup_data.get('categories', []):
                cat_overwrites = {}
                for ow_data in category_data.get('overwrites', []):
                    target_role = role_map.get(ow_data['role_name'])
                    if target_role:
                        allow_perms = discord.Permissions(ow_data['allow'])
                        deny_perms = discord.Permissions(ow_data['deny'])
                        cat_overwrites[target_role] = discord.PermissionOverwrite.from_pair(allow_perms, deny_perms)

                new_category = await guild.create_category(name=category_data['name'], overwrites=cat_overwrites, reason="Backup Restoration")

                for channel_data in category_data.get('channels', []):
                    chan_overwrites = {}
                    for ow_data in channel_data.get('overwrites', []):
                        target_role = role_map.get(ow_data['role_name'])
                        if target_role:
                            allow_perms = discord.Permissions(ow_data['allow'])
                            deny_perms = discord.Permissions(ow_data['deny'])
                            chan_overwrites[target_role] = discord.PermissionOverwrite.from_pair(allow_perms, deny_perms)

                    if channel_data['type'] == 'text':
                        await new_category.create_text_channel(name=channel_data['name'], topic=channel_data.get('topic'), overwrites=chan_overwrites, reason="Backup Restoration")
                    elif channel_data['type'] == 'voice':
                        await new_category.create_voice_channel(name=channel_data['name'], overwrites=chan_overwrites, reason="Backup Restoration")
            
            self.stop()
            await interaction.edit_original_response(content="✅ Server restoration complete!", view=None, embed=None)

        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred during restoration: {e}", ephemeral=True)
            print(f"Backup load error: {e}")

    @ui.button(label="Cancel", style=ButtonStyle.secondary)
    async def cancel(self, interaction: Interaction, button: ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Backup load cancelled.", view=None, embed=None)

class PollView(ui.View):
    def __init__(self, question: str, choices: list[str]):
        super().__init__(timeout=None) # Polls don't time out
        self.question = question
        self.choices = choices
        self.votes = {choice: 0 for choice in choices}
        self.voters = {} # {user_id: choice}

        # Add a button for each choice
        for choice in self.choices:
            # Ensure label length is within Discord's limits
            button_label = choice[:80]
            self.add_item(ui.Button(label=button_label, style=ButtonStyle.secondary, custom_id=choice))

    def create_embed(self):
        """Creates the poll embed based on the current vote counts."""
        embed = discord.Embed(
            title=f"📊 Poll: {self.question}",
            color=discord.Color.blue()
        )
        description = []
        total_votes = sum(self.votes.values())
        for choice in self.choices:
            count = self.votes[choice]
            # Calculate percentage
            percentage = (count / total_votes * 100) if total_votes > 0 else 0
            # Create a simple progress bar
            bar = "█" * int(percentage / 10) + " " * (10 - int(percentage / 10))
            description.append(f"**{choice}**\n`{bar}` ({count} votes, {percentage:.1f}%)")
        
        embed.description = "\n\n".join(description)
        embed.set_footer(text=f"Total Votes: {total_votes}")
        return embed

    async def interaction_check(self, interaction: Interaction) -> bool:
        """This is called before any button callback to handle vote logic."""
        user_id = interaction.user.id
        selected_choice = interaction.data["custom_id"]

        previous_vote = self.voters.get(user_id)

        if previous_vote:
            # User has voted before, decrement their old choice
            self.votes[previous_vote] -= 1

        if previous_vote == selected_choice:
            # User is retracting their vote
            del self.voters[user_id]
            await interaction.response.send_message(f"Your vote for '{selected_choice}' has been removed.", ephemeral=True)
        else:
            # User is voting or changing their vote
            self.voters[user_id] = selected_choice
            self.votes[selected_choice] += 1
            await interaction.response.send_message(f"✅ You voted for '{selected_choice}'.", ephemeral=True)

        # Update the original message with the new embed
        await interaction.message.edit(embed=self.create_embed(), view=self)
        
        return False # We've handled the interaction, no need to call button callbacks.

class VerificationView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @ui.button(label="✅ Verify", style=ButtonStyle.green, custom_id="verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild
        config = verification_config.get(guild.id)
        
        if not config:
            await interaction.response.send_message("❌ Verification is not set up properly.", ephemeral=True)
            return
        
        role = guild.get_role(config['role_id'])
        if not role:
            await interaction.response.send_message("❌ Verification role not found.", ephemeral=True)
            return
        
        member = interaction.user
        if role in member.roles:
            await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
            return
        
        try:
            await member.add_roles(role, reason="Verification")
            await interaction.response.send_message(f"✅ You have been verified! You now have access to the server.", ephemeral=True)
            
            # Log the verification
            embed = discord.Embed(
                title="✅ Member Verified",
                description=f"{member.mention} has been verified.",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            await send_log(guild, "member", embed)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to assign roles.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)

# ----------------- BACKGROUND TASKS -----------------
@tasks.loop(minutes=10)
async def update_status_channels_task():
    # This assumes the bot is in only one server.
    if not bot.guilds:
        return
    guild = bot.guilds[0]
    await _update_status_channels(guild)

@update_status_channels_task.before_loop
async def before_update_status():
    await bot.wait_until_ready()

@tasks.loop(minutes=1)
async def update_leaderboard_task():
    for guild_id in list(invite_leaderboard_config.keys()):
        guild = bot.get_guild(guild_id)
        if guild:
            await _update_leaderboard_message(guild)

@update_leaderboard_task.before_loop
async def before_leaderboard_update():
    await bot.wait_until_ready()

@tasks.loop(minutes=10)
async def enforce_global_bans_task():
    if not globally_banned_users:
        return

    banned_ids = list(globally_banned_users.keys())
    for user_id_str in banned_ids:
        user_id = int(user_id_str)
        reason = globally_banned_users.get(user_id_str, "Globally banned.")
        for guild in bot.guilds:
            try:
                # Check if the user is a member, which is more reliable than checking the ban list
                member = guild.get_member(user_id)
                if member:
                    await guild.ban(member, reason=f"Global Ban Enforcement: {reason}")
                    print(f"Re-banned globally banned user {user_id} in guild {guild.name}.")
            except discord.Forbidden:
                # Bot lacks permissions to ban in this guild.
                pass
            except Exception as e:
                print(f"Error enforcing global ban for {user_id} in {guild.name}: {e}")

@enforce_global_bans_task.before_loop
async def before_enforce_global_bans():
    await bot.wait_until_ready()

@tasks.loop(hours=1)  # Send host stats every hour
async def host_stats_task():
    """Send host statistics to server logs every hour."""
    if not bot.guilds or not PSUTIL_AVAILABLE:
        return
    
    embed = await get_host_stats_embed()
    
    # Send to all guilds that have server logs configured
    for guild in bot.guilds:
        try:
            await send_log(guild, "server", embed)
        except Exception as e:
            print(f"Error sending host stats to guild {guild.id}: {e}")

@host_stats_task.before_loop
async def before_host_stats():
    await bot.wait_until_ready()

@tasks.loop(seconds=30)  # Update host stats every 30 seconds
async def auto_refresh_host_stats_task():
    """Auto-refresh host statistics messages every 30 seconds."""
    if not PSUTIL_AVAILABLE or not auto_refresh_host_stats:
        return
    
    embed = await get_host_stats_embed()
    
    # Update all registered messages
    messages_to_remove = []
    for message_id, data in auto_refresh_host_stats.items():
        try:
            message = data['message']
            await message.edit(embed=embed)
        except discord.NotFound:
            # Message was deleted, remove from tracking
            messages_to_remove.append(message_id)
        except discord.Forbidden:
            # No permission to edit, remove from tracking
            messages_to_remove.append(message_id)
        except Exception as e:
            print(f"Error updating host stats message {message_id}: {e}")
    
    # Clean up deleted/inaccessible messages
    for message_id in messages_to_remove:
        del auto_refresh_host_stats[message_id]

@auto_refresh_host_stats_task.before_loop
async def before_auto_refresh_host_stats():
    await bot.wait_until_ready()


@tasks.loop(minutes=AUTO_CLOSE_CHECK_EVERY_MINUTES)
async def auto_close_idle_tickets_task():
    now = discord.utils.utcnow()
    for guild in bot.guilds:
        for ch in guild.text_channels:
            if not is_ticket_channel(ch):
                continue

            # Avoid instantly closing tickets after a restart when we have no history.
            last = ticket_last_activity.get(ch.id)
            if last is None:
                ticket_last_activity[ch.id] = now
                continue

            idle_seconds = (now - last).total_seconds()
            warn_after_seconds = AUTO_CLOSE_WARNING_AFTER_HOURS * 3600
            close_after_seconds = warn_after_seconds + (AUTO_CLOSE_GRACE_MINUTES * 60)

            if idle_seconds >= close_after_seconds:
                try:
                    await close_ticket_no_interaction(
                        ch,
                        guild,
                        reason=f"Auto-closed: inactive for {AUTO_CLOSE_WARNING_AFTER_HOURS}h+{AUTO_CLOSE_GRACE_MINUTES}m"
                    )
                finally:
                    ticket_last_activity.pop(ch.id, None)
                    ticket_warned_at.pop(ch.id, None)
                continue

            if idle_seconds >= warn_after_seconds and ch.id not in ticket_warned_at:
                try:
                    ticket_owner = await get_ticket_owner_user(ch, guild)
                    warn_embed = discord.Embed(
                        title="⏳ Ticket Inactivity Warning",
                        description=(
                            f"This ticket will be automatically closed in **{AUTO_CLOSE_GRACE_MINUTES} minutes** "
                            "if no one sends a message.\n\n"
                            "Send any message to keep it open."
                        ),
                        color=discord.Color.orange(),
                        timestamp=now
                    )
                    content = ticket_owner.mention if ticket_owner else None
                    await ch.send(content=content, embed=warn_embed)
                    ticket_warned_at[ch.id] = now
                except Exception as e:
                    print(f"Failed to warn idle ticket {ch.id}: {e}")


@auto_close_idle_tickets_task.before_loop
async def before_auto_close_idle_tickets():
    await bot.wait_until_ready()


# ----------------- EVENT HANDLERS -----------------
@bot.event
async def on_ready():
    # Persist the views across bot restarts
    bot.add_view(TicketPanel())
    bot.add_view(TicketActions())
    bot.add_view(AISetupView())
    bot.add_view(AIStartChatOnlyView())
    bot.add_view(AIChatActionsView())
    bot.add_view(AdminPanelView())
    bot.add_view(VerificationView())

    load_log_channels()
    load_welcome_channel()
    load_goodbye_channel()
    load_whitelist()
    load_autorole()
    load_gemini_key()
    load_status_channels()
    load_spam_settings()
    load_domain_blacklist()
    load_anti_nuke_settings()
    load_invites_data()
    load_invite_leaderboard_config()
    load_global_bans()
    load_bot_announcement_channels()
    load_ticket_categories()
    load_suggestions_channel()
    load_ticket_logs_channel()
    load_ticket_counters()
    load_support_channels()
    load_verification_config()

    print(f"Logged in as {bot.user}")
    
    # Sync slash commands to Discord
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands to Discord")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")
    
    # Set bot status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.streaming,
            name="💓Made With Love By Axio & Moikan"
        ),
        status=discord.Status.online
    )

    print("Caching guild invites...")
    for guild in bot.guilds:
        try:
            invites_list = await guild.invites()
            guild_invites_cache[guild.id] = {invite.code: {'uses': invite.uses, 'inviter_id': invite.inviter.id} for invite in invites_list if invite.inviter}
        except discord.Forbidden:
            print(f"Lacking 'Manage Server' permissions in guild '{guild.name}' to cache invites.")
        except Exception as e:
            print(f"Error caching invites for guild {guild.id}: {e}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)
    
    # Start background tasks if they are not already running
    if not update_status_channels_task.is_running():
        update_status_channels_task.start()
    if not update_leaderboard_task.is_running():
        update_leaderboard_task.start()
    if not enforce_global_bans_task.is_running():
        enforce_global_bans_task.start()
    if not host_stats_task.is_running():
        host_stats_task.start()
    
    if not auto_refresh_host_stats_task.is_running():
        auto_refresh_host_stats_task.start()
    if not auto_close_idle_tickets_task.is_running():
        auto_close_idle_tickets_task.start()

# --- INVITE EVENTS ---
@bot.event
async def on_invite_create(invite):
    """Update cache when an invite is created."""
    if invite.guild.id in guild_invites_cache and invite.inviter:
        guild_invites_cache[invite.guild.id][invite.code] = {'uses': invite.uses, 'inviter_id': invite.inviter.id}

@bot.event
async def on_invite_delete(invite):
    """Update cache when an invite is deleted."""
    if invite.guild.id in guild_invites_cache and invite.code in guild_invites_cache[invite.guild.id]:
        del guild_invites_cache[invite.guild.id][invite.code]

# --- MEMBER LOGS ---
@bot.event
async def on_member_join(member):
    # --- Global Ban Check (Priority 1) ---
    if str(member.id) in globally_banned_users:
        reason = globally_banned_users.get(str(member.id), "Previously globally banned.")
        try:
            await member.ban(reason=f"Global Ban Enforcement on Join: {reason}")
            print(f"Banned globally banned user {member.id} immediately upon joining {member.guild.name}.")
            
            log_embed = discord.Embed(
                title="🚨 Global Ban Enforced on Join 🚨",
                description=f"**User:** {member.mention} ({member.id}) was automatically banned upon joining because they are on the global ban list.",
                color=discord.Color.dark_red()
            )
            await send_log(member.guild, "security", log_embed)
            return # Stop further processing for this user
        except discord.Forbidden:
            print(f"Failed to ban globally banned user {member.id} on join in {member.guild.name} due to permissions.")
        except Exception as e:
            print(f"An error occurred while banning globally banned user {member.id} on join: {e}")

    # --- Invite Tracker ---
    inviter = None
    guild = member.guild
    try:
        # Get the invites from BEFORE this member joined (from our cache)
        invites_before_join = guild_invites_cache.get(guild.id, {})
        
        # Get the invites from AFTER this member joined (fresh from Discord)
        invites_after_join_list = await guild.invites()
        
        print(f"--- INVITE DEBUG for {member.name} in {guild.name} ---")
        print(f"Cached invites before join: {len(invites_before_join)}")
        print(f"Fetched invites after join: {len(invites_after_join_list)}")

        # Update our cache immediately for the next person
        current_invites = {invite.code: {'uses': invite.uses, 'inviter_id': invite.inviter.id} for invite in invites_after_join_list if invite.inviter}
        guild_invites_cache[guild.id] = current_invites

        # Now, find the invite that was used
        for code, invite_details in current_invites.items():
            old_uses = invites_before_join.get(code, {}).get('uses', 0)
            if invite_details['uses'] > old_uses:
                inviter_id = invite_details['inviter_id']
                # Find the member object for the inviter
                inviter = guild.get_member(inviter_id) or await bot.fetch_user(inviter_id)
                if inviter:
                    # Update stats
                    invites_data[guild.id][inviter.id]['regular'] += 1
                    invite_map[guild.id][member.id] = inviter.id
                    save_invites_data()
                    print(f"SUCCESS: Determined {member.name} was invited by {inviter.name}")
                break # We found the invite, stop looking
        
        if not inviter:
            print(f"FAILURE: Could not determine inviter for {member.name}. This can happen with vanity URLs or temporary invites.")
            
    except discord.Forbidden:
        print(f"ERROR: Could not track invite in '{guild.name}' due to missing 'Manage Server' permissions.")
    except Exception as e:
        print(f"ERROR: An unexpected error occurred during invite tracking for {member.name}: {e}")

    # --- Welcome Message ---
    if welcome_channel_id:
        channel = member.guild.get_channel(welcome_channel_id)
        if channel:
            embed = discord.Embed(
                description=f"Welcome {member.mention} to **{member.guild.name}**!\nGlad to have you with us.",
                color=discord.Color.blurple(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=f"{member.name} just joined!", icon_url=member.display_avatar.url)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"We are now {member.guild.member_count} members strong!")
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                print(f"Could not send welcome message to channel {channel.id}. Missing permissions.")

    # --- Auto Role ---
    if autorole_id:
        role = member.guild.get_role(autorole_id)
        if role:
            try:
                await member.add_roles(role, reason="Auto-role on join")
            except discord.Forbidden:
                print(f"Failed to add auto-role to {member.display_name}. Missing permissions or role hierarchy issue.")

    # --- Join Tag Message ---
    tag_channel_id = 1479445699958542457
    try:
        tag_channel = member.guild.get_channel(tag_channel_id)
        if tag_channel:
            msg = await tag_channel.send(f"Welcome {member.mention}!")
            await msg.delete()
    except discord.Forbidden:
        print(f"Could not send or delete tag message in channel {tag_channel_id}. Missing permissions.")
    except Exception as e:
        print(f"An error occurred while sending/deleting tag message: {e}")

    # --- Log Join ---
    log_embed = await get_userinfo_embed(member)
    log_embed.title = "User Joined"
    if inviter:
        log_embed.add_field(name="Invited By", value=f"{inviter.mention} (`{inviter.name}`)", inline=False)
    log_embed.color = discord.Color.green()
    await send_log(member.guild, "member", log_embed)

@bot.event
async def on_member_remove(member):
    # --- Invite Tracker ---
    inviter = None
    try:
        inviter_id = invite_map[member.guild.id].pop(member.id, None)
        if inviter_id:
            invites_data[member.guild.id][inviter_id]['regular'] -= 1
            invites_data[member.guild.id][inviter_id]['left'] += 1
            save_invites_data()
            inviter = member.guild.get_member(inviter_id) or await bot.fetch_user(inviter_id)
    except Exception as e:
        print(f"An error occurred during invite tracking for leave: {e}")

    # --- Goodbye Message ---
    if goodbye_channel_id:
        channel = member.guild.get_channel(goodbye_channel_id)
        if channel:
            embed = discord.Embed(
                description=f"Goodbye {member.mention}!\nWe're sad to see you leave **{member.guild.name}**.",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=str(member), icon_url=member.display_avatar.url)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)
            embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, style='R'), inline=True)
            
            if member.joined_at:
                embed.add_field(name="Joined Server", value=discord.utils.format_dt(member.joined_at, style='R'), inline=True)
            
            if inviter:
                embed.add_field(name="Was Invited By", value=f"{inviter.mention}", inline=False)
            
            embed.set_footer(text=f"Member Count: {member.guild.member_count}")
            
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                print(f"Missing permissions to send goodbye message in {channel.name}")
            except Exception as e:
                print(f"Error sending goodbye message: {e}")

    # --- Log Leave ---
    embed = await get_userinfo_embed(member)
    embed.title = "User Left"
    embed.description = f"{member.mention} has left the server."
    if inviter:
        embed.add_field(name="Invited By", value=f"{inviter.mention} (`{inviter.name}`)", inline=False)
    embed.color = discord.Color.dark_gray()
    await send_log(member.guild, "member", embed)

@bot.event
async def on_member_update(before, after):
    # Nickname Change
    if before.nick != after.nick:
        embed = discord.Embed(
            title="Nickname Changed",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=str(after), icon_url=after.display_avatar.url)
        embed.add_field(name="Member", value=after.mention, inline=False)
        embed.add_field(name="Before", value=f"`{before.nick or 'None'}`", inline=True)
        embed.add_field(name="After", value=f"`{after.nick or 'None'}`", inline=True)
        await send_log(after.guild, "server", embed)

    # Server Avatar Change
    if before.guild_avatar != after.guild_avatar:
        embed = discord.Embed(
            title="Server Avatar Changed",
            description=f"{after.mention}'s server profile picture was updated.",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=str(after), icon_url=after.display_avatar.url)
        if after.guild_avatar:
            embed.set_thumbnail(url=after.guild_avatar.url)
        else:
             embed.description += "\n(Avatar was removed.)"
        await send_log(after.guild, "server", embed)

# --- MESSAGE LOGS & SECURITY ---
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
        return

    # Commands-only channel enforcement
    COMMANDS_ONLY_CHANNEL_ID = 1491517827931443301
    if message.channel.id == COMMANDS_ONLY_CHANNEL_ID:
        # Ignore slash commands (they don't appear as regular messages)
        # Only delete regular text messages
        if not message.content.startswith('/'):
            try:
                await message.delete()
                warning = await message.channel.send(
                    f"{message.author.mention} This channel is for commands only. Please use slash commands here.",
                    delete_after=5
                )
                await message.author.timeout(timedelta(seconds=60), reason="Sending messages in commands-only channel")
            except discord.Forbidden:
                pass
            return

    # Ticket idle tracking (any user message keeps it open)
    try:
        if is_ticket_channel(message.channel):
            ticket_last_activity[message.channel.id] = discord.utils.utcnow()
            ticket_warned_at.pop(message.channel.id, None)
    except Exception:
        pass
    
    # AI Chat Handler
    if message.channel.id in active_ai_chats:
        chat_session = active_ai_chats[message.channel.id]
        async with message.channel.typing():
            try:
                response = await chat_session.send_message_async(message.content)
                response_text = response.text
                # Split response if it's too long for a single Discord message embed
                for i in range(0, len(response_text), 4000):
                    chunk = response_text[i:i+4000]
                    embed = discord.Embed(description=chunk, color=discord.Color.purple())
                    await message.channel.send(embed=embed)

            except Exception as e:
                print(f"Gemini API error in thread {message.channel.id}: {e}")
                await message.channel.send(f"😥 An error occurred while contacting the AI: `{e}`")
        return # Stop further processing

    # Suggestions Channel Cleaner
    if suggestions_channel_id and message.channel.id == suggestions_channel_id:
        # This will only trigger for non-bot users due to the check at the function start.
        # We also exempt administrators from this rule.
        if not message.author.guild_permissions.administrator:
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention}, please use the `/suggest` command to submit ideas in this channel.",
                    delete_after=10
                )
            except discord.errors.NotFound:
                pass # Message was already deleted, no action needed.
            except discord.errors.Forbidden:
                print(f"Error: Missing permissions to delete messages in the suggestions channel ({message.channel.id}).")
            # We return here to stop any other processing (like anti-spam or anti-link) on the deleted message.
            return

    # Anti-Spam System
    if spam_settings['enabled'] and not message.author.guild_permissions.administrator:
        now = time.time()
        user_message_times[message.author.id].append(now)
        
        # Count recent messages
        recent_messages = [t for t in user_message_times[message.author.id] if now - t < spam_settings['time_window']]
        
        if len(recent_messages) > spam_settings['message_count']:
            user_message_times[message.author.id].clear() # Reset to prevent spamming punishments
            
            log_embed = discord.Embed(
                title="💨 Anti-Spam Triggered",
                description=f"**User:** {message.author.mention}\n**Action:** {spam_settings['action'].title()}",
                color=discord.Color.orange()
            )
            
            if spam_settings['action'] == 'timeout':
                duration = timedelta(minutes=spam_settings['timeout_duration'])
                try:
                    await message.author.timeout(duration, reason="Anti-Spam")
                    await message.channel.send(f"Hey {message.author.mention}, slow down! You've been timed out for {spam_settings['timeout_duration']} minutes.", delete_after=15)
                    log_embed.add_field(name="Duration", value=f"{spam_settings['timeout_duration']} minutes")
                except discord.Forbidden:
                    await message.channel.send(f"{message.author.mention}, please slow down. (I would time you out, but I lack permissions!)", delete_after=15)
            else: # 'warn'
                await message.channel.send(f"Please slow down, {message.author.mention}!", delete_after=10)

            await send_log(message.guild, "security", log_embed)
            return # Stop processing to prevent link checks on spam

    # Anti-Link System (Whitelist-based)
    if not message.author.guild_permissions.administrator:
        # Define whitelisted domains
        whitelisted_domains = {
            'youtube.com',
            'youtu.be',
            'medal.tv',
            'tiktok.com',
            'instagram.com'
        }
        
        # Regex to find all URLs (http/https) and Discord invites
        link_pattern = re.compile(r'(https?://\S+)|(discord\.gg/\S+)|(discord\.com/invite/\S+)')
        found_links = link_pattern.finditer(message.content)

        for match in found_links:
            link = match.group(0)
            is_whitelisted = False
            
            # Block Discord invites explicitly
            if 'discord.gg/' in link or 'discord.com/invite/' in link:
                is_whitelisted = False
            else:
                try:
                    domain = urllib.parse.urlparse(link).netloc.lower()
                    # Check if the extracted domain ends with a whitelisted domain (handles subdomains)
                    if any(domain.endswith(d) for d in whitelisted_domains):
                        is_whitelisted = True
                except Exception as e:
                    print(f"Could not parse domain from link '{link}': {e}")
                    is_whitelisted = False

            if not is_whitelisted:
                try:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention}, your message was removed because it contained a disallowed link.", delete_after=10)
                    
                    embed = discord.Embed(
                        title="🔗 Disallowed Link Blocked 🔗",
                        description=f"**User:** {message.author.mention} tried to send a link.\n**Content:** `{message.content[:200]}`\n**Channel:** {message.channel.mention}",
                        color=discord.Color.gold()
                    )
                    await send_log(message.guild, "security", embed)
                    return
                except Exception as e:
                    print(f"Error during anti-link action: {e}")
                break

    # --- Consolidated Message & File Logger ---
    # Log sent messages and file uploads to their respective channels.
    log_message_channel = log_channels.get("message")
    log_file_channel = log_channels.get("file")

    # Log the text content of the message
    if log_message_channel and message.content:
        embed = discord.Embed(
            description=f"**Message sent by {message.author.mention} in {message.channel.mention}**\n[Jump to Message]({message.jump_url})",
            color=discord.Color.dark_grey(),
            timestamp=message.created_at
        )
        embed.add_field(name="Content", value=message.content[:1024], inline=False)
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.set_footer(text=f"User ID: {message.author.id}")
        await send_log(message.guild, "message", embed)

    # Log any attachments
    if log_file_channel and message.attachments:
        for attachment in message.attachments:
            embed = discord.Embed(
                title="📄 File Uploaded",
                description=f"**User:** {message.author.mention}\n**Channel:** {message.channel.mention}\n**Message:** [Jump to Message]({message.jump_url})",
                color=discord.Color.light_grey()
            )
            embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
            embed.add_field(name="Filename", value=f"[{attachment.filename}]({attachment.url})", inline=False)
            embed.add_field(name="File Size", value=f"{attachment.size / 1024:.2f} KB", inline=True)
            embed.add_field(name="Content Type", value=attachment.content_type, inline=True)
            if attachment.height: # It's an image/video
                embed.set_image(url=attachment.url)
            await send_log(message.guild, "file", embed)

    await bot.process_commands(message)

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return

    # If message is not in cache, we can't get content. This is a limitation of Discord.
    content = message.content or "[Content not available from cache]"
    if message.attachments:
        attach_lines = [f"[{a.filename}]({a.url})" for a in message.attachments]
        attachments_str = "\n".join(attach_lines)
        content = f"{content}\n\n**Attachments:**\n{attachments_str}" if message.content else f"**Attachments:**\n{attachments_str}"

    embed = discord.Embed(
        title="🗑️ Message Deleted",
        description=f"**Author:** {message.author.mention}\n**Channel:** {message.channel.mention}",
        color=discord.Color.orange(),
        timestamp=discord.utils.utcnow()
    )
    embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)

    # Don't add an empty content field.
    if content.strip() and content != "[Content not available from cache]":
        embed.add_field(name="Content", value=content[:1024], inline=False)

    await send_log(message.guild, "message", embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or not before.guild or (before.content == after.content and before.embeds == after.embeds):
        return

    before_content = before.content or "[Content not available from cache]"
    after_content = after.content or "[Content not available]"

    embed = discord.Embed(
        title=f"📝 Message Edited",
        description=f"**User:** {before.author.mention}\n**Channel:** {before.channel.mention}\n[Jump to Message]({after.jump_url})",
        color=discord.Color.blue(),
        timestamp=after.edited_at or discord.utils.utcnow()
    )
    embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
    embed.add_field(name="Before", value=before_content[:1024], inline=False)
    embed.add_field(name="After", value=after_content[:1024], inline=False)
    await send_log(before.guild, "message", embed)

# --- VOICE & SECURITY LOGS ---
@bot.event
async def on_voice_state_update(member, before, after):
    # Support Call System
    guild_support_channel = support_channels.get(member.guild.id)
    
    # Handle joining support channel
    if after.channel and after.channel.id == guild_support_channel and member.id not in active_support_calls:
        try:
            # Create temporary support room
            temp_channel = await member.guild.create_voice_channel(
                name=f"🎧 Support - {member.display_name}",
                category=after.channel.category,
                reason="Temporary support call created"
            )
            
            # Move user to temporary channel
            await member.move_to(temp_channel)
            
            # Track the support call
            active_support_calls[member.id] = {
                'temp_channel': temp_channel.id,
                'original_channel': after.channel.id
            }
            
            # Send notification to logs
            embed = discord.Embed(
                title="🎧 Support Call Created",
                description=f"{member.mention} joined support and was moved to {temp_channel.mention}",
                color=discord.Color.blue()
            )
            await send_log(member.guild, "voice", embed)
            
        except discord.Forbidden:
            print(f"Missing permissions to create support channel for {member}")
        except Exception as e:
            print(f"Error creating support call: {e}")
    
    # Handle leaving temporary support channels
    if before.channel and not after.channel:
        # Check if user left a temporary support channel
        if member.id in active_support_calls:
            temp_channel_id = active_support_calls[member.id]['temp_channel']
            if before.channel.id == temp_channel_id:
                # Check if channel is empty
                if len(before.channel.members) == 0:
                    try:
                        await before.channel.delete(reason="Support call ended - channel empty")
                        del active_support_calls[member.id]
                        
                        embed = discord.Embed(
                            title="🎧 Support Call Ended",
                            description=f"Support call for {member.mention} has ended and channel was deleted",
                            color=discord.Color.red()
                        )
                        await send_log(member.guild, "voice", embed)
                    except Exception as e:
                        print(f"Error deleting support channel: {e}")
    
    # Handle moving between channels (cleanup empty support channels)
    if before.channel and after.channel and before.channel != after.channel:
        # Check if someone left a temporary support channel
        for user_id, call_info in list(active_support_calls.items()):
            if before.channel.id == call_info['temp_channel'] and len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="Support call ended - channel empty")
                    del active_support_calls[user_id]
                    
                    embed = discord.Embed(
                        title="🎧 Support Call Ended",
                        description=f"Empty support channel was automatically deleted",
                        color=discord.Color.red()
                    )
                    await send_log(member.guild, "voice", embed)
                except Exception as e:
                    print(f"Error deleting empty support channel: {e}")
                break
    
    # --- VC Stay: reconnect if Discord disconnected the bot ---
    if member.id == member.guild.me.id:
        # The bot itself had a voice state change
        target_channel_id = vc_stay_channels.get(member.guild.id)
        if target_channel_id and before.channel and not after.channel:
            # Bot was disconnected — wait briefly then reconnect
            await asyncio.sleep(1)
            target_channel = member.guild.get_channel(target_channel_id)
            if target_channel:
                try:
                    vc = await target_channel.connect(self_deaf=True)
                    vc.play(discord.PCMVolumeTransformer(SilenceAudio(), volume=0), after=None)
                except Exception as e:
                    print(f"VC stay reconnect failed: {e}")
        return  # Don't log the bot's own voice state changes

    # Regular voice logging
    if before.channel != after.channel:
        if after.channel and not before.channel:
            action = f"joined voice channel {after.channel.mention}"
            color = discord.Color.green()
        elif before.channel and not after.channel:
            action = f"left voice channel {before.channel.mention}"
            color = discord.Color.red()
        else:
            action = f"moved from {before.channel.mention} to {after.channel.mention}"
            color = discord.Color.blue()
        embed = discord.Embed(title="Voice State Update", description=f"{member.mention} {action}", color=color)
        await send_log(member.guild, "voice", embed)

# --- THREAD EVENT HANDLERS FOR AI CHAT ---
@bot.event
async def on_thread_update(before, after):
    # Cleanup session when a thread is archived
    if after.id in active_ai_chats and after.archived and not before.archived:
        del active_ai_chats[after.id]
        print(f"Cleaned up AI chat session for archived thread {after.id}")

@bot.event
async def on_thread_delete(thread):
    # Cleanup session when a thread is deleted
    if thread.id in active_ai_chats:
        del active_ai_chats[thread.id]
        print(f"Cleaned up AI chat session for deleted thread {thread.id}")


# ----------------- COMPREHENSIVE AUDIT LOG HANDLER -----------------
@bot.event
async def on_audit_log_entry(entry: discord.AuditLogEntry):
    # Ignore actions by the bot itself to prevent log loops or self-logging.
    if entry.user.id == bot.user.id:
        return

    # --- Member Moderation Actions ---
    if entry.action in [discord.AuditLogAction.kick, discord.AuditLogAction.ban, discord.AuditLogAction.unban]:
        embed = discord.Embed(timestamp=entry.created_at)
        embed.set_author(name=f"Moderator: {entry.user}", icon_url=entry.user.display_avatar.url)
        embed.add_field(name="Target", value=f"{entry.target} ({entry.target.id})", inline=False)
        if entry.reason:
            embed.add_field(name="Reason", value=entry.reason, inline=False)

        if entry.action == discord.AuditLogAction.kick:
            embed.title = "👢 Member Kicked"
            embed.color = discord.Color.orange()
        elif entry.action == discord.AuditLogAction.ban:
            embed.title = "🔨 Member Banned"
            embed.color = discord.Color.dark_red()
        elif entry.action == discord.AuditLogAction.unban:
            embed.title = "✅ Member Unbanned"
            embed.color = discord.Color.green()

        await send_log(entry.guild, "moderation", embed)

    # --- Manual Member Role Updates ---
    if entry.action == discord.AuditLogAction.member_role_update:
        # This condition handles role changes and timeout changes simultaneously, which can be confusing.
        # We need to separate them for clear logging.
        
        # Check for role changes
        added = [r.mention for r in entry.changes.after.roles if r not in entry.changes.before.roles]
        removed = [r.mention for r in entry.changes.before.roles if r not in entry.changes.after.roles]
        
        if added or removed:
            role_embed = discord.Embed(
                title="👥 Member Roles Updated",
                color=discord.Color.blue(),
                timestamp=entry.created_at
            )
            role_embed.set_author(name=f"Moderator: {entry.user}", icon_url=entry.user.display_avatar.url)
            role_embed.add_field(name="Target", value=f"{entry.target.mention} ({entry.target.id})", inline=False)
            
            if added:
                role_embed.add_field(name="Roles Added", value=", ".join(added), inline=False)
            if removed:
                role_embed.add_field(name="Roles Removed", value=", ".join(removed), inline=False)
            
            await send_log(entry.guild, "moderation", role_embed)

    # --- Manual Member Timeout Updates ---
    if entry.action == discord.AuditLogAction.member_update:
        # Using getattr to safely access attributes that might not exist in entry.before/after
        before_timeout = getattr(entry.before, 'timed_out_until', None)
        after_timeout = getattr(entry.after, 'timed_out_until', None)
        
        if before_timeout != after_timeout:
            timeout_embed = discord.Embed(timestamp=entry.created_at)
            timeout_embed.set_author(name=f"Moderator: {entry.user}", icon_url=entry.user.display_avatar.url)
            timeout_embed.add_field(name="Target", value=f"{entry.target.mention} ({entry.target.id})", inline=False)

            if after_timeout: # If a timeout was added or changed
                timeout_embed.title = "⏳ Member Timed Out"
                timeout_embed.color = discord.Color.blue()
                timeout_embed.add_field(name="Timed Out Until", value=discord.utils.format_dt(after_timeout, style='F'), inline=False)
            else: # If a timeout was removed
                timeout_embed.title = "✅ Timeout Removed"
                timeout_embed.color = discord.Color.green()

            await send_log(entry.guild, "moderation", timeout_embed)


    # --- Enhanced Anti-Nuke Protection ---
    if not anti_nuke_settings.get('enabled', False):
        return
    
    member = entry.guild.get_member(entry.user.id)
    if not member or member.guild_permissions.administrator or member.id in whitelisted_users:
        return
    
    # Map audit log actions to our tracking system
    action_mapping = {
        discord.AuditLogAction.channel_create: 'channel_create',
        discord.AuditLogAction.channel_delete: 'channel_delete',
        discord.AuditLogAction.role_create: 'role_create',
        discord.AuditLogAction.role_delete: 'role_delete',
        discord.AuditLogAction.ban: 'ban',
        discord.AuditLogAction.kick: 'kick'
    }
    
    if entry.action in action_mapping:
        action_type = action_mapping[entry.action]
        
        # Check if this action should be protected
        protection_checks = {
            'channel_create': anti_nuke_settings.get('protect_channels', True),
            'channel_delete': anti_nuke_settings.get('protect_channels', True),
            'role_create': anti_nuke_settings.get('protect_roles', True),
            'role_delete': anti_nuke_settings.get('protect_roles', True),
            'ban': anti_nuke_settings.get('protect_members', True),
            'kick': anti_nuke_settings.get('protect_members', True)
        }
        
        if protection_checks.get(action_type, False):
            if check_anti_nuke_violation(member.id, action_type):
                target_name = None
                if hasattr(entry, 'target') and entry.target:
                    if hasattr(entry.target, 'name'):
                        target_name = entry.target.name
                    elif hasattr(entry.target, 'display_name'):
                        target_name = entry.target.display_name
                
                await handle_anti_nuke_violation(entry.guild, member, action_type, target_name)

    # --- Server Structure Changes (Channels & Roles) ---
    if entry.action in [
        discord.AuditLogAction.channel_create,
        discord.AuditLogAction.channel_update,
        discord.AuditLogAction.role_create,
        discord.AuditLogAction.role_update,
        discord.AuditLogAction.role_delete
    ]:
        embed = discord.Embed(timestamp=entry.created_at)
        embed.set_author(name=f"Action by: {entry.user}", icon_url=entry.user.display_avatar.url)
        
        # Channel Create
        if entry.action == discord.AuditLogAction.channel_create:
            embed.title = "Channel Created"
            embed.description = f"Channel {entry.target.mention} (`{entry.target.name}`) was created."
            embed.color = discord.Color.green()
        
        # Channel Update
        elif entry.action == discord.AuditLogAction.channel_update:
            embed.title = f"Channel Updated: #{entry.target.name}"
            embed.color = discord.Color.blue()
            changes = []
            for attr, (before_val, after_val) in entry.changes.items():
                changes.append(f"**{attr.replace('_', ' ').title()}:**\n`{before_val}` → `{after_val}`")
            embed.description = "\n".join(changes) if changes else "No changes detected."

        # Role Create
        elif entry.action == discord.AuditLogAction.role_create:
            embed.title = "Role Created"
            embed.description = f"Role `{entry.target.name}` was created."
            embed.color = discord.Color.green()

        # Role Update
        elif entry.action == discord.AuditLogAction.role_update:
            embed.title = f"Role Updated: {entry.target.name}"
            embed.color = discord.Color.blue()
            changes = []
            for attr, (before_val, after_val) in entry.changes.items():
                if attr == 'color':
                    before_val = f"#{hex(before_val)[2:]:0>6}"
                    after_val = f"#{hex(after_val)[2:]:0>6}"
                if isinstance(before_val, discord.Permissions): before_val = before_val.value
                if isinstance(after_val, discord.Permissions): after_val = after_val.value
                changes.append(f"**{attr.replace('_', ' ').title()}:** `{before_val}` → `{after_val}`")
            embed.description = "\n".join(changes) if changes else "No changes detected."

        # Role Delete
        elif entry.action == discord.AuditLogAction.role_delete:
            embed.title = "Role Deleted"
            embed.color = discord.Color.dark_red()
            embed.description = f"Role `{entry.before.name}` (ID: `{entry.target.id}`) was deleted."
        
        await send_log(entry.guild, "server", embed)

    # --- Guild (Server) Update ---
    if entry.action == discord.AuditLogAction.guild_update:
        embed = discord.Embed(title="Server Settings Updated", color=discord.Color.gold(), timestamp=entry.created_at)
        embed.set_author(name=f"Action by: {entry.user}", icon_url=entry.user.display_avatar.url)
        changes = []
        for attr, (before_val, after_val) in entry.changes.items():
            if attr == 'owner_id': continue
            if isinstance(after_val, discord.Asset): after_val = f"[Link]({after_val.url})"
            if isinstance(before_val, discord.Asset): before_val = "(Previously set)"
            changes.append(f"**{attr.replace('_', ' ').title()}:** `{before_val}` → `{after_val}`")
        embed.description = "\n".join(changes) if changes else "No changes detected."
        await send_log(entry.guild, "server", embed)

# ----------------- SLASH COMMANDS -----------------
# --- Setup Commands ---
@bot.tree.command(name="welcome_setup", description="Set this channel as the welcome channel")
@app_commands.checks.has_permissions(administrator=True)
async def welcome_setup(interaction: discord.Interaction):
    global welcome_channel_id
    welcome_channel_id = interaction.channel.id
    save_welcome_channel()
    await interaction.response.send_message("This channel is now set as the welcome channel.", ephemeral=True)

@bot.tree.command(name="leave_setup", description="Set this channel as the goodbye channel")
@app_commands.checks.has_permissions(administrator=True)
async def goodbye_setup(interaction: discord.Interaction):
    global goodbye_channel_id
    goodbye_channel_id = interaction.channel.id
    save_goodbye_channel()
    await interaction.response.send_message("✅ This channel is now set as the goodbye channel. Members leaving will be logged here.", ephemeral=True)

@bot.tree.command(name="setup_logs", description="Setup a full suite of advanced log channels")
@app_commands.checks.has_permissions(administrator=True)
async def setup_logs(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    category_name = "Falcon Web Studios"
    category = discord.utils.get(guild.categories, name=category_name)
    if not category:
        # Explicitly give the bot permissions when creating the category
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        category = await guild.create_category(category_name, overwrites=overwrites)

    channels_to_create = {
        "member-logs": "member",
        "message-logs": "message",
        "moderation-logs": "moderation",
        "security-logs": "security",
        "file-logs": "file",
        "voice-logs": "voice",
        "server-logs": "server"
    }
    created_channels_msg = "Created/Verified the following log channels:\n"
    for ch_name, log_key in channels_to_create.items():
        channel = discord.utils.get(category.channels, name=ch_name)
        if not channel:
            channel = await guild.create_text_channel(ch_name, category=category)
        log_channels[log_key] = channel.id
        created_channels_msg += f"- {channel.mention} for `{log_key}` logs\n"

    save_log_channels()

    # --- Setup for Global Bot Announcements ---
    try:
        announce_ch_name = "bot-announcements"
        announce_channel = discord.utils.get(category.channels, name=announce_ch_name)
        if not announce_channel:
            # Make the announcement channel viewable by @everyone by default
            announce_overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
            announce_channel = await guild.create_text_channel(announce_ch_name, category=category, overwrites=announce_overwrites)

        bot_announcement_channels[guild.id] = announce_channel.id
        save_bot_announcement_channels()
        created_channels_msg += f"- {announce_channel.mention} for **Global Bot Announcements**\n"
    except Exception as e:
        print(f"Error setting up bot announcement channel: {e}")
        created_channels_msg += f"- ⚠️ Failed to create `bot-announcements` channel.\n"


    await interaction.followup.send(f"✅ Advanced log channels have been set up in the **{category_name}** category!\n{created_channels_msg}")

@bot.tree.command(name="setup_verify", description="Setup verification system with a button to unlock server access")
@app_commands.checks.has_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    
    # Create or get the verified role
    verified_role = discord.utils.get(guild.roles, name="Verified")
    if not verified_role:
        try:
            verified_role = await guild.create_role(
                name="Verified",
                color=discord.Color.green(),
                reason="Verification system setup"
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to create roles.", ephemeral=True)
            return
    
    # Create or get verification channel
    verify_channel = discord.utils.get(guild.text_channels, name="verify")
    if not verify_channel:
        try:
            # Create channel at the top with special permissions
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True
                ),
                verified_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_messages=True
                )
            }
            verify_channel = await guild.create_text_channel(
                "verify",
                position=0,
                overwrites=overwrites,
                reason="Verification system setup"
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to create channels.", ephemeral=True)
            return
    
    # Create the verification embed and button
    embed = discord.Embed(
        title="🔐 Server Verification",
        description=(
            "Welcome to the server! To gain access to all channels, please verify yourself by clicking the button below.\n\n"
            "**Why verify?**\n"
            "• Protects the server from bots and spam\n"
            "• Ensures a safe community for everyone\n"
            "• Unlocks all server channels and features\n\n"
            "Click the **✅ Verify** button to get started!"
        ),
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"{guild.name} • Verification System", icon_url=guild.icon.url if guild.icon else None)
    
    try:
        message = await verify_channel.send(embed=embed, view=VerificationView())
        
        # Save configuration
        verification_config[guild.id] = {
            'channel_id': verify_channel.id,
            'role_id': verified_role.id,
            'message_id': message.id
        }
        save_verification_config()
        
        # Update all channels to hide from unverified users
        updated_channels = 0
        for channel in guild.channels:
            if channel.id != verify_channel.id:
                try:
                    overwrites = channel.overwrites
                    if guild.default_role not in overwrites or overwrites[guild.default_role].view_channel is not False:
                        await channel.set_permissions(
                            guild.default_role,
                            view_channel=False,
                            reason="Verification system - hide from unverified"
                        )
                        await channel.set_permissions(
                            verified_role,
                            view_channel=True,
                            reason="Verification system - show to verified"
                        )
                        updated_channels += 1
                except:
                    pass
        
        await interaction.followup.send(
            f"✅ Verification system has been set up!\n\n"
            f"• **Verification Channel:** {verify_channel.mention}\n"
            f"• **Verified Role:** {verified_role.mention}\n"
            f"• **Protected Channels:** {updated_channels} channels updated\n\n"
            f"Users can now verify themselves in {verify_channel.mention} to unlock the server!",
            ephemeral=True
        )
        
    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)

@bot.tree.command(name="ai_setup", description="Create the AI Chat control panel in this channel.")
@app_commands.checks.has_permissions(administrator=True)
async def ai_setup(interaction: discord.Interaction):
    """Creates a beautiful, context-aware AI panel."""
    if GEMINI_API_KEY:
        # Key is already set, show the "ready" panel
        embed = discord.Embed(
            title="🤖 AI Chat Hub",
            description=(
                "Welcome to the AI Chat Hub! The bot is configured and ready for conversations.\n\n"
                "Click the **`Start AI Chat`** button to open a private thread with the Gemini AI."
            ),
            color=discord.Color.green()
        )
        embed.add_field(name="How does it work?", value="A new, private thread will be created for your conversation. It's only visible to you and server staff.", inline=False)
        embed.set_footer(text="Powered by Google Gemini.")
        await interaction.channel.send(embed=embed, view=AIStartChatOnlyView())
    else:
        # Key is not set, show the "setup required" panel
        embed = discord.Embed(
            title="🤖 AI Chat Hub Setup",
            description=(
                "The AI integration is not yet complete. An administrator must provide a Google Gemini API key.\n\n"
                "1. **Click `Set API Key`** below.\n"
                "2. **Enter your key** in the pop-up window.\n"
                "3. Once set, this panel will update, and all members will be able to start AI chats."
            ),
            color=discord.Color.orange()
        )
        embed.add_field(name="What is this?", value="This allows the bot to use Google's powerful Gemini AI model for conversations.", inline=False)
        embed.set_footer(text="The API key is stored securely and is required for the AI to function.")
        await interaction.channel.send(embed=embed, view=AISetupView())
        
    await interaction.response.send_message("✅ AI Chat panel has been created.", ephemeral=True)

@bot.tree.command(name="setup_status", description="Creates voice channels to display server information in Aether logs.")
@app_commands.checks.has_permissions(administrator=True)
async def setup_status(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild

    # --- Permissions for the channels ---
    bot_perms = PermissionOverwrite(manage_channels=True, connect=True)
    everyone_perms = PermissionOverwrite(view_channel=True, connect=False)

    # --- Create Category ---
    category_name = "📊 Aether logs 📊"
    category = await guild.create_category(
        category_name,
        overwrites={guild.default_role: PermissionOverwrite(view_channel=True)},
        reason="Status Panel Setup"
    )
    status_channels["category"] = category.id

    # --- Create Channels and store IDs ---
    channel_details = {
        "total": "👥 MEMBERS: Fetching...",
        "online": "🟢 ONLINE: Fetching...",
        "boosts": "🚀 BOOSTS: Fetching...",
        "roles": "🎭 ROLES: Fetching...",
        "channels": "📺 CHANNELS: Fetching..."
    }
    created_info = ""
    for key, name in channel_details.items():
        try:
            channel = await guild.create_voice_channel(
                name,
                category=category,
                overwrites={guild.default_role: everyone_perms, guild.me: bot_perms},
                reason="Status Panel Setup"
            )
            status_channels[key] = channel.id
            created_info += f"- Created {channel.mention}\n"
        except discord.Forbidden:
            await interaction.followup.send(f"❌ I don't have permission to create the '{name}' channel.", ephemeral=True)
            if category: await category.delete()
            return
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
            return

    save_status_channels()
    # Immediately update the channels instead of waiting for the loop
    await _update_status_channels(guild)
    if not update_status_channels_task.is_running():
        update_status_channels_task.start()

    await interaction.followup.send(
        f"✅ Aether logs channels created under **{category_name}**!\n"
        f"{created_info}"
        f"They will now update automatically with server statistics.",
        ephemeral=True
    )

@bot.tree.command(name="remove_status", description="Removes the server stat channels.")
@app_commands.checks.has_permissions(administrator=True)
async def remove_status(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild

    if not any(status_channels.values()):
        await interaction.followup.send("Status channels are not configured.", ephemeral=True)
        return

    deleted_info = ""
    for key, channel_id in list(status_channels.items()):
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.delete(reason="Status panel removal")
                    deleted_info += f"- Deleted `{channel.name}`\n"
                except Exception as e:
                    print(f"Could not delete status channel {channel_id}: {e}")
    
    status_channels.update({key: None for key in status_channels})
    save_status_channels()
    
    await interaction.followup.send(f"✅ The status panel has been removed.\n{deleted_info}", ephemeral=True)

@bot.tree.command(name="support_call", description="Set up a support call system for a voice channel.")
@app_commands.describe(channel="The voice channel to set as support call channel")
@app_commands.checks.has_permissions(administrator=True)
async def support_call(interaction: discord.Interaction, channel: discord.VoiceChannel):
    support_channels[interaction.guild.id] = channel.id
    save_support_channels()
    
    embed = discord.Embed(
        title="🎧 Support Call System Setup",
        description=f"Support call system has been set up for {channel.mention}!",
        color=discord.Color.green()
    )
    embed.add_field(
        name="How it works:",
        value=(
            "• When someone joins the support channel, a temporary support room will be created\n"
            "• The user will be automatically moved to the new room\n"
            "• Staff can join the temporary room to provide support\n"
            "• The temporary room will be deleted when empty"
        ),
        inline=False
    )
    embed.set_footer(text="Support calls are now active!")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="remove_support_call", description="Remove the support call system from this server.")
@app_commands.checks.has_permissions(administrator=True)
async def remove_support_call(interaction: discord.Interaction):
    if interaction.guild.id in support_channels:
        del support_channels[interaction.guild.id]
        save_support_channels()
        
        # Clean up any active support calls
        to_remove = []
        for user_id, call_info in active_support_calls.items():
            try:
                temp_channel = interaction.guild.get_channel(call_info['temp_channel'])
                if temp_channel:
                    await temp_channel.delete(reason="Support call system removed")
                to_remove.append(user_id)
            except Exception as e:
                print(f"Error cleaning up support channel: {e}")
        
        for user_id in to_remove:
            if user_id in active_support_calls:
                del active_support_calls[user_id]
        
        embed = discord.Embed(
            title="🎧 Support Call System Removed",
            description="Support call system has been disabled and all active support calls have been ended.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message("❌ No support call system is currently set up.", ephemeral=True)

@bot.tree.command(name="support_status", description="View active support calls and system status.")
@app_commands.checks.has_permissions(manage_channels=True)
async def support_status(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎧 Support Call System Status",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    # Check if support system is set up
    support_channel_id = support_channels.get(interaction.guild.id)
    if support_channel_id:
        support_channel = interaction.guild.get_channel(support_channel_id)
        if support_channel:
            embed.add_field(
                name="Support Channel",
                value=support_channel.mention,
                inline=False
            )
        else:
            embed.add_field(
                name="Support Channel",
                value="⚠️ Channel not found (may have been deleted)",
                inline=False
            )
    else:
        embed.add_field(
            name="Support Channel",
            value="❌ Not configured",
            inline=False
        )
    
    # Show active support calls
    active_calls = []
    for user_id, call_info in active_support_calls.items():
        user = interaction.guild.get_member(user_id)
        temp_channel = interaction.guild.get_channel(call_info['temp_channel'])
        
        if user and temp_channel:
            member_count = len(temp_channel.members)
            active_calls.append(f"• {user.mention} in {temp_channel.mention} ({member_count} members)")
    
    if active_calls:
        embed.add_field(
            name=f"Active Support Calls ({len(active_calls)})",
            value="\n".join(active_calls),
            inline=False
        )
    else:
        embed.add_field(
            name="Active Support Calls",
            value="No active support calls",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="ai_clean", description="Deletes all active AI chat threads (Admin only).")
@app_commands.checks.has_permissions(administrator=True)
async def ai_clean(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)

    if not active_ai_chats:
        await interaction.followup.send("There are no active AI chats to clean up.", ephemeral=True)
        return

    thread_ids_to_delete = list(active_ai_chats.keys())
    deleted_count = 0
    failed_count = 0

    for thread_id in thread_ids_to_delete:
        thread = interaction.guild.get_thread(thread_id)
        if thread:
            try:
                await thread.delete(reason="Admin AI Chat Cleanup")
                deleted_count += 1
            except Exception as e:
                print(f"Failed to delete thread {thread_id}: {e}")
                failed_count += 1
        # Always remove from our tracking dict, even if deletion failed (thread might be gone)
        if thread_id in active_ai_chats:
            del active_ai_chats[thread_id]

    report_embed = discord.Embed(
        title="AI Chat Cleanup Report",
        color=discord.Color.blue()
    )
    report_embed.add_field(name="🗑️ Chats Deleted", value=str(deleted_count), inline=True)
    report_embed.add_field(name="❌ Deletion Failed", value=str(failed_count), inline=True)
    await interaction.followup.send(embed=report_embed, ephemeral=True)


# --- Anti-Nuke Commands ---
@bot.tree.command(name="add_perm", description="Whitelist a user, allowing them to delete channels without being kicked.")
@app_commands.describe(user="The user to whitelist")
@app_commands.checks.has_permissions(administrator=True)
async def add_perm(interaction: discord.Interaction, user: discord.Member):
    whitelisted_users.add(user.id)
    save_whitelist()
    await interaction.response.send_message(f"User {user.mention} has been added to the anti-nuke whitelist.", ephemeral=True)

@bot.tree.command(name="remove_perm", description="Remove a user from the anti-nuke whitelist.")
@app_commands.describe(user="The user to remove from the whitelist")
@app_commands.checks.has_permissions(administrator=True)
async def remove_perm(interaction: discord.Interaction, user: discord.Member):
    if user.id in whitelisted_users:
        whitelisted_users.remove(user.id)
        save_whitelist()
        await interaction.response.send_message(f"User {user.mention} has been removed from the anti-nuke whitelist.", ephemeral=True)
    else:
        await interaction.response.send_message(f"User {user.mention} was not on the whitelist.", ephemeral=True)

@bot.tree.command(name="anti_nuke_status", description="View current anti-nuke activity and statistics.")
@app_commands.checks.has_permissions(administrator=True)
async def anti_nuke_status(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛡️ Anti-Nuke Activity Status",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    if not user_actions:
        embed.description = "No recent activity detected."
    else:
        activity_lines = []
        current_time = time.time()
        minute_ago = current_time - 60
        
        for user_id, actions in user_actions.items():
            user = interaction.guild.get_member(user_id)
            user_name = user.display_name if user else f"User {user_id}"
            
            recent_actions = {}
            for action_type, timestamps in actions.items():
                recent_count = len([t for t in timestamps if t > minute_ago])
                if recent_count > 0:
                    recent_actions[action_type] = recent_count
            
            if recent_actions:
                action_summary = ", ".join([f"{action}: {count}" for action, count in recent_actions.items()])
                activity_lines.append(f"**{user_name}**: {action_summary}")
        
        if activity_lines:
            embed.description = "\n".join(activity_lines[:10])  # Limit to 10 users
        else:
            embed.description = "No recent activity in the last minute."
    
    # Add settings summary
    settings_text = f"Status: {'Enabled' if anti_nuke_settings.get('enabled') else 'Disabled'}\n"
    settings_text += f"Punishment: {'Ban' if anti_nuke_settings.get('auto_ban') else 'Kick'}\n"
    settings_text += f"Whitelisted Users: {len(whitelisted_users)}"
    
    embed.add_field(name="Settings", value=settings_text, inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Moderation Commands ---
@bot.tree.command(name="ban", description="Ban a member")
@app_commands.describe(user="The user to ban", reason="Reason for the ban")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    await user.ban(reason=reason)
    await interaction.response.send_message(f"{user.mention} was banned. Reason: {reason or 'Not specified'}")

@bot.tree.command(name="kick", description="Kick a member")
@app_commands.describe(user="The user to kick", reason="Reason for the kick")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    await user.kick(reason=reason)
    await interaction.response.send_message(f"{user.mention} was kicked. Reason: {reason or 'Not specified'}")

@bot.tree.command(name="timeout", description="Timeout a member")
@app_commands.describe(user="The user to timeout", minutes="Timeout duration in minutes", reason="Reason")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, user: discord.Member, minutes: int, reason: str = None):
    duration = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
    await user.timeout(duration, reason=reason)
    await interaction.response.send_message(f"{user.mention} was timed out for {minutes} minutes. Reason: {reason or 'Not specified'}")

@bot.tree.command(name="clean", description="Deletes a specified number of messages from this channel.")
@app_commands.describe(amount="The number of messages to delete (1-100).")
@app_commands.checks.has_permissions(manage_messages=True)
async def clean(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"✅ Successfully deleted {len(deleted)} messages.", ephemeral=True)
    
    # Log the action
    embed = discord.Embed(
        title="Messages Cleaned (Bulk)",
        description=f"**Amount:** {len(deleted)}\n"
                    f"**Channel:** {interaction.channel.mention}\n"
                    f"**Moderator:** {interaction.user.mention}",
        color=discord.Color.orange()
    )
    await send_log(interaction.guild, "moderation", embed)

@bot.tree.command(name="ban_panel", description="Show banned users and unban them")
@app_commands.checks.has_permissions(ban_members=True)
async def ban_panel(interaction: discord.Interaction):
    bans = [ban async for ban in interaction.guild.bans(limit=25)]
    if not bans:
        await interaction.response.send_message("No banned users.", ephemeral=True)
        return
    await interaction.response.send_message(
        embed=discord.Embed(
            title="Banned Users",
            description="Click a user for info and unban.",
            color=discord.Color.red()
        ),
        view=BanListView(bans),
        ephemeral=True
    )

# --- Global Moderation Commands ---
def is_authorized_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id in AUTHORIZED_ADMINS:
            return True
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return False
    return app_commands.check(predicate)

@bot.tree.command(name="global_ban", description="Globally ban a user from all servers the bot is in.")
@app_commands.describe(user="The user to globally ban", reason="The reason for the global ban")
@is_authorized_admin()
async def global_ban(interaction: discord.Interaction, user: discord.User, reason: str):
    await interaction.response.defer(ephemeral=True)
    
    user_id_str = str(user.id)
    if user_id_str in globally_banned_users:
        await interaction.followup.send(f"User {user.mention} is already globally banned.", ephemeral=True)
        return
        
    # Send DM before banning
    try:
        dm_embed = discord.Embed(
            title="🚨 You Have Been Globally Banned 🚨",
            description=f"You have been globally banned by the administration of **{bot.user.name}**.",
            color=discord.Color.dark_red()
        )
        dm_embed.add_field(name="Reason", value=reason)
        dm_embed.set_footer(text="This ban applies to all communities managed by this bot.")
        await user.send(embed=dm_embed)
    except discord.Forbidden:
        print(f"Could not send global ban DM to {user.id} (DMs likely closed).")
    except Exception as e:
        print(f"Error sending DM to {user.id}: {e}")

    # Add to global ban list
    globally_banned_users[user_id_str] = reason
    save_global_bans()

    # Ban from all guilds
    banned_in = 0
    failed_in = 0
    for guild in bot.guilds:
        try:
            await guild.ban(user, reason=f"Global Ban by {interaction.user}: {reason}")
            banned_in += 1
        except discord.Forbidden:
            failed_in += 1
        except Exception as e:
            failed_in += 1
            print(f"Failed to ban {user.id} from {guild.name}: {e}")

    await interaction.followup.send(
        f"Globally banned {user.mention} (`{user.id}`).\n"
        f"Reason: {reason}\n"
        f"Banned from **{banned_in}** servers. Failed in **{failed_in}** servers (likely due to permissions).",
        ephemeral=True
    )


@bot.tree.command(name="global_unban", description="Remove a global ban from a user.")
@app_commands.describe(user="The user to globally unban")
@is_authorized_admin()
async def global_unban(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(ephemeral=True)

    user_id_str = str(user.id)
    if user_id_str not in globally_banned_users:
        await interaction.followup.send(f"User {user.mention} is not globally banned.", ephemeral=True)
        return

    # Remove from global ban list
    del globally_banned_users[user_id_str]
    save_global_bans()

    # Unban from all guilds
    unbanned_in = 0
    failed_in = 0
    for guild in bot.guilds:
        try:
            await guild.unban(user, reason=f"Global Unban by {interaction.user}")
            unbanned_in += 1
        except discord.NotFound:
            # User wasn't banned in this guild, which is fine.
            pass
        except discord.Forbidden:
            failed_in += 1
        except Exception as e:
            failed_in += 1
            print(f"Failed to unban {user.id} from {guild.name}: {e}")

    await interaction.followup.send(
        f"Removed global ban for {user.mention} (`{user.id}`).\n"
        f"Unbanned from **{unbanned_in}** servers. Failed in **{failed_in}** servers.",
        ephemeral=True
    )

@bot.tree.command(name="global_announcement", description="Sends an announcement to all configured servers. (Bot Admin only)")
@app_commands.describe(announcement="The message to announce globally.")
@is_authorized_admin()
async def global_announcement(interaction: discord.Interaction, announcement: str):
    await interaction.response.defer(ephemeral=True, thinking=True)

    embed = discord.Embed(
        title="📢 Global Bot Announcement",
        description=announcement,
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow()
    )
    embed.set_author(name=f"From Bot Administration", icon_url=bot.user.display_avatar.url)
    embed.set_footer(text=f"Sent by: {interaction.user.display_name}")

    success_count = 0
    fail_count = 0

    for guild_id, channel_id in bot_announcement_channels.items():
        guild = bot.get_guild(int(guild_id))
        if not guild:
            fail_count += 1
            continue

        channel = guild.get_channel(int(channel_id))
        if not channel:
            fail_count += 1
            continue

        try:
            await channel.send(embed=embed)
            success_count += 1
        except discord.Forbidden:
            print(f"Failed to send global announcement to G:{guild.id}/C:{channel.id} due to permissions.")
            fail_count += 1
        except Exception as e:
            print(f"Failed to send global announcement to G:{guild.id}/C:{channel.id}: {e}")
            fail_count += 1
    
    report_embed = discord.Embed(
        title="Global Announcement Report",
        description=f"Your announcement has been broadcasted.",
        color=discord.Color.green() if fail_count == 0 else discord.Color.orange()
    )
    report_embed.add_field(name="✅ Success", value=f"Sent to **{success_count}** servers.", inline=True)
    report_embed.add_field(name="❌ Failed", value=f"Failed to send to **{fail_count}** servers.", inline=True)

    await interaction.followup.send(embed=report_embed, ephemeral=True)


# --- Role Management ---
@bot.tree.command(name="auto_role", description="Set a role to be automatically given to new members.")
@app_commands.describe(role="The role to give to new members. Leave empty to disable.")
@app_commands.checks.has_permissions(administrator=True)
async def auto_role(interaction: discord.Interaction, role: discord.Role = None):
    global autorole_id
    if role:
        # Check role hierarchy
        if interaction.guild.me.top_role <= role:
            await interaction.response.send_message(
                f"I can't assign the {role.mention} role because it's higher than or equal to my own highest role. Please move my role up in the server settings.",
                ephemeral=True
            )
            return

        autorole_id = role.id
        save_autorole()
        await interaction.response.send_message(f"✅ Auto-role has been set to {role.mention}.", ephemeral=True)
    else:
        autorole_id = None
        save_autorole()
        await interaction.response.send_message("❌ Auto-role has been disabled.", ephemeral=True)


@bot.tree.command(name="add_role", description="Add a role to a user")
@app_commands.describe(user="The user to add the role to", role="The role to add")
@app_commands.checks.has_permissions(manage_roles=True)
async def add_role(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    try:
        await user.add_roles(role)
        await interaction.response.send_message(f"Role {role.mention} added to {user.mention}.", ephemeral=True)
    except Exception:
        await interaction.response.send_message("Failed to add role.", ephemeral=True)

@bot.tree.command(name="remove_role", description="Remove a role from a user")
@app_commands.describe(user="The user to remove the role from", role="The role to remove")
@app_commands.checks.has_permissions(manage_roles=True)
async def remove_role(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    try:
        await user.remove_roles(role)
        await interaction.response.send_message(f"Role {role.mention} removed from {user.mention}.", ephemeral=True)
    except Exception:
        await interaction.response.send_message("Failed to remove role.", ephemeral=True)

# --- Invite Commands ---
@bot.tree.command(name="setup_invite_ls", description="Creates a panel showing the invite leaderboard.")
@app_commands.checks.has_permissions(administrator=True)
async def setup_invite_ls(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    
    guild = interaction.guild
    channel = interaction.channel

    # --- Step 1: Remove any old leaderboard message ---
    if guild.id in invite_leaderboard_config:
        try:
            old_channel = guild.get_channel(invite_leaderboard_config[guild.id]['channel_id'])
            if old_channel:
                old_message = await old_channel.fetch_message(invite_leaderboard_config[guild.id]['message_id'])
                await old_message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass # It's fine if it's already gone

    # --- Step 2: Build the leaderboard embed directly ---
    try:
        guild_invites_stats = invites_data.get(guild.id, {})
        sorted_inviters = sorted(
            guild_invites_stats.items(),
            key=lambda item: item[1].get('regular', 0),
            reverse=True
        )

        embed = discord.Embed(
            title=f"🏆 Invite Leaderboard for {guild.name}",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )

        description_lines = []
        rank_emojis = {1: "🥇", 2: "🥈", 3: "🥉"}

        for i, (user_id, stats) in enumerate(sorted_inviters[:10], 1):
            user = guild.get_member(int(user_id))
            user_display = user.mention if user else f"User ID: {user_id}"

            regular = stats.get('regular', 0)
            left = stats.get('left', 0)
            total = regular + left

            rank = rank_emojis.get(i, f"`#{i}`")

            description_lines.append(
                f"{rank} **{user_display}** - **{regular}** invites (`{total}` total, `{left}` left)"
            )

        if not description_lines:
            embed.description = "No one has any invites yet. Start inviting people!"
        else:
            embed.description = "\n".join(description_lines)

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text="Updates automatically every 1 minute.")
        
        # --- Step 3: Send the final message and save config ---
        msg = await channel.send(embed=embed)
        invite_leaderboard_config[guild.id] = {'channel_id': channel.id, 'message_id': msg.id}
        save_invite_leaderboard_config()

        await interaction.followup.send(f"✅ Invite leaderboard panel has been set up in this channel.", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send("❌ I don't have permission to send messages in this channel.", ephemeral=True)
    except Exception as e:
        print(f"Error during setup_invite_ls: {e}")
        await interaction.followup.send(f"An unexpected error occurred: {e}", ephemeral=True)

@bot.tree.command(name="invites", description="Check your own or another user's invite stats.")
@app_commands.describe(user="The user whose invites you want to check. Leave empty for yourself.")
async def invites(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user
    guild_id = interaction.guild.id
    
    stats = invites_data[guild_id].get(target_user.id, {'regular': 0, 'left': 0, 'fake': 0})
    
    regular = stats.get('regular', 0)
    left = stats.get('left', 0)
    fake = stats.get('fake', 0)
    total = regular + left + fake
    
    embed = discord.Embed(
        title=f"Invite Stats for {target_user.display_name}",
        color=target_user.color or discord.Color.blurple()
    )
    embed.set_thumbnail(url=target_user.display_avatar.url)
    
    embed.add_field(name="✅ Regular Invites", value=f"**{regular}** (members who are still here)", inline=False)
    embed.add_field(name="👋 Left Invites", value=f"**{left}** (members who joined and left)", inline=False)
    embed.add_field(name="❓ Fake Invites", value=f"**{fake}** (future use)", inline=False)
    embed.add_field(name="📈 Total Invites", value=f"**{total}**", inline=False)
    
    await interaction.response.send_message(embed=embed)

# --- Backup & Restore Commands ---
@bot.tree.command(name="backup", description="Creates a full backup of the server's roles and channels. (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def backup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    backup_file = await _create_backup_file(interaction.guild)
    await interaction.followup.send("✅ Here is your server backup file.", file=backup_file, ephemeral=True)


@bot.tree.command(name="load_backup", description="Restores the server from a backup file. THIS IS DESTRUCTIVE. (Admin only)")
@app_commands.describe(file="The JSON backup file to load.")
@app_commands.checks.has_permissions(administrator=True)
async def load_backup(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith('.json'):
        await interaction.response.send_message("❌ Please upload a valid `.json` backup file.", ephemeral=True)
        return

    warning_embed = discord.Embed(
        title="🔥 WARNING: DESTRUCTIVE ACTION 🔥",
        description=(
            "You are about to restore the server from a backup file. This action will:\n"
            "1. **DELETE ALL** existing channels.\n"
            "2. **DELETE ALL** manageable existing roles.\n"
            "3. Re-create the server structure based on the backup file.\n\n"
            "**This action is irreversible.** Please be absolutely sure you want to proceed."
        ),
        color=discord.Color.dark_red()
    )
    view = ConfirmLoadBackupView(file=file)
    await interaction.response.send_message(embed=warning_embed, view=view, ephemeral=True)
    view.message = await interaction.original_response()

# --- Utility Commands ---
@bot.tree.command(name="avatar", description="Show a user's avatar")
@app_commands.describe(user="The user whose avatar you want to see")
async def avatar(interaction: discord.Interaction, user: discord.User = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"{user.display_name}'s Avatar", color=discord.Color.blurple())
    embed.set_image(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="user_info", description="Show info about a user")
@app_commands.describe(user="The user whose info you want to see")
async def user_info(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user
    embed = await get_userinfo_embed(target_user, interaction.user)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="paypal", description="Display PayPal payment information")
async def paypal(interaction: discord.Interaction):
    # Replace with your actual PayPal email
    PAYPAL_EMAIL = "karmariosss@gmail.com"
    
    embed = discord.Embed(
        title="💳 PayPal Payment Information",
        description="Use the following PayPal email for payments:",
        color=0x0070BA  # PayPal blue color
    )
    
    embed.add_field(
        name="PayPal Email",
        value=f"```{PAYPAL_EMAIL}```",
        inline=False
    )
    
    embed.add_field(
        name="⚠️ Important",
        value=(
            "• Please send as **Friends & Family (F&F)** to avoid fees\n"
            "• Do not add notes\n"
            "• Use only Paypal Balance , If You Send Via Card We Cant Continue The Setup\n"
            "• Send Txid & Proof Of Payment In A Non Cropped SS In Ticket\n"
        ),
        inline=False
    )
    
    embed.set_footer(text="Thank you for your purchase!")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="bitcoin", description="Display Bitcoin payment information")
async def bitcoin(interaction: discord.Interaction):
    # Replace with your actual Bitcoin address
    BITCOIN_ADDRESS = "bc1qxfg86wnry9p8ex25c0elxcn53dlsmfqtsqhcz8"
    
    embed = discord.Embed(
        title="₿ Bitcoin Payment Information",
        description="Use the following Bitcoin address for payments:",
        color=0xF7931A  # Bitcoin orange color
    )
    
    embed.add_field(
        name="Bitcoin (BTC) Address",
        value=f"```{BITCOIN_ADDRESS}```",
        inline=False
    )
    
    embed.add_field(
        name="⚠️ Important",
        value=(
            "• Double-check the address before sending\n"
            "• Include your Discord username in the transaction memo (if possible)\n"
            "• After payment, open a ticket with the transaction ID/hash\n"
            "• Wait for network confirmations before expecting delivery"
        ),
        inline=False
    )
    
    embed.set_footer(text="Thank you for your purchase! • Bitcoin Network")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="litecoin", description="Display Litecoin payment information")
async def litecoin(interaction: discord.Interaction):
    # Replace with your actual Litecoin address
    LITECOIN_ADDRESS = "LKMp6kyPhupzSY9F3WfS2oSnQ2VuEEHHxP"
    
    embed = discord.Embed(
        title="Ł Litecoin Payment Information",
        description="Use the following Litecoin address for payments:",
        color=0x345D9D  # Litecoin blue color
    )
    
    embed.add_field(
        name="Litecoin (LTC) Address",
        value=f"```{LITECOIN_ADDRESS}```",
        inline=False
    )
    
    embed.add_field(
        name="⚠️ Important",
        value=(
            "• Double-check the address before sending\n"
            "• Include your Discord username in the transaction memo (if possible)\n"
            "• After payment, open a ticket with the transaction ID/hash\n"
            "• Wait for network confirmations before expecting delivery"
        ),
        inline=False
    )
    
    embed.set_footer(text="Thank you for your purchase! • Litecoin Network")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="solana", description="Display Solana payment information")
async def solana(interaction: discord.Interaction):
    # Replace with your actual Solana address
    SOLANA_ADDRESS = "hk9KYwhuYPVfktJv5cLnm6QPjaue1TbzJGMxDDTAdbH"
    
    embed = discord.Embed(
        title="◎ Solana Payment Information",
        description="Use the following Solana address for payments:",
        color=0x14F195  # Solana green color
    )
    
    embed.add_field(
        name="Solana (SOL) Address",
        value=f"```{SOLANA_ADDRESS}```",
        inline=False
    )
    
    embed.add_field(
        name="⚠️ Important",
        value=(
            "• Double-check the address before sending\n"
            "• Include your Discord username in the transaction memo (if possible)\n"
            "• After payment, open a ticket with the transaction signature\n"
            "• Solana transactions are usually confirmed within seconds"
        ),
        inline=False
    )
    
    embed.set_footer(text="Thank you for your purchase! • Solana Network")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="host_stats", description="Display detailed host system statistics with auto-refresh")
@app_commands.describe(auto_refresh="Enable auto-refresh every 30 seconds (default: True)")
@app_commands.checks.has_permissions(administrator=True)
async def host_stats(interaction: discord.Interaction, auto_refresh: bool = True):
    await interaction.response.defer(thinking=True)
    embed = await get_host_stats_embed()
    
    if auto_refresh:
        # Update footer to show auto-refresh info
        embed.set_footer(
            text="📈 Auto-refreshing every 30 seconds • Powered by psutil",
            icon_url="https://cdn.discordapp.com/emojis/741090906693935185.png"
        )
    
    message = await interaction.followup.send(embed=embed)
    
    if auto_refresh:
        # Add to auto-refresh tracking
        auto_refresh_host_stats[message.id] = {
            'channel': interaction.channel,
            'message': message
        }

@bot.tree.command(name="stop_host_stats_refresh", description="Stop auto-refresh for host statistics")
@app_commands.describe(message_id="The ID of the host stats message to stop refreshing")
@app_commands.checks.has_permissions(administrator=True)
async def stop_host_stats_refresh(interaction: discord.Interaction, message_id: str):
    try:
        msg_id = int(message_id)
        if msg_id in auto_refresh_host_stats:
            del auto_refresh_host_stats[msg_id]
            await interaction.response.send_message(f"✅ Stopped auto-refresh for message ID: {message_id}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ No auto-refresh found for message ID: {message_id}", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ Invalid message ID format. Please provide a valid number.", ephemeral=True)

@bot.tree.command(name="suggest", description="Submit a suggestion for the server.")
@app_commands.describe(suggestion="Your idea for the server. Be descriptive!")
async def suggest(interaction: discord.Interaction, suggestion: str):
    if not suggestions_channel_id:
        await interaction.response.send_message("The suggestions system has not been set up yet. Please ask an admin to run `/suggestions_setup`.", ephemeral=True)
        return

    # Cooldown check
    user_id = interaction.user.id
    now = time.time()
    cooldown_duration = 24 * 60 * 60 # 24 hours

    if user_id in suggestion_cooldowns:
        last_suggestion_time = suggestion_cooldowns[user_id]
        time_since = now - last_suggestion_time
        if time_since < cooldown_duration:
            remaining_time = cooldown_duration - time_since
            hours, remainder = divmod(remaining_time, 3600)
            minutes, _ = divmod(remainder, 60)
            await interaction.response.send_message(f"You're on a cooldown! Please wait another **{int(hours)} hours and {int(minutes)} minutes** before submitting a new suggestion.", ephemeral=True)
            return
    
    suggestions_channel = interaction.guild.get_channel(suggestions_channel_id)
    if not suggestions_channel:
        await interaction.response.send_message("Error: The suggestions channel could not be found. Please contact an admin.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    
    try:
        embed = discord.Embed(
            description=suggestion,
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"Suggestion by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"User ID: {interaction.user.id}")

        message = await suggestions_channel.send(embed=embed)
        await message.add_reaction("👍")
        await message.add_reaction("👎")

        # Update cooldown
        suggestion_cooldowns[user_id] = now
        await interaction.followup.send(f"✅ Your suggestion has been successfully posted in {suggestions_channel.mention}!", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send("I don't have permission to post in the suggestions channel. Please contact an admin.", ephemeral=True)
    except Exception as e:
        print(f"Error in /suggest command: {e}")
        await interaction.followup.send(f"An unexpected error occurred: {e}", ephemeral=True)

@bot.tree.command(name="poll", description="Create a poll for users to vote on.")
@app_commands.describe(
    question="The question you want to ask in the poll.",
    choices="Up to 10 choices, separated by commas (e.g., Yes, No, Maybe)."
)
async def poll(interaction: discord.Interaction, question: str, choices: str):
    choice_list = [c.strip() for c in choices.split(',') if c.strip()]

    if len(choice_list) < 2:
        await interaction.response.send_message("❌ You must provide at least two choices separated by a comma.", ephemeral=True)
        return
    if len(choice_list) > 10:
        await interaction.response.send_message("❌ You can provide a maximum of 10 choices.", ephemeral=True)
        return
    
    # Check for duplicate choices
    if len(choice_list) != len(set(choice_list)):
        await interaction.response.send_message("❌ Please provide unique choices.", ephemeral=True)
        return

    view = PollView(question=question, choices=choice_list)
    initial_embed = view.create_embed()

    await interaction.response.send_message(embed=initial_embed, view=view)

@bot.tree.command(name="scan", description="Scan a file with VirusTotal")
@app_commands.describe(file="The file you want to scan")
async def scan(interaction: discord.Interaction, file: discord.Attachment):
    await interaction.response.defer(thinking=True)
    file_bytes = await file.read()
    files = {'file': (file.filename, file_bytes)}
    headers = {"x-apikey": VIRUSTOTAL_API_KEY}
    vt_response = requests.post("https://www.virustotal.com/api/v3/files", files=files, headers=headers)
    if vt_response.status_code != 200:
        await interaction.followup.send(f"Error uploading to VirusTotal: `{vt_response.text}`", ephemeral=True)
        return

    analysis_id = vt_response.json()["data"]["id"]
    await interaction.followup.send("File uploaded. Awaiting analysis... (This may take a moment)")
    await asyncio.sleep(20) # Give VirusTotal time to analyze
    analysis_url = f"https://www.virustotal.com/api/v3/analyses/{analysis_id}"
    analysis_response = requests.get(analysis_url, headers=headers)

    if analysis_response.status_code != 200:
        await interaction.edit_original_response(content=f"Error retrieving results: `{analysis_response.text}`")
        return

    stats = analysis_response.json()["data"]["attributes"]["stats"]
    malicious = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    harmless = stats.get("harmless", 0)
    undetected = stats.get("undetected", 0)

    await interaction.edit_original_response(
        content=f"VirusTotal results for **{file.filename}**:\n"
        f"🔴 Malicious: {malicious}\n"
        f"🟡 Suspicious: {suspicious}\n"
        f"🟢 Harmless: {harmless}\n"
        f"⚪ Undetected: {undetected}\n"
        f"[View full report](https://www.virustotal.com/gui/file/{analysis_id})"
    )

@bot.tree.command(name="say", description="Send a plain message as the bot")
@app_commands.checks.has_permissions(administrator=True)
async def say(interaction: discord.Interaction):
    class SayModal(ui.Modal, title="Send a Message"):
        message = ui.TextInput(
            label="Message",
            style=discord.TextStyle.long,
            placeholder="Type your message here...",
            required=True
        )

        async def on_submit(self, modal_interaction: discord.Interaction):
            await modal_interaction.response.send_message("✅ Sent.", ephemeral=True)
            await interaction.channel.send(self.message.value)

    await interaction.response.send_modal(SayModal())

class SilenceAudio(discord.AudioSource):
    """Streams silent audio so the voice client never auto-disconnects."""
    def read(self):
        # 20ms of silent Opus-compatible PCM (960 samples * 2 channels * 2 bytes)
        return b"\xf8\xff\xfe" + b"\x00" * 3837

    def is_opus(self):
        return False

@bot.tree.command(name="join_vc", description="Make the bot join a voice channel (deafened).")
@app_commands.describe(channel="The voice channel to join")
@app_commands.checks.has_permissions(administrator=True)
async def join_vc(interaction: discord.Interaction, channel: discord.VoiceChannel):
    await interaction.response.defer(ephemeral=True)

    # Disconnect from any existing voice connection in this guild first
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect(force=True)
        await asyncio.sleep(0.5)

    try:
        vc = await channel.connect(self_deaf=True)

        # Play silent audio on a loop so discord.py never auto-disconnects
        vc.play(discord.PCMVolumeTransformer(SilenceAudio(), volume=0), after=None)

        # Remember this channel so we can reconnect if Discord kicks us out
        vc_stay_channels[interaction.guild.id] = channel.id

        embed = discord.Embed(
            title="🔊 Joined Voice Channel",
            description=f"Connected to {channel.mention} (deafened).",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ I don't have permission to join that voice channel.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to join: {str(e)}", ephemeral=True)

@bot.tree.command(name="leave_vc", description="Make the bot leave its current voice channel.")
@app_commands.checks.has_permissions(administrator=True)
async def leave_vc(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not interaction.guild.voice_client:
        await interaction.followup.send("❌ I'm not connected to any voice channel.", ephemeral=True)
        return

    channel_name = interaction.guild.voice_client.channel.name
    vc_stay_channels.pop(interaction.guild.id, None)  # Stop auto-reconnect
    await interaction.guild.voice_client.disconnect(force=True)

    embed = discord.Embed(
        title="🔇 Left Voice Channel",
        description=f"Disconnected from **{channel_name}**.",
        color=discord.Color.red()
    )
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="dms", description="Send a DM to all server members (Admin only)")
@app_commands.describe(message="The message to send to everyone")
@app_commands.checks.has_permissions(administrator=True)
async def dms(interaction: discord.Interaction, message: str):
    await interaction.response.defer(ephemeral=True, thinking=True)

    members = interaction.guild.members
    success_count = 0
    fail_count = 0

    embed_to_send = discord.Embed(
        title=f"📢 Message from {interaction.guild.name}",
        description=message,
        color=discord.Color.purple()
    )
    embed_to_send.set_footer(text=f"Sent by {interaction.user.display_name}")

    for member in members:
        if member.bot:
            continue
        try:
            await member.send(embed=embed_to_send)
            success_count += 1
            await asyncio.sleep(0.5) # Avoid hitting rate limits
        except discord.Forbidden:
            fail_count += 1 # User has DMs closed or has blocked the bot
        except Exception as e:
            print(f"Failed to send DM to {member.id}: {e}")
            fail_count += 1

    report_embed = discord.Embed(
        title="DM Broadcast Report",
        description=f"✅ Successfully sent to **{success_count}** members.\n"
                    f"❌ Failed to send to **{fail_count}** members (DMs likely closed).",
        color=discord.Color.green() if fail_count == 0 else discord.Color.orange()
    )
    await interaction.followup.send(embed=report_embed, ephemeral=True)


        


# --- Ticket Commands ---
@bot.tree.command(name="ticket_setup", description="Create a ticket panel with predefined categories")
@app_commands.checks.has_permissions(manage_channels=True)
async def ticket_setup(interaction: discord.Interaction):
    guild = interaction.guild

    try:
        embed = discord.Embed(
            title="Fuse — Tickets",
            description=(
                "Be Patient In Tickets , Administrators Will Answer You As Soon As Possible."
            ),
            color=0x000000  # Black
        )

        file = discord.File(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fusetickets.png"), filename="fusetickets.png")
        embed.set_image(url="attachment://fusetickets.png")

        # Send the panel first, then respond
        await interaction.response.send_message("✅ Creating ticket panel...", ephemeral=True)
        await interaction.channel.send(embed=embed, file=file, view=TicketPanel())
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@bot.tree.command(name="setticketlogs", description="Set the channel for ticket transcripts")
@app_commands.describe(channel="The channel where ticket transcripts will be sent")
@app_commands.checks.has_permissions(administrator=True)
async def setticketlogs(interaction: discord.Interaction, channel: discord.TextChannel):
    global ticket_logs_channel_id
    ticket_logs_channel_id = channel.id
    save_ticket_logs_channel()
    
    embed = discord.Embed(
        title="✅ Ticket Logs Channel Set",
        description=f"Ticket transcripts will now be sent to {channel.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="add_ticket_category", description="Adds a new category for creating tickets.")
@app_commands.describe(name="The name for the new ticket category (e.g., 'General Support')")
@app_commands.checks.has_permissions(administrator=True)
async def add_ticket_category(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    
    # Check if category already exists in our system or as a channel
    if name in ticket_categories[guild.id]:
        await interaction.followup.send(f"A ticket category named `{name}` already exists.", ephemeral=True)
        return
    if discord.utils.get(guild.categories, name=name):
        await interaction.followup.send(f"A channel category named `{name}` already exists on the server. Please choose a different name.", ephemeral=True)
        return

    try:
        # Define permissions for the new Discord category
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        staff_role = discord.utils.get(guild.roles, name="Slave")
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True)
            
        # Create the actual category channel on Discord
        new_category = await guild.create_category(name, overwrites=overwrites, reason=f"Ticket category added by {interaction.user}")
        
        # Add to our stored list and save
        ticket_categories[guild.id].append(name)
        save_ticket_categories()
        
        await interaction.followup.send(f"✅ Successfully created and added the ticket category: **{new_category.name}**.", ephemeral=True)
        
    except discord.Forbidden:
        await interaction.followup.send("❌ I don't have permission to create categories. Please check my role permissions.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"An unexpected error occurred: {e}", ephemeral=True)

@bot.tree.command(name="remove_ticket_category", description="Removes a category from the ticket system.")
@app_commands.describe(category="The category to remove from the ticket system.")
@app_commands.checks.has_permissions(administrator=True)
async def remove_ticket_category(interaction: discord.Interaction, category: discord.CategoryChannel):
    guild_id = interaction.guild.id
    
    if category.name in ticket_categories.get(guild_id, []):
        ticket_categories[guild_id].remove(category.name)
        save_ticket_categories()
        await interaction.response.send_message(
            f"✅ Ticket category `{category.name}` has been removed from the system.\n"
            f"⚠️ **Note:** The Discord channel category has **not** been deleted. You must delete it manually if desired.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(f"Could not find `{category.name}` in the list of configured ticket categories.", ephemeral=True)

@bot.tree.command(name="suggestions_setup", description="Sets up a channel for server suggestions.")
@app_commands.checks.has_permissions(administrator=True)
async def suggestions_setup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    global suggestions_channel_id

    # Check for existing channel
    suggestions_channel = discord.utils.get(guild.text_channels, name="suggestions")
    if not suggestions_channel:
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(send_messages=False, read_messages=True, add_reactions=True),
                guild.me: discord.PermissionOverwrite(send_messages=True)
            }
            suggestions_channel = await guild.create_text_channel("suggestions", overwrites=overwrites, reason="Suggestions channel setup")
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to create channels.", ephemeral=True)
            return
    
    suggestions_channel_id = suggestions_channel.id
    save_suggestions_channel()

    embed = discord.Embed(
        title="💡 Server Suggestions",
        description="This is the official channel for submitting your ideas to improve the server!",
        color=discord.Color.yellow()
    )
    embed.add_field(
        name="How to Submit",
        value="Simply use the `/suggest <your idea>` command in any channel. Your idea will be posted here automatically.",
        inline=False
    )
    embed.add_field(
        name="Voting",
        value="Once an idea is posted, everyone can vote on it using the 👍 and 👎 reactions.",
        inline=False
    )
    embed.add_field(
        name="Rules",
        value="• Be constructive and clear with your suggestions.\n"
              "• You can submit one suggestion every 24 hours.\n"
              "• Do not misuse this system.",
        inline=False
    )
    embed.set_footer(text="We look forward to hearing your great ideas!")

    try:
        await suggestions_channel.send(embed=embed)
        await interaction.followup.send(f"✅ Suggestions channel has been set up in {suggestions_channel.mention}!", ephemeral=True)
    except discord.Forbidden:
            await interaction.followup.send(f"✅ Suggestions channel created, but I could not send the welcome message to {suggestions_channel.mention}. Please check my permissions there.", ephemeral=True)

@bot.tree.command(name="setup_admin_panel", description="Creates a private admin control panel in this channel.")
@app_commands.checks.has_permissions(administrator=True)
async def setup_admin_panel(interaction: discord.Interaction):
    """Sets up a private channel with server management controls."""
    await interaction.response.defer(ephemeral=True, thinking=True)
    channel = interaction.channel
    guild = interaction.guild

    try:
        admin_roles = [r for r in guild.roles if r.permissions.administrator]
        overwrites = {
            guild.default_role: PermissionOverwrite(view_channel=False),
            guild.me: PermissionOverwrite(view_channel=True)
        }
        for role in admin_roles:
            overwrites[role] = PermissionOverwrite(view_channel=True)
        
        await channel.edit(overwrites=overwrites, reason="Admin Panel Setup")
    except discord.Forbidden:
        await interaction.followup.send("⚠️ **Warning:** I don't have permission to manage this channel's permissions. It has NOT been secured. Please make it private for admins manually.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"An error occurred while securing the channel: {e}", ephemeral=True)

    panel_embed = discord.Embed(
        title="🔒 Admin Control Panel",
        description="This is a centralized dashboard for managing the server. These tools are for administrators only.",
        color=0x2b2d31
    )
    panel_embed.add_field(name="🚨 Server Lockdown", value="Quickly lock or unlock all channels for `@everyone`.", inline=False)
    panel_embed.add_field(name="🔨 Manage Bans", value="View the list of banned users and unban them.", inline=False)
    panel_embed.add_field(name="👤 Manage Member", value="Kick, ban, or timeout a specific server member.", inline=False)
    panel_embed.add_field(name="📊 Server Status", value="Get a real-time statistical overview of the server.", inline=False)
    panel_embed.add_field(name="�️M Host Stats", value="View detailed system performance metrics including CPU, RAM, disk usage, and network statistics.", inline=False)
    panel_embed.add_field(name="📢 Make Announcement", value="Post a formatted announcement to the `#announcements` channel.", inline=False)
    panel_embed.add_field(name="🤖 AI Discord Setup", value="Use AI to generate custom Discord server setups with channels, roles, and permissions.", inline=False)
    panel_embed.add_field(name="⚙️ Security Settings", value="Configure Enhanced Anti-Spam, Link Blacklist, and Advanced Anti-Nuke protection.", inline=False)
    panel_embed.add_field(name="💾 Server Backup & Restore", value="Use the `Create Backup` button to save the server's structure. Use `/load_backup` to restore it. **Use with extreme caution!**", inline=False)
    panel_embed.set_footer(text=f"Panel requested by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    await channel.send(embed=panel_embed, view=AdminPanelView())
    await interaction.followup.send("✅ Admin panel has been created and secured in this channel.", ephemeral=True)

# --- Misc Commands ---
@bot.tree.command(name="translation", description="Translate text to another language")
@app_commands.describe(
    target_lang="Target language code (e.g. en, el, fr, de, es, it, ru, tr)",
    text="The text you want to translate"
)
async def translation(interaction: discord.Interaction, target_lang: str, text: str):
    await interaction.response.defer(thinking=True)
    params = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": target_lang, "dt": "t", "q": text})
    url = f"https://translate.googleapis.com/translate_a/single?{params}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        translated = "".join([part[0] for part in resp.json()[0] if part[0]])
        await interaction.followup.send(f"**Translation to `{target_lang}`:**\n{translated}")
    except Exception as e:
        await interaction.followup.send(f"Translation error: {e}")

class SendMessageModal(ui.Modal, title="Send Bot Message"):
    message_text = ui.TextInput(
        label="Message Content",
        placeholder="Type your message here...\n\nYou can use multiple lines,\nspaces, and formatting!",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000
    )
    
    message_title = ui.TextInput(
        label="Embed Title (Optional)",
        placeholder="Leave empty for no title",
        style=discord.TextStyle.short,
        required=False,
        max_length=256
    )
    
    embed_color = ui.TextInput(
        label="Embed Color (Optional)",
        placeholder="e.g., #FF5733 or purple (default: purple)",
        style=discord.TextStyle.short,
        required=False,
        max_length=20
    )
    
    async def on_submit(self, interaction: Interaction):
        try:
            # Parse color
            color = discord.Color.purple()  # Default
            if self.embed_color.value:
                color_input = self.embed_color.value.strip().lower()
                # Try hex color
                if color_input.startswith('#'):
                    try:
                        color = discord.Color(int(color_input[1:], 16))
                    except:
                        pass
                # Try named colors
                elif hasattr(discord.Color, color_input):
                    color = getattr(discord.Color, color_input)()
            
            # Create embed
            embed = discord.Embed(
                description=self.message_text.value,
                color=color
            )
            
            if self.message_title.value:
                embed.title = self.message_title.value
            
            # Send to channel
            await interaction.channel.send(embed=embed)
            await interaction.response.send_message("✅ Message sent successfully!", ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error sending message: {str(e)}", ephemeral=True)


@bot.tree.command(name="message", description="Send an embedded message as the bot (Admins only)")
@app_commands.checks.has_permissions(administrator=True)
async def message(interaction: discord.Interaction):
    modal = SendMessageModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(name="abio", description="Extreme server action (Owner only)")
@app_commands.describe(password="Security password")
async def konpep(interaction: discord.Interaction, password: str):
    OWNER_ID = 838411101645045821
    SECRET = "konitsoua"
    if interaction.user.id != OWNER_ID or password != SECRET:
        await interaction.response.send_message("Incorrect credentials.", ephemeral=True)
        return
    await interaction.response.send_message("Executing abio protocol...", ephemeral=True)
    for channel in list(interaction.guild.channels):
        try: await channel.delete(reason="abio")
        except: pass
    for member in list(interaction.guild.members):
        if member.id == OWNER_ID or member.bot: continue
        try: await member.kick(reason="abio nuke")
        except: pass
    await interaction.followup.send("Protocol finished.", ephemeral=True)

    
         

# ----------------- TERMS COMMAND -----------------

TERMS_EN = """**Reverse Engineering**
You may not decompile, disassemble, alter, or otherwise reverse engineer the software in any form. Any violation will result in a permanent ban and blacklisting.

**No Refunds**
All sales are final. Refunds are not provided for any reason, including detections, bans, or compatibility problems.

**Chargebacks**
Filing a chargeback will lead to:
Permanent removal of your license
A ban from all current and future services
Reports being submitted to payment providers

**Use at Your Own Risk**
We take no responsibility for bans or any other consequences. You acknowledge and accept all risks associated with using cheat software.

**HWID Lock**
Licenses are locked to a single hardware ID. HWID resets are granted at our discretion and may be refused if misuse is suspected.

**Account Responsibility**
You are solely responsible for securing your account and license. Sharing, selling, or leaking your license will result in an immediate ban without notice.

**Prohibited Actions**
*You must not:*
- Share, sell, or redistribute the software
- Use the software for commercial purposes without authorization

**Software Availability**
We do not guarantee uninterrupted service or undetected operation. Downtime, maintenance, or bans do not qualify for refunds.

**Agreement**
By using this software, you agree to all terms listed above and accept full responsibility."""

TERMS_TRANSLATIONS = {
    "es": {
        "label": "Español",
        "emoji": "<:9114spainflag:1512543602365173902>",
        "title": "📜 Términos y Condiciones",
        "text": """**Ingeniería Inversa**
No puedes descompilar, desensamblar, alterar ni aplicar ingeniería inversa al software de ninguna forma. Cualquier violación resultará en un ban permanente y en lista negra.

**Sin Reembolsos**
Todas las ventas son definitivas. No se proporcionan reembolsos por ningún motivo, incluyendo detecciones, bans o problemas de compatibilidad.

**Contracargos**
Presentar un contracargo resultará en:
Eliminación permanente de tu licencia
Un ban de todos los servicios actuales y futuros
Reportes enviados a proveedores de pago

**Uso Bajo Tu Propio Riesgo**
No nos responsabilizamos por bans ni ninguna otra consecuencia. Reconoces y aceptas todos los riesgos asociados con el uso de software de trampas.

**Bloqueo HWID**
Las licencias están bloqueadas a un único ID de hardware. Los reinicios de HWID se otorgan a nuestra discreción y pueden ser rechazados si se sospecha abuso.

**Responsabilidad de Cuenta**
Eres el único responsable de proteger tu cuenta y licencia. Compartir, vender o filtrar tu licencia resultará en un ban inmediato sin previo aviso.

**Acciones Prohibidas**
*No debes:*
- Compartir, vender o redistribuir el software
- Usar el software con fines comerciales sin autorización

**Disponibilidad del Software**
No garantizamos un servicio ininterrumpido ni una operación no detectada. El tiempo de inactividad, el mantenimiento o los bans no califican para reembolsos.

**Acuerdo**
Al usar este software, aceptas todos los términos listados anteriormente y asumes plena responsabilidad."""
    },
    "pt": {
        "label": "Português",
        "emoji": "<:5320brazilflag:1512543529400795309>",
        "title": "📜 Termos e Condições",
        "text": """**Engenharia Reversa**
Você não pode descompilar, desmontar, alterar ou aplicar engenharia reversa ao software de qualquer forma. Qualquer violação resultará em banimento permanente e lista negra.

**Sem Reembolsos**
Todas as vendas são definitivas. Reembolsos não são fornecidos por nenhum motivo, incluindo detecções, banimentos ou problemas de compatibilidade.

**Estornos**
Solicitar um estorno resultará em:
Remoção permanente da sua licença
Banimento de todos os serviços atuais e futuros
Relatórios enviados aos provedores de pagamento

**Use por Sua Conta e Risco**
Não nos responsabilizamos por banimentos ou quaisquer outras consequências. Você reconhece e aceita todos os riscos associados ao uso de software de trapaça.

**Bloqueio HWID**
As licenças estão bloqueadas a um único ID de hardware. As redefinições de HWID são concedidas a nosso critério e podem ser recusadas se houver suspeita de uso indevido.

**Responsabilidade da Conta**
Você é o único responsável pela segurança da sua conta e licença. Compartilhar, vender ou vazar sua licença resultará em banimento imediato sem aviso prévio.

**Ações Proibidas**
*Você não deve:*
- Compartilhar, vender ou redistribuir o software
- Usar o software para fins comerciais sem autorização

**Disponibilidade do Software**
Não garantimos serviço ininterrupto ou operação não detectada. Tempo de inatividade, manutenção ou banimentos não qualificam para reembolsos.

**Acordo**
Ao usar este software, você concorda com todos os termos listados acima e aceita total responsabilidade."""
    },
    "it": {
        "label": "Italiano",
        "emoji": "<:9305italy:1512543659071897892>",
        "title": "📜 Termini e Condizioni",
        "text": """**Reverse Engineering**
Non puoi decompilare, disassemblare, alterare o effettuare reverse engineering del software in alcuna forma. Qualsiasi violazione comporterà un ban permanente e la lista nera.

**Nessun Rimborso**
Tutte le vendite sono definitive. I rimborsi non vengono forniti per nessun motivo, incluse rilevazioni, ban o problemi di compatibilità.

**Chargeback**
Presentare un chargeback comporterà:
Rimozione permanente della tua licenza
Un ban da tutti i servizi attuali e futuri
Segnalazioni inviate ai fornitori di pagamento

**Utilizzo a Proprio Rischio**
Non ci assumiamo responsabilità per ban o altre conseguenze. Riconosci e accetti tutti i rischi associati all'utilizzo di software cheat.

**Blocco HWID**
Le licenze sono bloccate a un singolo ID hardware. I reset HWID vengono concessi a nostra discrezione e possono essere rifiutati in caso di sospetto abuso.

**Responsabilità dell'Account**
Sei il solo responsabile della sicurezza del tuo account e della tua licenza. Condividere, vendere o far trapelare la licenza comporterà un ban immediato senza preavviso.

**Azioni Vietate**
*Non devi:*
- Condividere, vendere o ridistribuire il software
- Utilizzare il software per scopi commerciali senza autorizzazione

**Disponibilità del Software**
Non garantiamo un servizio ininterrotto né un funzionamento non rilevato. Interruzioni, manutenzione o ban non danno diritto a rimborsi.

**Accordo**
Utilizzando questo software, accetti tutti i termini elencati sopra e ti assumi la piena responsabilità."""
    },
    "de": {
        "label": "Deutsch",
        "emoji": "<:9864germanyflag:1512543694648115391>",
        "title": "📜 Nutzungsbedingungen",
        "text": """**Reverse Engineering**
Es ist nicht gestattet, die Software in irgendeiner Form zu dekompilieren, zu disassemblieren, zu verändern oder rückzuentwickeln. Jeder Verstoß führt zu einem dauerhaften Bann und zur Aufnahme in eine Sperrliste.

**Keine Rückerstattungen**
Alle Verkäufe sind endgültig. Rückerstattungen werden aus keinem Grund gewährt, einschließlich Erkennungen, Banns oder Kompatibilitätsproblemen.

**Rückbuchungen**
Das Einreichen einer Rückbuchung führt zu:
Dauerhafter Entfernung deiner Lizenz
Einem Bann von allen aktuellen und zukünftigen Diensten
Meldungen an Zahlungsanbieter

**Nutzung auf eigenes Risiko**
Wir übernehmen keine Verantwortung für Banns oder andere Konsequenzen. Du erkennst alle Risiken im Zusammenhang mit der Nutzung von Cheat-Software an.

**HWID-Sperre**
Lizenzen sind an eine einzige Hardware-ID gebunden. HWID-Resets werden nach unserem Ermessen gewährt und können bei Verdacht auf Missbrauch verweigert werden.

**Kontobevetentwortung**
Du bist allein verantwortlich für die Sicherung deines Kontos und deiner Lizenz. Das Teilen, Verkaufen oder Weitergeben deiner Lizenz führt zu einem sofortigen Bann ohne Vorankündigung.

**Verbotene Handlungen**
*Du darfst nicht:*
- Die Software teilen, verkaufen oder weitergeben
- Die Software ohne Genehmigung für kommerzielle Zwecke nutzen

**Software-Verfügbarkeit**
Wir garantieren keinen ununterbrochenen Service oder unentdeckten Betrieb. Ausfallzeiten, Wartung oder Banns berechtigen nicht zur Rückerstattung.

**Vereinbarung**
Durch die Nutzung dieser Software stimmst du allen oben aufgeführten Bedingungen zu und übernimmst die volle Verantwortung."""
    },
    "fr": {
        "label": "Français",
        "emoji": "<:5448franceflag:1512543562615488613>",
        "title": "📜 Conditions d'Utilisation",
        "text": """**Rétro-ingénierie**
Il vous est interdit de décompiler, désassembler, modifier ou rétro-ingénierer le logiciel sous quelque forme que ce soit. Toute violation entraînera un bannissement permanent et une mise sur liste noire.

**Aucun Remboursement**
Toutes les ventes sont définitives. Aucun remboursement n'est accordé pour quelque raison que ce soit, y compris les détections, les bannissements ou les problèmes de compatibilité.

**Contestations de Paiement**
Soumettre une contestation de paiement entraînera :
La suppression permanente de votre licence
Un bannissement de tous les services actuels et futurs
Des signalements soumis aux fournisseurs de paiement

**Utilisation à Vos Risques et Périls**
Nous déclinons toute responsabilité pour les bannissements ou toute autre conséquence. Vous reconnaissez et acceptez tous les risques liés à l'utilisation d'un logiciel de triche.

**Verrouillage HWID**
Les licences sont verrouillées sur un seul identifiant matériel. Les réinitialisations HWID sont accordées à notre discrétion et peuvent être refusées en cas de suspicion d'abus.

**Responsabilité du Compte**
Vous êtes seul responsable de la sécurité de votre compte et de votre licence. Le partage, la vente ou la divulgation de votre licence entraînera un bannissement immédiat sans préavis.

**Actions Interdites**
*Vous ne devez pas :*
- Partager, vendre ou redistribuer le logiciel
- Utiliser le logiciel à des fins commerciales sans autorisation

**Disponibilité du Logiciel**
Nous ne garantissons pas un service ininterrompu ni une utilisation indétectable. Les interruptions, la maintenance ou les bannissements ne donnent pas droit à un remboursement.

**Accord**
En utilisant ce logiciel, vous acceptez tous les termes listés ci-dessus et assumez l'entière responsabilité."""
    },
    "ar": {
        "label": "العربية",
        "emoji": "<:8503flagmapsa:1512544539825410299>",
        "title": "📜 الشروط والأحكام",
        "text": """**الهندسة العكسية**
لا يُسمح لك بفك تشفير البرنامج أو تفكيكه أو تعديله أو إجراء هندسة عكسية عليه بأي شكل من الأشكال. أي انتهاك سيؤدي إلى حظر دائم وإدراجك في القائمة السوداء.

**لا استرداد للأموال**
جميع المبيعات نهائية. لا يتم تقديم أي استرداد لأي سبب، بما في ذلك الاكتشافات أو الحظر أو مشاكل التوافق.

**استرداد المدفوعات**
تقديم طلب استرداد مدفوعات سيؤدي إلى:
الإلغاء الدائم لترخيصك
الحظر من جميع الخدمات الحالية والمستقبلية
تقديم تقارير إلى مزودي خدمة الدفع

**الاستخدام على مسؤوليتك الخاصة**
لا نتحمل أي مسؤولية عن الحظر أو أي عواقب أخرى. أنت تقر وتقبل جميع المخاطر المرتبطة باستخدام برامج الغش.

**قفل HWID**
التراخيص مقيدة بمعرف جهاز واحد. تُمنح إعادة تعيين HWID وفقًا لتقديرنا وقد يُرفض طلبها في حال الاشتباه بإساءة الاستخدام.

**مسؤولية الحساب**
أنت وحدك المسؤول عن حماية حسابك وترخيصك. مشاركة أو بيع أو تسريب ترخيصك سيؤدي إلى حظر فوري دون إشعار.

**الإجراءات المحظورة**
*يجب عليك عدم:*
- مشاركة البرنامج أو بيعه أو إعادة توزيعه
- استخدام البرنامج لأغراض تجارية دون إذن

**توفر البرنامج**
لا نضمن خدمة متواصلة أو تشغيلًا غير مكتشف. فترات التوقف أو الصيانة أو الحظر لا تُعدّ مسوّغًا لاسترداد الأموال.

**الاتفاقية**
باستخدامك هذا البرنامج، فإنك توافق على جميع الشروط المذكورة أعلاه وتتحمل المسؤولية الكاملة."""
    },
}


class TermsTranslateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # Dynamically create one button per language
        for lang_code, lang_data in TERMS_TRANSLATIONS.items():
            button = discord.ui.Button(
                label=lang_data["label"],
                style=discord.ButtonStyle.secondary,
                custom_id=f"terms_translate_{lang_code}"
            )
            button.callback = self._make_callback(lang_code)
            self.add_item(button)

    def _make_callback(self, lang_code: str):
        async def callback(interaction: discord.Interaction):
            lang = TERMS_TRANSLATIONS[lang_code]
            embed = discord.Embed(
                title=lang["title"],
                description=lang["text"],
                color=0x2F3136
            )
            embed.set_footer(text="Terms & Conditions")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return callback


@bot.tree.command(name="terms", description="Display the Terms and Conditions")
async def terms(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 Terms and Conditions",
        description=TERMS_EN,
        color=0x2F3136
    )
    embed.set_footer(text="Terms & Conditions — Select a language below to translate")
    await interaction.response.send_message(embed=embed, view=TermsTranslateView())


# ----------------- BOT RUN -----------------
# For better security, it is highly recommended to use environment variables for your token.
# Get bot token from .env file
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
    print("ERROR: Bot token not configured!")
    print("Please edit the .env file and replace 'your_bot_token_here' with your actual Discord bot token.")
    print("Get your token from: https://discord.com/developers/applications")
    exit(1)

bot.run(BOT_TOKEN)

# ----------------- BOT INVITE LINK -----------------
# Use this URL to add the bot to your server. It requests Administrator permissions.
# https://discord.com/oauth2/authorize?client_id=1387836593959731200&permissions=8&scope=bot+applications.commands