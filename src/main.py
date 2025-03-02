import logging
import json
import asyncio
import random
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
import requests
import discord
from discord import app_commands
from discord.ext import commands, tasks

# Load environment variables from .env file
load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL")
API_PASSWORD = os.getenv("API_PASSWORD")
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
LANGUAGE = os.getenv("LANGUAGE", "en")

# Enable basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load translations
def load_translations(language):
    with open(f'lang/{language}.json', 'r', encoding='utf-8') as file:
        return json.load(file)

translations = load_translations(LANGUAGE)

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents, sync_commands=True)
tracking_channel_id = None
status_message_id = None
server_offline_message_sent = False
webhook_message_id = None
server_start_time = None
server_online = False
cached_player_list = None

# Define emojis
GREEN_DOT = "<:green_circle:1252142135581163560>"
RED_DOT = "<:red_circle:1252142033758459011>"

def is_admin():
    """Check if the user has the admin role."""
    async def predicate(interaction: discord.Interaction):
        if interaction.guild is None:
            return False
        role = interaction.guild.get_role(ADMIN_ROLE_ID)
        if role is None:
            logging.error(f"Error: Admin role with id: {ADMIN_ROLE_ID} could not be found")
            return False
        return role in interaction.user.roles
    return app_commands.check(predicate)

async def send_webhook_message(message):
    """Sends a message to the Discord webhook."""
    global webhook_message_id
    try:
        data = {"content": message}
        response = requests.post(WEBHOOK_URL, json=data)
        response.raise_for_status()
        logging.info(f"Webhook message sent successfully, response: {response.status_code}")
        webhook_message_id = response.json()['id']
    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending webhook message: {e}")
        return False
    return True

async def remove_webhook_message():
    """Removes the message from the discord webhook"""
    global webhook_message_id
    try:
        response = requests.delete(f'{WEBHOOK_URL}/messages/{webhook_message_id}')
        response.raise_for_status()
        logging.info(f"Removed webhook message: {response.status_code}")
        webhook_message_id = None
    except requests.exceptions.RequestException as e:
        logging.error(f"Error removing webhook message: {e}")
        return False
    return True

