import json
import subprocess
import os
import sys
import time
import threading
from typing import List, Dict, Any

class BotMonitor:
    def __init__(self, data_file: str = "data.json"):
        self.data_file = data_file
        self.data = self._load_data()
        self.running_bots: Dict[int, subprocess.Popen] = {}
        self.lock = threading.Lock()
        self.monitoring = False

    def _load_data(self) -> List[Dict[str, Any]]:
        try:
            if not os.path.exists(self.data_file):
                print(f"Error: {self.data_file} not found")
                return []
                
            with open(self.data_file, "r", encoding="utf8") as f:
                data = json.load(f)
                
            if not isinstance(data, list):
                print(f"Error: {self.data_file} should contain a list of bot configurations")
                return []
                
            return data
            
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {self.data_file}: {e}")
            return []
        except Exception as e:
            print(f"Error loading data: {e}")
            return []

    def _validate_bot_config(self, config: Dict[str, Any], index: int) -> bool:
        required_fields = ["bot_token", "model", "personality"]
        
        for field in required_fields:
            if field not in config:
                print(f"Error: Bot {index} missing required field '{field}'")
                return False
                
        if not isinstance(config.get("msg_chance", 5), int) or config.get("msg_chance", 5) < 0:
            print(f"Warning: Bot {index} has invalid msg_chance, using default (5)")
            config["msg_chance"] = 5
            
        return True

    def _start_bot_process(self, index: int) -> subprocess.Popen:
        try:
            print(f"Starting bot {index}...")
            
            current_data = self._load_data()
            if index >= len(current_data):
                print(f"Error: Bot index {index} out of range")
                return None
                
            if not self._validate_bot_config(current_data[index], index):
                return None
            
            process = subprocess.Popen(
                [sys.executable, "discord_bot.py", str(index)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            return process
            
        except FileNotFoundError:
            print(f"Error: discord_bot.py not found")
            return None
        except Exception as e:
            print(f"Error starting bot {index}: {e}")
            return None

    def _monitor_bot_process(self, index: int, process: subprocess.Popen):

        try:
            stdout, stderr = process.communicate()
            
            with self.lock:
                if index in self.running_bots:
                    del self.running_bots[index]
            
            if process.returncode != 0:
                print(f"Bot {index} failed with return code {process.returncode}")
                if stderr:
                    print(f"Bot {index} stderr: {stderr}")
            else:
                print(f"Bot {index} finished successfully")
                
        except Exception as e:
            print(f"Error monitoring bot {index}: {e}")
            with self.lock:
                if index in self.running_bots:
                    del self.running_bots[index]

    def _start_new_bots(self):
        new_data = self._load_data()
        
        if not new_data:
            return
            
        with self.lock:
            current_count = len(self.running_bots)
            new_count = len(new_data)
            
            # Start new bots if the count increased
            if new_count > current_count:
                for i in range(len(new_data)):
                    if i not in self.running_bots:
                        if i < len(self.data):
                          
                            if self.data[i] != new_data[i]:
                                print(f"Bot {i} configuration changed, restarting...")
                                # Stop old bot if running
                                if i in self.running_bots:
                                    self.running_bots[i].terminate()
                                    del self.running_bots[i]
                        
                        process = self._start_bot_process(i)
                        if process:
                            self.running_bots[i] = process
                        
                            monitor_thread = threading.Thread(
                                target=self._monitor_bot_process,
                                args=(i, process),
                                daemon=True
                            )
                            monitor_thread.start()
            
            self.data = new_data

    def _cleanup_finished_bots(self):
        with self.lock:
            finished_bots = []
            for index, process in self.running_bots.items():
                if process.poll() is not None:  
                    finished_bots.append(index)
            
            for index in finished_bots:
                print(f"Cleaning up finished bot {index}")
                del self.running_bots[index]

    def start_monitoring(self):
        print(f"Starting continuous monitoring of {self.data_file}...")
        print("Press Ctrl+C to stop monitoring and shut down all bots")
        print(f"DEBUG: Data loaded: {len(self.data)} bots found")
        
        self._start_new_bots()
        
        last_mod_time = 0
        if os.path.exists(self.data_file):
            last_mod_time = os.path.getmtime(self.data_file)
        
        self.monitoring = True
        
        try:
            while self.monitoring:
                # Check if file has been modified
                if os.path.exists(self.data_file):
                    current_mod_time = os.path.getmtime(self.data_file)
                    if current_mod_time > last_mod_time:
                        print(f"Detected changes in {self.data_file}, checking for new bots...")
                        time.sleep(0.5)  # Small delay to ensure file write is complete
                        self._start_new_bots()
                        last_mod_time = current_mod_time
                
                self._cleanup_finished_bots()
               
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\nReceived interrupt signal, shutting down...")
        finally:
            self._shutdown_all_bots()

    def _shutdown_all_bots(self):
        with self.lock:
            print(f"Shutting down {len(self.running_bots)} running bots...")
            for index, process in self.running_bots.items():
                try:
                    print(f"Terminating bot {index}...")
                    process.terminate()

                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        print(f"Force killing bot {index}...")
                        process.kill()
                except Exception as e:
                    print(f"Error terminating bot {index}: {e}")
            
            self.running_bots.clear()
        print("All bots have been shut down.")

    def stop_monitoring(self):
        self.monitoring = False

    def list_bots(self):
        if not self.data:
            print("No bot configurations found.")
            return
            
        print(f"Found {len(self.data)} bot configurations:")
        for i, config in enumerate(self.data):
            model = config.get("model", "Unknown")
            chance = config.get("msg_chance", 5)
            status = "Running" if i in self.running_bots else "Stopped"
            print(f"  {i}: Model={model}, Response Chance={chance}%, Status={status}")

def main():
    print("DEBUG: bot_monitor.py starting...")
    monitor = BotMonitor()
    print(f"DEBUG: BotMonitor initialized, args: {sys.argv}")
    
    if len(sys.argv) == 1:
        print("DEBUG: No arguments, starting monitoring...")
        monitor.start_monitoring()
    elif len(sys.argv) == 2:
        arg = sys.argv[1]
        
        if arg == "list":
            monitor.list_bots()
        elif arg == "help":
            print("Usage:")
            print("  python bot_monitor.py       - Start continuous monitoring")
            print("  python bot_monitor.py list  - List all bot configurations with status")
            print("  python bot_monitor.py help  - Show this help message")
        else:
            print(f"Error: '{arg}' is not a valid command")
            print("Use 'python bot_monitor.py help' for usage information")
    else:
        print("Error: Too many arguments")
        print("Use 'python bot_monitor.py help' for usage information")

if __name__ == "__main__":
    main()