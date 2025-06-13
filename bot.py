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
from telegram import Update, InlineQueryResultGif, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, InlineQueryHandler, ContextTypes
import textwrap

# Configure logging
log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper())
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=log_level
)
logger = logging.getLogger(__name__)

class TranslationBot:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.application = Application.builder().token(bot_token).build()
        
        # Load configuration from environment variables
        self.load_config()
        
        # Language codes for translation (Latin and non-Latin languages)
        self.languages = {
            # Latin-based languages
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
            'fi': 'Finnish',
            # Non-Latin languages
            'ru': 'Russian',
            'ar': 'Arabic'
        }
        
        # Languages that require special font handling
        self.non_latin_languages = {'ru', 'ar'}

        # Language command mapping for inline queries (including /random)
        self.language_commands = {f'/{k}': k for k in self.languages.keys()}
        self.language_commands['/random'] = 'random'  # Special case for random selection
        self.language_commands['/help'] = 'help'  # Special case for help
        
        # Load whitelist
        self.whitelist = self.load_whitelist()
        
        # Query debouncing - track last query time per user
        self.user_query_times = {}
        
        # Setup handlers
        self.application.add_handler(InlineQueryHandler(self.handle_inline_query))
    
    def load_config(self):
        """Load configuration from environment variables with defaults"""
        # Query processing configuration
        self.debounce_delay = float(os.getenv('DEBOUNCE_DELAY', '2.0'))
        self.processing_timeout = float(os.getenv('PROCESSING_TIMEOUT', '28.0'))
        
        # GIF generation configuration
        self.gif_width = int(os.getenv('GIF_WIDTH', '800'))
        self.gif_height = int(os.getenv('GIF_HEIGHT', '450'))
        self.gif_frames = int(os.getenv('GIF_FRAMES', '20'))
        self.gif_duration = int(os.getenv('GIF_DURATION', '150'))
        self.gif_quality = int(os.getenv('GIF_QUALITY', '95'))
        
        # Font configuration
        self.main_font_size = int(os.getenv('MAIN_FONT_SIZE', '32'))
        self.lang_font_size = int(os.getenv('LANG_FONT_SIZE', '16'))
        self.text_wrap_width = int(os.getenv('TEXT_WRAP_WIDTH', '30'))
        
        # Animation configuration
        self.hue_saturation = int(os.getenv('HUE_SATURATION', '85'))
        self.hue_value = int(os.getenv('HUE_VALUE', '95'))
        
        # Upload configuration
        self.upload_timeout = int(os.getenv('UPLOAD_TIMEOUT', '30'))
        
        logger.info(f"Loaded config: {self.gif_width}x{self.gif_height}, {self.gif_frames} frames, {self.debounce_delay}s debounce")
    
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
    
    def parse_language_command(self, query: str) -> Tuple[str, Optional[str]]:
        """Parse language command from query. Returns (text, language_code)"""
        query = query.strip()
        
        # Check for help command
        if query.lower() == '/help' or query.lower().startswith('/help '):
            return 'help', 'help'
        
        # Check if query starts with a language command
        for command, lang_code in self.language_commands.items():
            if command == '/help':  # Skip help command in this loop
                continue
            if query.lower().startswith(command.lower()):
                # Extract the text after the command
                remaining_text = query[len(command):].strip()
                if remaining_text:  # Only return if there's text to translate
                    # Handle special case for /random
                    if lang_code == 'random':
                        return remaining_text, None  # None means random selection
                    else:
                        return remaining_text, lang_code
                break
        
        return query, None
    
    async def translate_text(self, text: str, target_language: Optional[str] = None) -> Tuple[str, str, str]:
        """Translate text to specified language or random language"""
        try:
            # Use specified language or select random
            if target_language and target_language in self.languages:
                lang_code = target_language
                lang_name = self.languages[lang_code]
            else:
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
    
    def get_font_for_language(self, language_code: str, font_size: int) -> Tuple[Optional[object], int]:
        """Get appropriate font for the given language code"""
        if language_code in self.non_latin_languages:
            # Font paths for non-Latin languages
            non_latin_font_paths = [
                # Russian/Cyrillic fonts
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Has Cyrillic
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # Has Cyrillic
                "/System/Library/Fonts/Arial.ttf",  # macOS
                # Arabic fonts
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Has some Arabic
                "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",  # Noto Arabic
                "/System/Library/Fonts/GeezaPro.ttc",  # macOS Arabic
                # Windows fonts (Unicode support)
                "/Windows/Fonts/arial.ttf",
                "/Windows/Fonts/calibri.ttf",
            ]
            
            for font_path in non_latin_font_paths:
                try:
                    font = ImageFont.truetype(font_path, font_size)
                    logger.info(f"Using font {font_path} for language {language_code}")
                    return font, font_size
                except (OSError, IOError):
                    continue
            
            # Fallback: try with smaller size
            logger.warning(f"No suitable font found for {language_code}, using default")
            try:
                font = ImageFont.load_default()
                return font, max(font_size - 8, 16)
            except:
                return None, max(font_size - 8, 16)
        else:
            # Latin languages - use existing font selection
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Raspberry Pi
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",  # Common Linux
                "/System/Library/Fonts/Arial.ttf",  # macOS
                "/Windows/Fonts/arial.ttf",  # Windows
            ]
            
            for font_path in font_paths:
                try:
                    font = ImageFont.truetype(font_path, font_size)
                    return font, font_size
                except (OSError, IOError):
                    continue
            
            # Fallback
            try:
                font = ImageFont.load_default()
                return font, 20
            except:
                return None, 16

    async def create_gif(self, text: str, language: str, original_text: str) -> Tuple[Optional[bytes], str]:
        """Create an animated GIF from text"""
        try:
            # Use configured GIF settings
            width, height = self.gif_width, self.gif_height
            frames = self.gif_frames
            
            # Determine language code for font selection
            lang_code = None
            for code, name in self.languages.items():
                if name == language:
                    lang_code = code
                    break
            
            # Adjust text wrapping for different languages
            if lang_code in self.non_latin_languages:
                # Non-Latin languages might need different wrapping
                if lang_code == 'ar':
                    # Arabic is RTL, but PIL handles this automatically
                    wrap_width = self.text_wrap_width
                else:  # Russian
                    wrap_width = self.text_wrap_width
            else:
                wrap_width = self.text_wrap_width
            
            # Wrap text for better display
            wrapped_text = textwrap.fill(text, width=wrap_width)
            
            # Create frames
            gif_frames = []
            
            for frame_num in range(frames):
                # Create frame with higher quality
                img = Image.new('RGBA', (width, height), color=(255, 255, 255, 255))
                draw = ImageDraw.Draw(img)
                
                # Get appropriate font for this language
                font_size = self.main_font_size
                font, actual_font_size = self.get_font_for_language(lang_code or 'en', font_size)
                
                # Calculate text position with better centering
                text_lines = wrapped_text.split('\n')
                total_text_height = len(text_lines) * actual_font_size * 1.2
                
                start_y = (height - total_text_height) // 2 - 30
                
                # Draw each line of text
                for i, line in enumerate(text_lines):
                    if font:
                        try:
                            text_bbox = draw.textbbox((0, 0), line, font=font)
                            line_width = text_bbox[2] - text_bbox[0]
                        except:
                            # Fallback for older PIL versions or font issues
                            line_width = len(line) * (actual_font_size * 0.6)
                    else:
                        line_width = len(line) * (actual_font_size * 0.6)
                    
                    x = (width - line_width) // 2
                    y = start_y + (i * actual_font_size * 1.3)
                    
                    # Animated color effect with configurable colors
                    hue = (frame_num * 360 // frames) % 360
                    color = self.hsv_to_rgb(hue, self.hue_saturation, self.hue_value)
                    
                    # Add text shadow for better readability
                    shadow_offset = 2
                    try:
                        draw.text((x + shadow_offset, y + shadow_offset), line, fill=(0, 0, 0, 100), font=font)
                        draw.text((x, y), line, fill=color, font=font)
                    except Exception as e:
                        # Fallback if font rendering fails
                        logger.warning(f"Font rendering issue: {e}, using fallback")
                        draw.text((x + shadow_offset, y + shadow_offset), line, fill=(0, 0, 0, 100))
                        draw.text((x, y), line, fill=color)
                
                # Draw language info with smaller font
                lang_font_size = max(self.lang_font_size, actual_font_size - 8)
                lang_font, _ = self.get_font_for_language(lang_code or 'en', lang_font_size)
                
                lang_text = f"→ {language}"
                if lang_font:
                    try:
                        lang_bbox = draw.textbbox((0, 0), lang_text, font=lang_font)
                        lang_width = lang_bbox[2] - lang_bbox[0]
                    except:
                        lang_width = len(lang_text) * (lang_font_size * 0.6)
                else:
                    lang_width = len(lang_text) * (lang_font_size * 0.6)
                
                lang_x = (width - lang_width) // 2
                lang_y = start_y + total_text_height + 20
                
                # Language info in a subtle color
                try:
                    draw.text((lang_x, lang_y), lang_text, fill=(100, 100, 100), font=lang_font)
                except:
                    draw.text((lang_x, lang_y), lang_text, fill=(100, 100, 100))
                
                # Convert RGBA to RGB for GIF compatibility
                rgb_img = Image.new('RGB', (width, height), (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                
                gif_frames.append(rgb_img)
            
            # Save GIF with configured quality settings
            gif_bytes = BytesIO()
            gif_frames[0].save(
                gif_bytes,
                format='GIF',
                save_all=True,
                append_images=gif_frames[1:],
                duration=self.gif_duration,
                loop=0,
                optimize=True,
                quality=self.gif_quality
            )
            gif_bytes.seek(0)
            
            # Generate filename
            filename = f"translation_{uuid.uuid4().hex[:8]}.gif"
            
            logger.info(f"Created GIF with {len(gif_frames)} frames at {width}x{height} for {language}")
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
                async with session.post(url, data=data, timeout=self.upload_timeout) as response:
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
            
            # Parse language command from query
            text_to_translate, target_language = self.parse_language_command(query)
            
            # Handle help command
            if target_language == 'help':
                help_text = self.create_help_message()
                return [
                    InlineQueryResultArticle(
                        id=f"help_{uuid.uuid4().hex[:6]}",
                        title="💡 How to use this bot",
                        description="Complete guide and available commands",
                        input_message_content=InputTextMessageContent(
                            message_text=help_text,
                            parse_mode='Markdown'
                        )
                    )
                ]
            
            if not text_to_translate.strip():
                logger.warning("No text to translate after parsing command")
                return []

            if target_language:
                logger.info(f"Using specified language: {self.languages[target_language]}")
            else:
                logger.info("Using random language selection")
            
            # Translate the text
            translated_text, lang_name, lang_code = await self.translate_text(text_to_translate, target_language)
            logger.info(f"Translated '{text_to_translate}' to {lang_name}: '{translated_text}'")
            
            # Create GIF
            gif_bytes, filename = await self.create_gif(translated_text, lang_name, text_to_translate)
            
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
    
    def create_help_message(self) -> str:
        """Create help message with available language commands"""
        commands = ['🎲 /random - Random Language']
        for code, name in sorted(self.languages.items()):
            commands.append(f"🌍 /{code} - {name}")
        
        commands_text = "\n".join(commands)
        return f"""💡 **How to use this bot:**

**Available commands:**
{commands_text}

**Examples:**
• `/random Hello world` (random language)
• `/es Hello world` (Spanish)
• `/it Ciao mondo` (Italian)
• `Hello world` (also random language)"""
    
    def get_matching_language_commands(self, query: str) -> List[Tuple[str, str, str]]:
        """Get language commands that match the query. Returns (command, language_name, language_code)"""
        query_lower = query.lower().strip()
        
        # Prepare all commands with /random first
        all_commands = [('/random', 'Random Language', 'random')]
        all_commands.extend([(cmd, self.languages[code], code) for cmd, code in self.language_commands.items() if code != 'random'])
        
        if not query_lower:
            # Return all commands if no query, with /random first
            return all_commands
        
        matches = []
        for command, lang_name, lang_code in all_commands:
            # Match if query starts with the command or if the language name contains the query
            if (command.lower().startswith(query_lower) or 
                lang_name.lower().startswith(query_lower) or
                (lang_code != 'random' and lang_code.lower().startswith(query_lower))):
                matches.append((command, lang_name, lang_code))
        
        return matches
    
    def create_language_command_results(self, query: str) -> List:
        """Create inline results for language commands using articles (text-based)"""
        matching_commands = self.get_matching_language_commands(query)
        results = []
        
        for command, lang_name, lang_code in matching_commands[:15]:  # Limit to 15 suggestions
            result_id = f"cmd_{lang_code}_{uuid.uuid4().hex[:6]}"
            
            # Create different descriptions based on command type
            if lang_code == 'random':
                title = f"🎲 {command} - {lang_name}"
                description = "Tap to use random translation"
            else:
                title = f"🌍 {command} - {lang_name}"
                description = f"Tap to use {lang_name} translation"
            
            results.append(
                InlineQueryResultArticle(
                    id=result_id,
                    title=title,
                    description=description,
                    input_message_content=InputTextMessageContent(
                        message_text=f"{command} "
                    )
                )
            )
        
        return results

    def should_show_command_suggestions(self, query: str) -> bool:
        """Determine if we should show command suggestions instead of translation"""
        # Never show command suggestions - always process text
        return False
    
    def create_help_result(self) -> List:
        """Create a help result when query is empty"""
        help_text = self.create_help_message()
        return [
            InlineQueryResultArticle(
                id=f"help_cmd_{uuid.uuid4().hex[:6]}",
                title="📋 /help - Show Commands",
                description="Get detailed help and command list",
                input_message_content=InputTextMessageContent(
                    message_text=help_text,
                    parse_mode='Markdown'
                )
            ),
            InlineQueryResultArticle(
                id=f"help_{uuid.uuid4().hex[:6]}",
                title="💡 How to use this bot",
                description="Type text to translate to random, or use /lang commands (e.g. /it)",
                input_message_content=InputTextMessageContent(
                    message_text=help_text,
                    parse_mode='Markdown'
                )
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
                    [InlineQueryResultArticle(
                        id=str(uuid.uuid4()),
                        title="❌ Access Denied",
                        description="You are not authorized to use this bot.",
                        input_message_content=InputTextMessageContent(
                            message_text="❌ You are not authorized to use this bot."
                        )
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
            
            # Show help if query is empty
            if not query:
                help_results = self.create_help_result()
                await update.inline_query.answer(help_results, cache_time=1)
                return
            
            # Debounce mechanism - wait before processing translation
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
                    
                    # Process query with configured timeout
                    results = await asyncio.wait_for(
                        self.create_translation_result(query), 
                        timeout=self.processing_timeout
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