async def fetch_player_data():
    """Fetches player count and player list data from the API with backoff retry."""
    global server_offline_message_sent, webhook_message_id, server_start_time, server_online, cached_player_list
    player_count_url = f"{API_BASE_URL}/player/count?password={API_PASSWORD}"
    player_list_url = f"{API_BASE_URL}/player/list?password={API_PASSWORD}"
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            count_response = requests.get(player_count_url, timeout=5)
            count_response.raise_for_status()
            count_data = count_response.json()
        
            list_response = requests.get(player_list_url, timeout=5)
            list_response.raise_for_status()
            list_data = list_response.json()

            if server_offline_message_sent:
                await remove_webhook_message()
                server_offline_message_sent = False
                logging.info("Server back online detected")

                server_start_time = datetime.now(timezone.utc)
                server_online = True
                cached_player_list = None
            
            server_online = True
            
            if not server_start_time:
                server_start_time = datetime.now(timezone.utc)
            
            return count_data, list_data, True
    
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching API Data (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                if not server_offline_message_sent:
                    await send_webhook_message("Server cannot be reached. It has either crashed or restarted.")
                    server_offline_message_sent = True
                    server_start_time = None
                    server_online = False
                    cached_player_list = None
                return None, None, False
            retry_delay = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(retry_delay)

def format_uptime():
    """Calculates and formats the server uptime."""
    global server_start_time
    if server_start_time:
        uptime = datetime.now(timezone.utc) - server_start_time
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s" if days > 0 else f"{hours}h {minutes}m {seconds}s"
        return uptime_str
    else:
        return "Offline"

async def create_embed(count_data, list_data, server_online):
    """Creates a Discord Embed with formatted player data."""
    uptime = format_uptime()
    global cached_player_list

    if not server_online:
        embed = discord.Embed(title="Motor Town Server Status", color=discord.Color.red())
        embed.add_field(name=translations["server_status"], value=f"{RED_DOT} {translations['server_offline']}", inline=False)
        return embed
    
    if not count_data or not list_data:
        return None
    num_players = count_data["data"]["num_players"]
    player_list = list_data["data"]

    cached_player_list = player_list

    embed = discord.Embed(title="Motor Town Server Status", color=discord.Color.green())
    embed.add_field(name=translations["server_status"], value=f"{GREEN_DOT} | {translations['server_online']}", inline=False)
    embed.add_field(name=translations["uptime"], value=uptime, inline=False)
    embed.add_field(name=translations["players_online"], value=f"{num_players}", inline=False)
    
    if player_list:
        player_names = "\n".join([player["name"] for _, player in player_list.items()])
        embed.add_field(name=translations["player_names"], value=player_names, inline=False)
    else:
        embed.add_field(name=translations["player_names"], value=translations["no_players_online"], inline=False)
    return embed

async def create_banlist_embed(ban_data):
    """Creates a Discord Embed with the banned player list."""
    if not ban_data or not ban_data['data']:
        embed = discord.Embed(title=translations["banned_players"], color=discord.Color.red())
        embed.add_field(name=translations["banned_players"], value=translations["no_banned_players"], inline=False)
        return embed

    banned_players = ban_data['data']
    embed = discord.Embed(title=translations["banned_players"], color=discord.Color.red())
    if banned_players:
        banned_names = "\n".join([player["name"] for _, player in banned_players.items()])
        embed.add_field(name=translations["banned_players"], value=banned_names, inline=False)
    return embed

@bot.tree.command(name="showmtstats", description="Activates server statistics updates in the current channel.")
@is_admin()
async def show_mt_stats(interaction: discord.Interaction):
    global tracking_channel_id, status_message_id, server_online
    tracking_channel_id = interaction.channel_id

    if not update_stats.is_running():
        await interaction.response.defer()
        count_data, list_data, server_online = await fetch_player_data()
        if server_online:
            embed = await create_embed(count_data, list_data, server_online)
            if embed:
                ctx = await commands.Context.from_interaction(interaction)
                status_message = await ctx.send(embed=embed)
                status_message_id = status_message.id
                update_stats.start()
                await interaction.followup.send("Player statistics updates started in this channel.", ephemeral=True)
        else:
            embed = await create_embed(None, None, server_online)
            ctx = await commands.Context.from_interaction(interaction)
            status_message = await ctx.send(embed=embed)
            status_message_id = status_message.id
            update_stats.start()
            await interaction.followup.send("Server is offline. Stats started", ephemeral=True)
    else:
        await interaction.response.send_message("Player statistics updates already running in this channel", ephemeral=True)

@bot.tree.command(name="removemtstats", description="Deactivates server statistics updates.")
@is_admin()
async def remove_mt_stats(interaction: discord.Interaction):
    global tracking_channel_id, status_message_id
    if update_stats.is_running() and tracking_channel_id == interaction.channel_id:
        update_stats.cancel()
        tracking_channel_id = None
        status_message_id = None
        server_start_time = None
        await interaction.response.send_message("Player statistics updates stopped in this channel", ephemeral=True)
    elif tracking_channel_id is None:
        await interaction.response.send_message("Player statistics updates are not running", ephemeral=True)
    elif tracking_channel_id != interaction.channel_id:
        await interaction.response.send_message("Player statistics updates are not running in this channel.", ephemeral=True)

@tasks.loop(seconds=30)
async def update_stats():
    global status_message_id, tracking_channel_id, server_start_time, server_online
    if not tracking_channel_id or not status_message_id:
        return
    
    try:
        count_data, list_data, server_online = await fetch_player_data()
        embed = await create_embed(count_data, list_data, server_online)
    except Exception as e:
        logging.error(f"Error fetching player data for stats: {e}")
        server_online = False
        embed = await create_embed(None, None, server_online)
      
    try:    
        channel = bot.get_channel(tracking_channel_id)
        if channel:
            message = await channel.fetch_message(status_message_id)
            await message.edit(embed=embed)
        else:
            logging.error(f"Channel with id: {tracking_channel_id} not found, cannot update status message")
            status_message_id = None
            update_stats.stop()
    except discord.errors.NotFound as e:
        logging.error(f"Error editing message, message not found: {e}")
        status_message_id = None
        update_stats.stop()
    except discord.errors.HTTPException as e:
        logging.error(f"Error editing message: {e}")
        status_message_id = None
        update_stats.stop()

@bot.tree.command(name="mtmsg", description="Sends a message to the game server chat.")
@is_admin()
async def mt_msg(interaction: discord.Interaction, message: str):
    url = f"{API_BASE_URL}/chat?password={API_PASSWORD}&message={message}"
    try:
        await interaction.response.defer()
        response = requests.post(url)
        response.raise_for_status()
        logging.info(f"Sent message to server (command): {message}, Response code: {response.status_code}")
        await interaction.followup.send(f"Message sent to server chat: `{message}`")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending message (command): {e}, response: {e.response}")
        await interaction.followup.send(f"Error sending message: {e}", ephemeral=True)

@bot.tree.command(name="mtban", description="Bans a player from the server.")
@is_admin()
async def mt_ban(interaction: discord.Interaction, player_name: str):
    player_list_url = f"{API_BASE_URL}/player/list?password={API_PASSWORD}"
    try:
        await interaction.response.defer()
        list_response = requests.get(player_list_url)
        list_response.raise_for_status()
        list_data = list_response.json()
        if list_data and list_data['data']:
            player_found = False
            for _, player in list_data['data'].items():
                if player['name'] == player_name:
                    unique_id = player['unique_id']
                    player_found = True
                    ban_url = f"{API_BASE_URL}/player/ban?password={API_PASSWORD}&unique_id={unique_id}"
                    try:
                        ban_response = requests.post(ban_url)
                        ban_response.raise_for_status()
                        logging.info(f"Banned player: {player_name}, Response code: {ban_response.status_code}")
                        await interaction.followup.send(f"Player `{player_name}` banned from server.")
                        break
                    except requests.exceptions.RequestException as e:
                        logging.error(f"Error banning player: {e}")
                        await interaction.followup.send(f"Error banning player: {e}", ephemeral=True)
                        break
            if not player_found:
                await interaction.followup.send(f"Player with name `{player_name}` not found on the server.", ephemeral=True)
        else:
            await interaction.followup.send("Error: Could not get player list", ephemeral=True)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error retrieving player list: {e}")
        await interaction.followup.send(f"Error retrieving player list: {e}", ephemeral=True)

@bot.tree.command(name="mtkick", description="Kicks a player from the server.")
@is_admin()
async def mt_kick(interaction: discord.Interaction, player_name: str):
    player_list_url = f"{API_BASE_URL}/player/list?password={API_PASSWORD}"
    try:
        await interaction.response.defer()
        list_response = requests.get(player_list_url)
        list_response.raise_for_status()
        list_data = list_response.json()
        if list_data and list_data['data']:
            player_found = False
            for _, player in list_data['data'].items():
                if player['name'] == player_name:
                    unique_id = player['unique_id']
                    player_found = True
                    kick_url = f"{API_BASE_URL}/player/kick?password={API_PASSWORD}&unique_id={unique_id}"
                    try:
                        kick_response = requests.post(kick_url)
                        kick_response.raise_for_status()
                        logging.info(f"Kicked player: {player_name}, Response code: {kick_response.status_code}")
                        await interaction.followup.send(f"Player `{player_name}` kicked from server.")
                        break
                    except requests.exceptions.RequestException as e:
                        logging.error(f"Error kicking player: {e}")
                        await interaction.followup.send(f"Error kicking player: {e}", ephemeral=True)
                        break
            if not player_found:
                await interaction.followup.send(f"Player with name `{player_name}` not found on the server.", ephemeral=True)
        else:
            await interaction.followup.send("Error: Could not get player list", ephemeral=True)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error retrieving player list: {e}")
        await interaction.followup.send(f"Error retrieving player list: {e}", ephemeral=True)

@bot.tree.command(name="mtunban", description="Unbans a player from the server.")
@is_admin()
async def mt_unban(interaction: discord.Interaction, player_name: str):
    ban_list_url = f"{API_BASE_URL}/player/banlist?password={API_PASSWORD}"
    try:
        await interaction.response.defer()
        ban_response = requests.get(ban_list_url)
        ban_response.raise_for_status()
        ban_data = ban_response.json()
        if ban_data and ban_data['data']:
            player_found = False
            for _, player in ban_data['data'].items():
                if player['name'] == player_name:
                    unique_id = player['unique_id']
                    player_found = True
                    unban_url = f"{API_BASE_URL}/player/unban?password={API_PASSWORD}&unique_id={unique_id}"
                    try:
                        unban_response = requests.post(unban_url)
                        unban_response.raise_for_status()
                        logging.info(f"Unbanned player: {player_name}, Response code: {unban_response.status_code}")
                        await interaction.followup.send(f"Player `{player_name}` unbanned from server.")
                        break
                    except requests.exceptions.RequestException as e:
                        logging.error(f"Error unbanning player: {e}")
                        await interaction.followup.send(f"Error unbanning player: {e}", ephemeral=True)
                        break
            if not player_found:
                await interaction.followup.send(f"Player with name `{player_name}` not found on the ban list.", ephemeral=True)
        else:
            await interaction.followup.send("Error: Could not get ban list", ephemeral=True)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error retrieving ban list: {e}")
        await interaction.followup.send(f"Error retrieving ban list: {e}", ephemeral=True)

@bot.tree.command(name="mtshowbanned", description="Displays a list of banned players")
@is_admin()
async def mt_showbanned(interaction: discord.Interaction):
    ban_list_url = f"{API_BASE_URL}/player/banlist?password={API_PASSWORD}"
    try:
        await interaction.response.defer()
        ban_response = requests.get(ban_list_url)
        ban_response.raise_for_status()
        ban_data = ban_response.json()
        embed = await create_banlist_embed(ban_data)
        await interaction.followup.send(embed=embed)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error retrieving ban list: {e}")
        await interaction.followup.send(f"Error retrieving ban list: {e}", ephemeral=True)

@bot.event
async def on_message(message):
    """Event that gets called when a message is sent"""
    pass

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return
    
    logging.error(f"Error in app command: {error}")
    await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)

@bot.event
async def on_ready():
    """Event that gets called when the bot is ready."""
    print(f'Logged in as {bot.user.name}')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} commands')
    except Exception as e:
        logging.error(f"Error syncing commands: {e}")

bot.run(TOKEN)