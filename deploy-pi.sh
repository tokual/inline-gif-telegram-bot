#!/bin/bash

# Simple deployment script for Raspberry Pi
echo "🚀 Deploying Telegram GIF Bot on Raspberry Pi..."

# Update system and install dependencies
sudo apt update
sudo apt install -y python3 python3-pip python3-venv libjpeg-dev zlib1g-dev libfreetype6-dev

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python packages
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "BOT_TOKEN=your_bot_token_here" > .env
    echo "⚠️  Please edit .env and add your bot token"
fi

# Create .whitelist file if it doesn't exist
if [ ! -f .whitelist ]; then
    echo "# Add your Telegram user IDs here" > .whitelist
    echo "⚠️  Please edit .whitelist and add authorized user IDs"
fi

# Create systemd service
sudo tee /etc/systemd/system/telegram-gif-bot.service > /dev/null << EOF
[Unit]
Description=Telegram GIF Bot
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$(pwd)
Environment=PATH=$(pwd)/.venv/bin
ExecStart=$(pwd)/.venv/bin/python $(pwd)/bot.py
Restart=always
RestartSec=10
EnvironmentFile=$(pwd)/.env

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable telegram-gif-bot
sudo systemctl start telegram-gif-bot

echo "✅ Deployment complete!"
echo "📋 Commands:"
echo "  Status: sudo systemctl status telegram-gif-bot"
echo "  Logs:   sudo journalctl -u telegram-gif-bot -f"
echo "  Stop:   sudo systemctl stop telegram-gif-bot"
