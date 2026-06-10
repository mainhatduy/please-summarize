# Discord Group Chat Summarizer & Music Self-Bot

This project is a Discord self-bot (running as a personal user account) that provides two main features for private group chats (Group Chat / Group DM):
1. **Chat summarization:** Collect the latest N messages or messages from the last N hours, send them to the Gemini API for translation, and generate a concise summary in Vietnamese.
2. **YouTube music playback:** Download the audio stream from YouTube via `yt-dlp` and stream it directly into the group's voice call using `FFmpeg`.

---

## ⚠️ Important Notice (Discord ToS)

> [!WARNING]
> Using a **Self-bot** (automating a personal account) violates Discord's **Terms of Service (ToS)**.
> The account running this bot may be detected and permanently banned by Discord.
> Use **only a clone/test account** for this project, and never use your main account.

---

## 🛠️ System Requirements

Before getting started, make sure your machine has:
1. **Python 3.11** or newer.
2. **uv** (a fast Python package manager). Install with:
   ```bash
   pip install uv
   ```
3. **FFmpeg** (audio processing and decoding tool).
   - **Ubuntu/Debian:** `sudo apt update && sudo apt install -y ffmpeg`
   - **macOS (Homebrew):** `brew install ffmpeg`
   - **Windows:** Download from the FFmpeg website and add the `bin` folder to your PATH.

---

## ⚙️ Configuration and Installation

### 1. Prepare the `.env` file
Copy or create a `.env` file in the project root:
```env
DISCORD_TOKEN=your_discord_user_token_here
GEMINI_API_KEY=your_gemini_api_key_here
MEMORY_TTL_HOURS=48
# CHANNEL_ID=your_target_channel_id_here  # (Optional)
```

> [!IMPORTANT]
> **How to get your Discord User Token (Self-bot Token):**
> 1. Open Discord in a web browser (Chrome/Firefox) and sign in with your test account.
> 2. Press `F12` (or `Ctrl + Shift + I`) to open Developer Tools, then select the **Network** tab.
> 3. Send a message or switch channels to generate requests.
> 4. Find a request with names starting with `messages` or `science`.
> 5. In the **Request Headers**, copy the value of the **`Authorization`** field (this is your user token, a long string not prefixed with `Bot `).
> 6. Paste this value into `DISCORD_TOKEN` in `.env`.

> [!TIP]
> **How to filter commands by CHANNEL_ID (Optional):**
> If you want the bot to only respond in a specific Group DM or chat channel, add `CHANNEL_ID=YOUR_CHANNEL_ID` to `.env`. If not set, the bot will respond to commands from any chat it is in.

### 2. Install dependencies
Use `uv` to install all dependencies from `requirements.txt`:
```bash
uv pip install -r requirements.txt
```

---

## 🚀 Run the Bot

### Run locally

Start the application with:
```bash
uv run python -m app.main
```

The bot will automatically load environment variables from `.env` and log in with your user account.

---

## 🐳 Deploy with Docker

> [!TIP]
> Docker is recommended for running the bot continuously on a server/VPS without installing Python or FFmpeg manually.

### Requirements

- **Docker** installed ([installation guide](https://docs.docker.com/get-docker/))

### 1. Prepare the `.env` file

Create a `.env` file in the project root (see the instructions above):
```env
DISCORD_TOKEN=your_discord_user_token_here
GEMINI_API_KEY=your_gemini_api_key_here
MEMORY_TTL_HOURS=48
```

> [!CAUTION]
> Never commit your `.env` file to Git. `.gitignore` is configured to ignore it.

### 2. Build the image

```bash
docker build -t discord-summarizer-bot .
```

### 3. Run the container

```bash
docker run -d \
  --name discord-bot \
  --env-file .env \
  -v discord-bot-data:/data \
  --restart unless-stopped \
  discord-summarizer-bot
```

| Flag | Meaning |
|---|---|
| `-d` | Run detached |
| `--name discord-bot` | Set a container name for easier management |
| `--env-file .env` | Load environment variables from `.env` |
| `-v discord-bot-data:/data` | Persist short-term memory and daily fortune history across container rebuilds |
| `--restart unless-stopped` | Restart automatically if the bot crashes, unless stopped manually |

### 4. Manage the container

```bash
# View logs in real time
docker logs -f discord-bot

# View the last 50 log lines
docker logs discord-bot --tail 50

# Stop the bot
docker stop discord-bot

# Restart the bot
docker restart discord-bot

# Remove the container (must stop first)
docker rm discord-bot
```

### 5. Update the bot (after code changes)

```bash
# Rebuild the image with updated code
docker build -t discord-summarizer-bot .

# Remove the old container and run again
docker rm -f discord-bot
docker run -d \
  --name discord-bot \
  --env-file .env \
  -v discord-bot-data:/data \
  --restart unless-stopped \
  discord-summarizer-bot
```

---

## 📝 Command List (Prefix: `.`)

Anyone in the Group DM can use the following commands:

### 💬 Text summary commands
*   `.tomtat <limit>` (or `.sum_msgs`): Summarize the last N messages in the group chat (default 50 if unspecified, maximum 500 messages).
*   `.tomtat_time <hours>` (or `.sum_time`): Summarize all messages from the last N hours (default 1 hour, maximum 12 hours, up to 500 total messages).

### 🎶 Voice call music commands
*   `.join`: Ask the bot to join the ongoing group voice call.
*   `.play <song name or YouTube link>`: Ask the bot to join the call (if not already in) and play music from YouTube (supports search by name or direct link).
*   `.leave` (or `.stop`): Stop playback and disconnect the bot from the voice call.

```bash
docker build -t discord-summarizer-bot .
docker rm -f discord-bot
docker run -d --name discord-bot --env-file .env -v discord-bot-data:/data --restart unless-stopped discord-summarizer-bot
```
