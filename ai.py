import requests
import openai
import json
import os
import io
from typing import List, Dict, Optional, Any, Union

class ChatManager:
    def __init__(self, chat_file: str = "chat.json", personality: str = ""):
        self.chat_file = chat_file
        self.client = openai.OpenAI(
            api_key="dummy", 
            base_url="https://text.pollinations.ai/openai"
        )
        self.default_system_prompt = {
            "role": "system",
            "content": (
                "You are a Discord AI. Follow character at all times. "
                "You will receive messages that will be formatted from users in this format: "
                "<username>(<bot/user>): <message> | Info: <channel> in <guild> (guild)"
                "\n Do not respond in this format. It's only instructions on how to interpret the format. "
                "Note that the user may not be talking about you, so do not act as if they are unless "
                "you see your name in their response or based off context. You may invoke the image generation tool by saying 'Gen: <prompt>' on a new line. "
                "You can also use the tool 'see_pfp: <username>' to view a user's profile picture if you need to see what they look like or analyze their avatar."
                f"The following is your personality, embody it with full percision and never break character: {personality}"
            )
        }

    def _load_all_histories(self) -> List[List[Dict[str, str]]]:
        if os.path.exists(self.chat_file):
            with open(self.chat_file, "r", encoding="utf8") as f:
                data = json.load(f)
                # dementia over 500 messages
                if len(data) > 500:
                    data = data[-500:] # last 500 to prevent memory issues
                return data if isinstance(data, list) else []
        return []

    def _save_all_histories(self, histories: List[List[Dict[str, str]]]) -> bool:
        with open(self.chat_file, "w", encoding="utf8") as f:
            json.dump(histories, f, indent=2, ensure_ascii=False)
        return True

    def _ensure_history_exists(self, histories: List[List[Dict[str, str]]], bot_id: int, personality: str = "") -> None:
        while len(histories) <= bot_id:
            system_prompt = self.default_system_prompt.copy()
            if personality:
                system_prompt["content"] += f"\n{personality}"
            histories.append([system_prompt])

    def add_to_history(self, message: str, bot_id: int = 0, image_urls: List[str] = None) -> bool:
        histories = self._load_all_histories()
        self._ensure_history_exists(histories, bot_id)
        

        user_message = {"role": "user", "content": []}

        user_message["content"].append({
            "type": "text",
            "text": message
        })
        
        # Add image content if provided
        if image_urls:
            for image_url in image_urls:
                user_message["content"].append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
        
     
        if not image_urls:
            user_message = {"role": "user", "content": message}
        
        histories[bot_id].append(user_message)
        return self._save_all_histories(histories)

    def get_chat_history(self, bot_id: int = 0, personality: str = "") -> List[Dict[str, str]]:
        histories = self._load_all_histories()
        self._ensure_history_exists(histories, bot_id, personality)
        return histories[bot_id].copy()

    def get_ai_response(self, query: str, bot_id: int = 0, model: str = "openai-large", 
                      personality: str = "", max_tokens: int = 1000, temperature: float = 0.7, 
                      image_urls: List[str] = None) -> Union[str, Dict[str, Any]]:

        chat_history = self.get_chat_history(bot_id, personality)
        

        current_message = {"role": "user", "content": []}

        current_message["content"].append({
            "type": "text",
            "text": query
        })
        
        # Add image content if provided
        if image_urls:
            for image_url in image_urls:
                current_message["content"].append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
        
    
        if not image_urls:
            current_message = {"role": "user", "content": query}
        
        messages = chat_history + [current_message]
        
        completion = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        response = completion.choices[0].message.content
        
        histories = self._load_all_histories()
        self._ensure_history_exists(histories, bot_id, personality)
     
        histories[bot_id].append(current_message)
        histories[bot_id].append({"role": "assistant", "content": response})
        
        self._save_all_histories(histories)

       
        image_data = None
        pfp_requests = []
        if "---" in response:
            response=response.split("---")[0]
        lines = response.splitlines()
        filtered_lines = []

        for line in lines:
            if line.strip().startswith("Gen:"):
                prompt = line.split("Gen:", 1)[1].strip()
                image_data = gen_image(prompt)
                break 
            elif line.strip().startswith("see_pfp:"):
                username = line.split("see_pfp:", 1)[1].strip()
                pfp_requests.append(username)
            else:
                filtered_lines.append(line)
        response = '\n'.join(filtered_lines)
        if response == "":
            response = "OK"
        return {"content": response, "image": image_data, "pfp_requests": pfp_requests}

    def clear_history(self, bot_id: int = 0, personality: str = "") -> bool:
        histories = self._load_all_histories()
        
        if bot_id < len(histories):
            system_prompt = self.default_system_prompt.copy()
            if personality:
                system_prompt["content"] += f"\n{personality}"
            histories[bot_id] = [system_prompt]
            return self._save_all_histories(histories)
        
        return True

chat_manager = ChatManager()

def add_to_history(info: str, id: int = 0, image_urls: List[str] = None) -> bool:
    return chat_manager.add_to_history(info, id, image_urls)

def get_ai_response(query: str, history=None, model: str = "openai-large", 
                   id: int = 0, personality1: str = "", image_urls: List[str] = None) -> Union[str, Dict[str, Any]]:
    return chat_manager.get_ai_response(query, id, model, personality1, image_urls=image_urls)

def gen_image(query: str) -> Optional[io.BytesIO]:

    if not query or not isinstance(query, str):
        raise ValueError("Query must be a non-empty string")

    query = query.strip()
    query += "no-logo" 
    

    base_url = "https://image.pollinations.ai/prompt/"
    encoded_query = requests.utils.quote(query)
    url = f"{base_url}{encoded_query}?nolog=true&nologo=true&width=800&height=800&enhance=true&safe=false&model=flux&seed=4438"
    
    response = requests.get(url, timeout=60)
    response.raise_for_status()  
    
    return io.BytesIO(response.content)

def gen_voice(text: str, voice: str = "dan") -> Optional[io.BytesIO]:
    if not text or not isinstance(text, str):
        raise ValueError("Text must be a non-empty string")

    text = "Repeat the exact text, no adding anything else: " + text
    text = text.strip()

    base_url = "https://text.pollinations.ai/"
    encoded_text = requests.utils.quote(text)
    url = f"{base_url}{encoded_text}?model=openai-audio&voice={voice}"

    response = requests.get(url, timeout=60)
    response.raise_for_status()  
    
    return io.BytesIO(response.content)