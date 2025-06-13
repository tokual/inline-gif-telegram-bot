# Raspberry Pi Deployment

## Steps

1. Clone the repo on your Raspberry Pi:
   ```bash
   git clone https://github.com/tokual/inline-gif-telegram-bot.git
   cd inline-gif-telegram-bot
   ```

2. Set your BOT_TOKEN in `.env`:
   ```bash
   echo "BOT_TOKEN=your_actual_bot_token_here" > .env
   ```

3. Add user IDs to `.whitelist`:
   ```bash
   echo "123456789  # your_telegram_user_id" > .whitelist
   ```

4. Run the deployment script:
   ```bash
   chmod +x deploy-pi.sh && ./deploy-pi.sh
   ```

That's it!

## How to Update

```bash
cd inline-gif-telegram-bot
git pull origin main
sudo systemctl restart telegram-bot
```

If you get merge conflicts due to local changes, force update with:
```bash
git reset --hard HEAD
git pull origin main
sudo systemctl restart telegram-bot
```
