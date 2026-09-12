# BallBot

BallBot is a production-ready Discord bot scaffold built with Python 3.11+, `discord.py` 2.x, and SQLite.

## Features

- Slash-command help menu with `/commands`
- Giveaway hosting with persistent entry buttons and role-restricted entry
- Live chain-of-command embed tracking based on configured roles
- Owner-only `/setup` commands for all server configuration
- Dropdown-based ticket creation with transcripts
- SQLite persistence for guild config, ticket counters, tickets, giveaways, and entrants
- Reusable embed helpers for success, error, info, and warning responses

## Requirements

- Python 3.11 or newer
- A Discord application and bot token

## Installation

1. Clone the repository.
2. Create and activate a virtual environment.
3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and fill in your bot token.
5. Enable the `Members` and `Message Content` intents for the bot in the Discord developer portal before the first run.
6. Start the bot:

   ```bash
   python bot.py
   ```

## Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `BOT_TOKEN` | Yes | Discord bot token |
| `DATABASE_PATH` | No | SQLite database path, defaults to `data/ballbot.sqlite3` |

## Discord Intents

Enable these privileged and standard intents in the Discord developer portal and in the bot:

- `guilds`
- `members`
- `messages`
- `message_content` for complete ticket transcript message bodies

The bot enables these intents in `bot.py`, and the same intents must also be enabled for the application in the Discord developer portal.

## Recommended Bot Permissions

- View Channels
- Send Messages
- Embed Links
- Attach Files
- Read Message History
- Manage Channels
- Manage Messages
- Use Slash Commands

If you use tickets or chain refreshes, ensure the bot can create channels, edit channel permissions, and post in the configured target channels.

## Project Structure

```text
bot.py
cogs/
  commands.py
  setup.py
  tickets.py
  giveaways.py
  chain.py
utils/
  db.py
  embeds.py
  transcripts.py
requirements.txt
.env.example
```

## Setup Workflow

All setup commands are owner-only. If a non-owner uses any `/setup` command, BallBot replies ephemerally and explains that only the server owner can configure the bot.

Recommended order:

1. `/setup giveaway-role` — set the required giveaway entry role
2. `/setup chain-roles` — provide the ordered role mentions or IDs for the chain
3. `/setup chain-channel` — choose where the live chain embed should be posted
4. `/setup ticket-transcripts` — choose where ticket transcripts are uploaded
5. `/setup ticket-category` — choose the category used for new ticket channels
6. `/setup ticket-staff-roles` — configure the roles allowed to view tickets
7. `/setup ticket-panel` — post the persistent ticket dropdown message
8. `/setup status` — review the saved configuration

## Command Overview

### `/commands`

Shows the main embed help menu for giveaways, tickets, chain-of-command tools, and setup commands.

### Giveaways

- `/giveaway start` posts a giveaway embed with a persistent **Enter Giveaway** button.
- Giveaway entry is checked when the button is clicked and blocked unless the member has the configured role.
- Duplicate entries are prevented in SQLite.
- `/giveaway end` closes a giveaway and picks winners.
- `/giveaway reroll` draws a fresh winner set for an ended giveaway.
- Active giveaway data persists through bot restarts.

### Chain of Command

- `/chain show` displays the current chain embed on demand.
- The configured chain display message updates automatically when members gain or lose tracked roles.
- Missing roles or missing display channels are handled gracefully.

### Tickets

- Ticket creation happens from the persistent dropdown panel, not a slash command.
- Included ticket types:
  - Questions
  - Suggestions
- Each ticket creates a numbered private channel such as `ticket-0001`.
- Access is limited to:
  - the ticket opener
  - configured ticket staff roles
  - the bot
- Closing a ticket generates an HTML transcript, uploads it to the configured transcript channel, stores the record in SQLite, and locks the ticket channel.

## Persistence

SQLite stores:

- guild configuration
- ticket counter
- ticket records
- giveaway records
- giveaway entrants

The bot initializes its database tables on startup if they do not exist.