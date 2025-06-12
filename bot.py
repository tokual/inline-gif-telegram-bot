import asyncio
import logging
import os
import random
import uuid
import time
from io import BytesIO
from typing import List, Tuple, Optional

import aiohttp
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineQueryResultGif, InputTextMessageContent
from telegram.ext import Application, InlineQueryHandler, ContextTypes
import textwrap

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TranslationBot:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.application = Application.builder().token(bot_token).build()
        
        # Language codes for random translation (only Latin-based languages)
        self.languages = {
            'es': 'Spanish',
            'fr': 'French', 
            'de': 'German',
            'it': 'Italian',
            'pt': 'Portuguese',
            'pl': 'Polish',
            'nl': 'Dutch',
            'sv': 'Swedish',
            'da': 'Danish',
            'no': 'Norwegian',
            'fi': 'Finnish'
        }
        
        # Load whitelist
        self.whitelist = self.load_whitelist()
        
        # Query debouncing - track last query time per user
        self.user_query_times = {}
        self.debounce_delay = 2.0  # Increased to 2.0 seconds for Raspberry Pi
        
        # Setup handlers
        self.application.add_handler(InlineQueryHandler(self.handle_inline_query))
    
    def load_whitelist(self) -> set:
        """Load whitelisted user IDs from .whitelist file"""
        try:
            with open('.whitelist', 'r') as f:
                whitelist = set()
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Extract just the numeric ID
                        if line.isdigit():
                            whitelist.add(line)
                        else:
                            # Handle format like "@username 12345" or "12345 # username"
                            parts = line.split()
                            for part in parts:
                                if part.isdigit():
                                    whitelist.add(part)
                                    break
                return whitelist
        except FileNotFoundError:
            logger.warning("No .whitelist file found")
            return set()
    
    def is_user_whitelisted(self, user_id: int) -> bool:
        """Check if user is whitelisted"""
        return str(user_id) in self.whitelist
    
    async def translate_text(self, text: str) -> Tuple[str, str, str]:
        """Translate text to a random language using Google Translate API"""
        try:
            # Select random target language
            lang_code = random.choice(list(self.languages.keys()))
            lang_name = self.languages[lang_code]
            
            # Using Google Translate API (free tier)
            url = "https://translate.googleapis.com/translate_a/single"
            params = {
                'client': 'gtx',
                'sl': 'auto',  # Auto-detect source language
                'tl': lang_code,
                'dt': 't',
                'q': text
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        result = await response.json()
                        translated_text = result[0][0][0]
                        logger.info(f"Translated '{text}' to {lang_name}: '{translated_text}'")
                        return translated_text, lang_name, lang_code
                    else:
                        logger.error(f"Translation API error: {response.status}")
                        return text, "English", "en"  # Fallback
                        
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text, "English", "en"  # Fallback
    
    async def create_gif(self, text: str, language: str, original_text: str) -> Tuple[Optional[bytes], str]:
        """Create an animated GIF from text"""
        try:
            # Higher quality GIF settings
            width, height = 800, 450
            frames = 20
            
            # Wrap text for better display
            wrapped_text = textwrap.fill(text, width=30)
            
            # Create frames
            gif_frames = []
            
            for frame_num in range(frames):
                # Create frame with higher quality
                img = Image.new('RGBA', (width, height), color=(255, 255, 255, 255))
                draw = ImageDraw.Draw(img)
                
                # Try to load better fonts with fallbacks for Raspberry Pi
                font = None
                font_size = 32
                font_paths = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Raspberry Pi
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",  # Common Linux
                    "/System/Library/Fonts/Arial.ttf",  # macOS
                    "/Windows/Fonts/arial.ttf",  # Windows
                ]
                
                for font_path in font_paths:
                    try:
                        font = ImageFont.truetype(font_path, font_size)
                        break
                    except (OSError, IOError):
                        continue
                
                # If no system font found, try smaller default size
                if font is None:
                    try:
                        font = ImageFont.load_default()
                        # Scale up the default font effect
                        font_size = 20
                    except:
                        font_size = 16
                
                # Calculate text position with better centering
                text_lines = wrapped_text.split('\n')
                total_text_height = len(text_lines) * font_size * 1.2
                
                start_y = (height - total_text_height) // 2 - 30
                
                # Draw each line of text
                for i, line in enumerate(text_lines):
                    if font:
                        text_bbox = draw.textbbox((0, 0), line, font=font)
                        line_width = text_bbox[2] - text_bbox[0]
                    else:
                        line_width = len(line) * (font_size * 0.6)
                    
                    x = (width - line_width) // 2
                    y = start_y + (i * font_size * 1.3)
                    
                    # Animated color effect with better colors
                    hue = (frame_num * 360 // frames) % 360
                    color = self.hsv_to_rgb(hue, 85, 95)
                    
                    # Add text shadow for better readability
                    shadow_offset = 2
                    draw.text((x + shadow_offset, y + shadow_offset), line, fill=(0, 0, 0, 100), font=font)
                    draw.text((x, y), line, fill=color, font=font)
                
                # Draw language info with smaller font
                lang_font_size = max(16, font_size - 8)
                lang_font = None
                
                for font_path in font_paths:
                    try:
                        lang_font = ImageFont.truetype(font_path, lang_font_size)
                        break
                    except (OSError, IOError):
                        continue
                
                if lang_font is None:
                    lang_font = font
                
                lang_text = f"→ {language}"
                if lang_font:
                    lang_bbox = draw.textbbox((0, 0), lang_text, font=lang_font)
                    lang_width = lang_bbox[2] - lang_bbox[0]
                else:
                    lang_width = len(lang_text) * (lang_font_size * 0.6)
                
                lang_x = (width - lang_width) // 2
                lang_y = start_y + total_text_height + 20
                
                # Language info in a subtle color
                draw.text((lang_x, lang_y), lang_text, fill=(100, 100, 100), font=lang_font)
                
                # Convert RGBA to RGB for GIF compatibility
                rgb_img = Image.new('RGB', (width, height), (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                
                gif_frames.append(rgb_img)
            
            # Save GIF with better quality settings
            gif_bytes = BytesIO()
            gif_frames[0].save(
                gif_bytes,
                format='GIF',
                save_all=True,
                append_images=gif_frames[1:],
                duration=150,  # Slightly slower for better viewing
                loop=0,
                optimize=True,  # Enable optimization
                quality=95  # Higher quality
            )
            gif_bytes.seek(0)
            
            # Generate filename
            filename = f"translation_{uuid.uuid4().hex[:8]}.gif"
            
            logger.info(f"Created GIF with {len(gif_frames)} frames at {width}x{height}")
            return gif_bytes.getvalue(), filename
            
        except Exception as e:
            logger.error(f"Error creating GIF: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None, ""
    
    def hsv_to_rgb(self, h: float, s: float, v: float) -> Tuple[int, int, int]:
        """Convert HSV to RGB color values"""
        h = h / 360.0
        s = s / 100.0
        v = v / 100.0
        
        if s == 0:
            return int(v * 255), int(v * 255), int(v * 255)
        
        i = int(h * 6)
        f = (h * 6) - i
        p = v * (1 - s)
        q = v * (1 - s * f)
        t = v * (1 - s * (1 - f))
        
        i = i % 6
        
        if i == 0:
            r, g, b = v, t, p
        elif i == 1:
            r, g, b = q, v, p
        elif i == 2:
            r, g, b = p, v, t
        elif i == 3:
            r, g, b = p, q, v
        elif i == 4:
            r, g, b = t, p, v
        elif i == 5:
            r, g, b = v, p, q
        
        return int(r * 255), int(g * 255), int(b * 255)
    
    async def upload_gif_to_uguu(self, gif_bytes: bytes, filename: str) -> Optional[str]:
        """Upload GIF to uguu.se for temporary hosting"""
        try:
            url = "https://uguu.se/upload"
            
            # Create form data for uguu.se API
            data = aiohttp.FormData()
            data.add_field('files[]', gif_bytes, filename=filename, content_type='image/gif')
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, timeout=30) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # uguu.se returns different response formats
                        # Check for successful upload and extract URL
                        if isinstance(result, dict):
                            # Handle object response format
                            if 'files' in result and len(result['files']) > 0:
                                gif_url = result['files'][0].get('url')
                                if gif_url:
                                    logger.info(f"Uploaded GIF successfully to uguu.se: {gif_url}")
                                    return gif_url
                            # Handle direct URL response
                            elif 'url' in result:
                                gif_url = result['url']
                                logger.info(f"Uploaded GIF successfully to uguu.se: {gif_url}")
                                return gif_url
                        elif isinstance(result, list) and len(result) > 0:
                            # Handle array response format
                            if isinstance(result[0], dict) and 'url' in result[0]:
                                gif_url = result[0]['url']
                                logger.info(f"Uploaded GIF successfully to uguu.se: {gif_url}")
                                return gif_url
                        
                        # If we get here, try to parse as plain text response
                        response_text = await response.text()
                        if response_text.startswith('http'):
                            logger.info(f"Uploaded GIF successfully to uguu.se: {response_text}")
                            return response_text.strip()
                        
                        logger.error(f"Unexpected uguu.se response format: {result}")
                        return None
                    else:
                        error_text = await response.text()
                        logger.error(f"uguu.se upload error {response.status}: {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error uploading GIF to uguu.se: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def is_valid_url(self, url: str) -> bool:
        """Validate if URL is accessible"""
        import re
        return bool(re.match(r'^https?://', url)) and len(url) > 10
    
    async def create_translation_result(self, query: str) -> List:
        """Create translation and GIF result"""
        try:
            logger.info(f"Processing query: '{query}'")
            
            if not query.strip():
                logger.warning("Empty query received")
                return []
            
            # Translate the text
            translated_text, lang_name, lang_code = await self.translate_text(query)
            logger.info(f"Translated '{query}' to {lang_name}: '{translated_text}'")
            
            # Create GIF
            gif_bytes, filename = await self.create_gif(translated_text, lang_name, query)
            
            if not gif_bytes:
                logger.error("Failed to create GIF")
                return self.create_error_result("Failed to create GIF")
            
            # Upload GIF to uguu.se
            gif_url = await self.upload_gif_to_uguu(gif_bytes, filename)
            
            if not gif_url or not self.is_valid_url(gif_url):
                logger.error("Failed to upload GIF or invalid URL")
                return self.create_error_result("Failed to upload GIF")
            
            logger.info(f"Successfully uploaded GIF: {gif_url}")
            
            # Create inline result
            result_id = str(uuid.uuid4())
            
            results = [
                InlineQueryResultGif(
                    id=result_id,
                    gif_url=gif_url,
                    thumbnail_url=gif_url,
                    title=f"🌍 {translated_text}"
                )
            ]
            
            logger.info(f"Created {len(results)} result(s)")
            return results
            
        except Exception as e:
            logger.error(f"Error in create_translation_result: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self.create_error_result("Translation error occurred")
    
    def create_error_result(self, error_message: str) -> List:
        """Create an error result for inline query"""
        return [
            InlineQueryResultGif(
                id=str(uuid.uuid4()),
                gif_url="https://media.giphy.com/media/l2JehQ2GitHGdVG9y/giphy.gif",  # Error GIF
                thumbnail_url="https://media.giphy.com/media/l2JehQ2GitHGdVG9y/giphy.gif",
                title="❌ Translation failed",
                caption=f"Sorry, {error_message}. Please try again."
            )
        ]
    
    async def handle_inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline queries with debouncing"""
        try:
            # Check if user is whitelisted
            user_id = update.inline_query.from_user.id
            if not self.is_user_whitelisted(user_id):
                logger.warning(f"Unauthorized user {user_id} tried to use bot")
                await update.inline_query.answer(
                    [InlineQueryResultGif(
                        id=str(uuid.uuid4()),
                        gif_url="https://media.giphy.com/media/l2JehQ2GitHGdVG9y/giphy.gif",
                        thumbnail_url="https://media.giphy.com/media/l2JehQ2GitHGdVG9y/giphy.gif",
                        title="❌ Access Denied",
                        caption="You are not authorized to use this bot."
                    )],
                    cache_time=1
                )
                return
            
            query = update.inline_query.query.strip()
            current_time = time.time()
            
            # Check if there was a previous query that will be superseded
            previous_time = self.user_query_times.get(user_id)
            if previous_time:
                time_diff = current_time - previous_time
                logger.info(f"User {user_id} had previous query {time_diff:.2f}s ago - will be superseded")
            
            # Update user's last query time
            self.user_query_times[user_id] = current_time
            
            logger.info(f"Received inline query from user {user_id}: '{query}' (will wait {self.debounce_delay}s)")
            
            if not query:
                # Show help message for empty query using a simple GIF result
                await update.inline_query.answer(
                    [InlineQueryResultGif(
                        id=str(uuid.uuid4()),
                        gif_url="https://media.giphy.com/media/l0HlBO7eyXzSZkJri/giphy.gif",  # Help GIF
                        thumbnail_url="https://media.giphy.com/media/l0HlBO7eyXzSZkJri/giphy.gif",
                        title="💡 How to use",
                        caption="Type some text to translate and create a GIF!",
                        input_message_content=InputTextMessageContent(
                            message_text="💡 Type some text after @annoygminline_bot to translate it to a random language and create an animated GIF!"
                        )
                    )],
                    cache_time=1
                )
                return
            
            # Debounce mechanism - wait before processing
            async def debounced_processing():
                try:
                    # Wait for debounce delay
                    logger.info(f"Starting {self.debounce_delay}s wait for query from user {user_id}: '{query}'")
                    await asyncio.sleep(self.debounce_delay)
                    
                    # Check if this query is still the latest for this user
                    latest_time = self.user_query_times.get(user_id)
                    if latest_time != current_time:
                        logger.info(f"Query '{query}' from user {user_id} superseded by newer query (time mismatch: {current_time} vs {latest_time}), skipping")
                        return
                    
                    logger.info(f"Processing debounced query from user {user_id}: '{query}' (passed debounce check)")
                    
                    # Process query with timeout (reduced to account for debounce delay)
                    results = await asyncio.wait_for(
                        self.create_translation_result(query), 
                        timeout=28.0  # Reduced timeout to account for longer debounce delay
                    )
                    
                    # Double-check if query is still current before sending results
                    if self.user_query_times.get(user_id) != current_time:
                        logger.info(f"Query '{query}' from user {user_id} outdated after processing, not sending results")
                        return
                    
                    if results:
                        logger.info(f"Sending {len(results)} results for query: '{query}' from user {user_id}")
                        await update.inline_query.answer(results, cache_time=0)
                    else:
                        logger.warning(f"No results for query: '{query}' from user {user_id}, sending error result")
                        error_results = self.create_error_result("No results found")
                        await update.inline_query.answer(error_results, cache_time=1)
                        
                except asyncio.TimeoutError:
                    # Only send timeout error if query is still current
                    if self.user_query_times.get(user_id) == current_time:
                        logger.error(f"Processing timed out for query: '{query}' from user {user_id}")
                        timeout_results = self.create_error_result("Processing timed out")
                        await update.inline_query.answer(timeout_results, cache_time=1)
                    else:
                        logger.info(f"Query '{query}' from user {user_id} timed out but was already superseded")
                except Exception as e:
                    # Only send error if query is still current
                    if self.user_query_times.get(user_id) == current_time:
                        logger.error(f"Error in debounced_processing: {e}")
                        error_results = self.create_error_result("An error occurred")
                        await update.inline_query.answer(error_results, cache_time=1)
                    else:
                        logger.info(f"Query '{query}' from user {user_id} had error but was already superseded")
            
            # Start debounced processing in background
            asyncio.create_task(debounced_processing())
            
        except Exception as e:
            logger.error(f"Error in handle_inline_query: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def run(self):
        """Start the bot"""
        logger.info("Starting Translation GIF Bot...")
        self.application.run_polling(drop_pending_updates=True)

def main():
    # Get bot token from environment variable
    bot_token = os.getenv('BOT_TOKEN')
    
    if not bot_token:
        logger.error("BOT_TOKEN environment variable not set!")
        logger.info("Please set your bot token: export BOT_TOKEN='your_bot_token_here'")
        return
    
    # Create and run bot
    bot = TranslationBot(bot_token)
    bot.run()

if __name__ == '__main__':
    main()
