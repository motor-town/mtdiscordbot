# MTDiscordBot

This project is a Discord bot that interacts with Motor-Town Dedicated Server WebAPI. It provides various commands for server management, including player statistics, banning, and kicking players.

## ToDo:

- add pelican/pterodactyl eggs
- add Discord commands overview

## Features

- Fetch and display player statistics.
- Send messages to the game server chat.
- Ban and kick players from the server.
- Display a list of banned players.

## Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd mt
   ```

2. Create a `.env` file in the `src` directory and add your configuration settings:
   ```
   DISCORD_BOT_TOKEN=your_bot_token
   API_BASE_URL=your_api_base_url
   API_PASSWORD=your_api_password
   WEBHOOK_URL=your_webhook_url
   ```

3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

To run the bot, execute the following command:
```
python src/main.py
```

Make sure to replace the placeholders in the `.env` file with your actual credentials.

## Dependencies

This project requires the following Python packages:

- discord.py
- requests
- python-dotenv
- psutil 
- matplotlib

## Discord 
**These Bot permissions are required**
- Privileged Gateway Intents
  - Presence Intent
  - Message Content Intent
- Bot Perms
  - View Channels
  - Send Messages
  - Embed Links
  - Use Application Commands

**Full list of commands**
```/showmtstats```
```/removemtstats```
```/mtkick```
```/mtban```
```/mtmsg```
```/mtunban```
```/mtshowbanned```
```/mtmsg```

Server stats window is updated every 30 seconds.

## License
This project is licensed under the MIT License. See the LICENSE file for more details.

The bot is based of https://github.com/ValhallaCommunityOfficial/Motor-Town-Discord-Bot. Check out their Homepage: https://www.thevalhallacommunity.com/home
