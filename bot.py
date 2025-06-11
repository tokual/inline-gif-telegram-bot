import asyncio
import logging
import os
import random
import uuid
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
        
        # Language codes for random translation
        self.languages = {
            'es': 'Spanish',
            'fr': 'French', 
            'de': 'German',
            'it': 'Italian',
            'pt': 'Portuguese',
            'ru': 'Russian',
            'ja': 'Japanese',
            'ko': 'Korean',
            'zh': 'Chinese',
            'ar': 'Arabic',
            'hi': 'Hindi',
            'tr': 'Turkish',
            'pl': 'Polish',
            'nl': 'Dutch',
            'sv': 'Swedish',
            'da': 'Danish',
            'no': 'Norwegian',
            'fi': 'Finnish',
            'el': 'Greek',
            'he': 'Hebrew'
        }
        
        # Setup handlers
        self.application.add_handler(InlineQueryHandler(self.handle_inline_query))
    
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
            # GIF settings
            width, height = 500, 300
            frames = 20
            
            # Wrap text for better display
            wrapped_text = textwrap.fill(text, width=25)
            
            # Create frames
            gif_frames = []
            
            for frame_num in range(frames):
                # Create frame
                img = Image.new('RGB', (width, height), color='white')
                draw = ImageDraw.Draw(img)
                
                # Try to load a font, fallback to default if not available
                try:
                    font_size = 24
                    font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", font_size)
                except:
                    try:
                        font = ImageFont.truetype("arial.ttf", font_size)
                    except:
                        font = ImageFont.load_default()
                
                # Calculate text position
                text_bbox = draw.textbbox((0, 0), wrapped_text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
                x = (width - text_width) // 2
                y = (height - text_height) // 2 - 20
                
                # Animated color effect
                hue = (frame_num * 360 // frames) % 360
                color = self.hsv_to_rgb(hue, 100, 80)
                
                # Draw text
                draw.text((x, y), wrapped_text, fill=color, font=font)
                
                # Draw language info
                lang_text = f"Language: {language}"
                lang_y = y + text_height + 20
                draw.text((x, lang_y), lang_text, fill='black', font=font)
                
                gif_frames.append(img)
            
            # Save GIF to bytes
            gif_bytes = BytesIO()
            gif_frames[0].save(
                gif_bytes,
                format='GIF',
                save_all=True,
                append_images=gif_frames[1:],
                duration=100,  # 100ms per frame
                loop=0
            )
            gif_bytes.seek(0)
            
            # Generate filename
            filename = f"translation_{uuid.uuid4().hex[:8]}.gif"
            
            logger.info(f"Created GIF with {len(gif_frames)} frames")
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
                    title=f"🌍 {translated_text}",
                    caption=f"🔤 Original: {query}\n🌍 {lang_name}: {translated_text}"
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
        """Handle inline queries"""
        try:
            query = update.inline_query.query.strip()
            logger.info(f"Received inline query: '{query}'")
            
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
            
            # Process query with timeout
            async def delayed_processing():
                try:
                    results = await asyncio.wait_for(
                        self.create_translation_result(query), 
                        timeout=25.0  # Leave 5 seconds buffer before Telegram timeout
                    )
                    
                    if results:
                        logger.info(f"Sending {len(results)} results for query: '{query}'")
                        await update.inline_query.answer(results, cache_time=0)
                    else:
                        logger.warning(f"No results for query: '{query}', sending error result")
                        error_results = self.create_error_result("No results found")
                        await update.inline_query.answer(error_results, cache_time=1)
                        
                except asyncio.TimeoutError:
                    logger.error(f"Processing timed out for query: '{query}'")
                    timeout_results = self.create_error_result("Processing timed out")
                    await update.inline_query.answer(timeout_results, cache_time=1)
                except Exception as e:
                    logger.error(f"Error in delayed_processing: {e}")
                    error_results = self.create_error_result("An error occurred")
                    await update.inline_query.answer(error_results, cache_time=1)
            
            # Start processing in background
            asyncio.create_task(delayed_processing())
            
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
