import discord
from discord.ext import commands
import ai
import json
import random
import sys
import os
import requests
from typing import Dict, Any, Optional

class DiscordAIBot:
    def __init__(self, bot_id: int):
        self.bot_id = bot_id
        self.config = self._load_config()
        self.chat_manager = ai.ChatManager()

        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        
        self.bot = commands.Bot(
            command_prefix=self.config.get("prefix", "-"),
            intents=intents
        )
        
        self._setup_events()

    def _load_config(self) -> Dict[str, Any]:
        try:
            if not os.path.exists("data.json"):
                raise FileNotFoundError("data.json not found")
                
            with open("data.json", "r", encoding="utf8") as f:
                data = json.load(f)
                
            if not isinstance(data, list):
                raise ValueError("data.json should contain a list of bot configurations")
                
            if self.bot_id >= len(data):
                raise IndexError(f"Bot index {self.bot_id} out of range (max: {len(data)-1})")
                
            config = data[self.bot_id]
            
            required_fields = ["bot_token", "model", "personality"]
            for field in required_fields:
                if field not in config:
                    raise ValueError(f"Missing required field '{field}' in bot configuration")

            config.setdefault("msg_chance", 5)  
            config.setdefault("max_tokens", 1000)
            config.setdefault("temperature", 0.7)
            
            return config
            
        except (FileNotFoundError, json.JSONDecodeError, ValueError, IndexError) as e:
            print(f"Error loading bot configuration: {e}")
            sys.exit(1)

    def _setup_events(self):
        
        @self.bot.event
        async def on_ready():
            print(f"Bot ready as {self.bot.user}")
            print(f"Invite URL: https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&permissions=8&integration_type=0&scope=bot")

        @self.bot.event
        async def on_message(message):
            if message.author == self.bot.user:
                return
                
            # Process commands first
            await self.bot.process_commands(message)
            
        
            voice_mode = False
            voice_name = "dan" 
            
            content_lower = message.content.strip().lower()
            if content_lower.endswith("/voice"):
                voice_mode = True
            elif "/voice " in content_lower:
  
                voice_parts = message.content.strip().split()
                for i, part in enumerate(voice_parts):
                    if part.lower() == "/voice" and i + 1 < len(voice_parts):
                        voice_mode = True
                        voice_name = voice_parts[i + 1]
                        break
            
            should_respond = self._should_respond_to_message(message)
            

            if voice_mode:
                should_respond = True
            

            formatted_message = self._format_message(message)
            

            image_urls = []
            if message.attachments:
                for attachment in message.attachments:
                    if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                        image_urls.append(attachment.url)
            
            if should_respond:
                await self._handle_ai_response(message, formatted_message, image_urls, voice_mode, voice_name)

    def _should_respond_to_message(self, message: discord.Message) -> bool:
        if message.mentions and self.bot.user in message.mentions:
            return True

        if self.bot.user.name.lower() in message.content.lower():
            return True
            
 
        return random.randint(1, 100) <= self.config["msg_chance"]

    def _format_message(self, message: discord.Message) -> str:
        guild_name = message.guild.name if message.guild else "Direct Message"
        channel_name = message.channel.name if hasattr(message.channel, 'name') else "DM"
        
   
        content = message.content.strip()
        
        # Handle /voice at the end
        if content.lower().endswith("/voice"):
            content = content[:-6].strip()

        elif "/voice " in content.lower():
            words = content.split()
            new_words = []
            skip_next = False
            for i, word in enumerate(words):
                if skip_next:
                    skip_next = False
                    continue
                if word.lower() == "/voice" and i + 1 < len(words):
                    skip_next = True 
                    continue
                elif word.lower() == "/voice":
                    continue
                new_words.append(word)
            content = " ".join(new_words)
        
        return (f"{message.author.name} / {message.author.nick if message.author.nick else ''}: {content} | "
               f"Info: {channel_name} (channel name) in {guild_name} (guild)")

    async def _handle_ai_response(self, message: discord.Message, formatted_message: str, image_urls: list, voice_mode: bool = False, voice_name: str = "dan"):
        try:
            async with message.channel.typing():

                personality = f"{self.config['personality']} Your name is {self.bot.user}."
                
                response_data = self.chat_manager.get_ai_response(
                    query=formatted_message,
                    bot_id=self.bot_id,
                    model=self.config["model"],
                    personality=personality,
                    max_tokens=self.config["max_tokens"],
                    temperature=self.config["temperature"],
                    image_urls=image_urls
                )
                

                if isinstance(response_data, dict):
                    response_text = response_data.get("content", "")
                    image_data = response_data.get("image")
                    pfp_requests = response_data.get("pfp_requests", [])
                else:
                    response_text = response_data
                    image_data = None
                    pfp_requests = []
                
        
                if response_text:
                    await self._send_chunked_response(message, response_text)
              
                if pfp_requests:
                    await self._handle_pfp_requests(message, pfp_requests)
                
                if image_data:
                    try:
                        file = discord.File(fp=image_data, filename="generated_image.png")
                        await message.channel.send(file=file)
                    except Exception as e:
                        print(f"Error sending image: {e}")
                        await message.channel.send("I generated an image but couldn't send it.")
                
                if voice_mode and response_text:
                    try:
                        voice_data = ai.gen_voice(response_text, voice_name)
                        if voice_data:
                            file = discord.File(fp=voice_data, filename="response.mp3")
                            await message.channel.send(f"🔊 Voice response ({voice_name}):", file=file)
                    except Exception as e:
                        print(f"Error generating/sending voice: {e}")
                        await message.channel.send(f"Sorry, I couldn't generate the voice response with voice '{voice_name}'.")
                
        except Exception as e:
            print(f"Error handling AI response: {e}")
            await message.reply("Sorry, I encountered an error while processing your message.")

    async def _send_chunked_response(self, message: discord.Message, response: str, chunk_size: int = 1900):
        if len(response) <= chunk_size:
            await message.reply(response)
        else:
            chunks = [response[i:i+chunk_size] for i in range(0, len(response), chunk_size)]
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await message.reply(chunk)
                else:
                    await message.channel.send(chunk)

    async def _handle_pfp_requests(self, message: discord.Message, pfp_requests: list):
        
        for username in pfp_requests:
            try:
                target_user = None
                if message.guild:
                    for member in message.guild.members:
                        if (member.display_name.lower() == username.lower() or 
                            member.name.lower() == username.lower()):
                            target_user = member
                            break
                
                if target_user:
                    avatar_url = target_user.display_avatar.url
                    
                    personality = f"{self.config['personality']} Your name is {self.bot.user}."
                    pfp_query = f"Here is {target_user.display_name}'s profile picture. Analyze what you see."
                    
                    pfp_response = self.chat_manager.get_ai_response(
                        query=pfp_query,
                        bot_id=self.bot_id,
                        model=self.config["model"],
                        personality=personality,
                        max_tokens=self.config["max_tokens"],
                        temperature=self.config["temperature"],
                        image_urls=[avatar_url]
                    )
                    
                    if isinstance(pfp_response, dict):
                        pfp_text = pfp_response.get("content", "")
                    else:
                        pfp_text = pfp_response
                    
                    if pfp_text:
                        await message.channel.send(f"{pfp_text}")
                    
                else:
                    await message.channel.send(f"❌ Couldn't find user '{username}' in this server.")
                    
            except Exception as e:
                print(f"Error handling PFP request for {username}: {e}")
                await message.channel.send(f"❌ Error processing profile picture request for '{username}'.")

    def add_commands(self):
        
        @self.bot.command(name="assist")
        async def assist(ctx):
            model_api = "https://text.pollinations.ai/models"
            try:
                response = requests.get(model_api)
                models = response.json()
                model_list = []
                for model in models:
                    name = model.get("name", "")
                    desc = model.get("description", "")
                    if name and desc:
                        model_list.append(f"- {name}: {desc}")
                model_text = "\n".join(model_list)
                await ctx.reply(f"This is a R.AI bot. \nCommands:\n -remove <start of bot_token ( 7 characters min )>\n-create <bot_token> <model> <personality> \n Available models:\n{model_text} \n > You can mention a AI by saying its name, pinging it or replying to its messages\nThe messages can be spoken if you add /voice to the end of your query")
            except Exception as e:
                print(f"Error fetching model list: {e}")
                await ctx.reply("An error occurred while fetching the model list Sorry LMAO.")

        @self.bot.command(name="remove")
        async def remove(ctx, bot_start):

            if len(bot_start) < 7:
                await ctx.reply("Bot token must be at least 7 characters long.")
                return
            
            with open("data.json", "r", encoding="utf8") as f:
                data = json.load(f)

            for bot in data:
                if bot["bot_token"].startsWith(bot_start):
                    data.remove(bot)
                    break
                
            with open("data.json", "w", encoding="utf8") as f:
                json.dump(data, f, indent=4)

            await ctx.reply("Bot removed successfully!")

        @self.bot.command(name="create")
        async def create(ctx, bot_token, model, personality):
            
            await ctx.message.delete()

            data_conf = {
                "bot_token": bot_token,
                "model": model,
                "msg_chance": 0,
                "personality": personality,
            }

            with open("data.json", "r", encoding="utf8") as f:
                data = json.load(f)

            data.append(data_conf)

            with open("data.json", "w", encoding="utf8") as f:
                json.dump(data, f, indent=4)


            await ctx.reply("Bot created successfully!")
      

    def run(self):
        self.add_commands()
        try:
            self.bot.run(self.config["bot_token"])
        except discord.LoginFailure:
            print("Error: Invalid bot token")
            sys.exit(1)
        except Exception as e:
            print(f"Error running bot: {e}")
            sys.exit(1)

def main():
    if len(sys.argv) != 2:
        print("Usage: python discord_bot.py <bot_id>")
        sys.exit(1)
    
    try:
        bot_id = int(sys.argv[1])
    except ValueError:
        print("Error: Bot ID must be a number")
        sys.exit(1)
    
    bot = DiscordAIBot(bot_id)
    bot.run()

if __name__ == "__main__":
    main()