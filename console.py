# discord.gg/nekos ON TOP
import datetime
from colorama import Fore, Style, init
import os
import threading

print_lock = threading.Lock()
def safe_print(message):
    with print_lock:
        print(message)

class bcolors:
    BLACK        = '\033[30m'
    TIME         = '\033[90m'
    OKBLUE       = '\033[94m'
    DEEPBLUE     = '\033[34m'
    PURPLE       = '\033[95m'
    FAIL         = '\033[91m'
    SUCCESS      = '\033[92m'
    ENDC         = '\033[0m'
    HEADER       = '\033[95m'
    OKGREEN      = '\033[92m'
    WARNING      = '\033[93m'
    BOLD         = '\033[1m'
    UNDERLINE    = '\033[4m'
    DARKGREEN    = '\033[32m'
    PINK         = '\033[38;5;13m'
    TWITTERBLUE  = '\033[38;2;29;161;242m'
    CLOUDFLARE_ORANGE = '\033[38;2;243;128;32m' 

class Console:
    def __init__(self):
        init(autoreset=True)
        self.colors = {
            "green": Fore.GREEN,
            "red": Fore.RED,
            "yellow": Fore.YELLOW,
            "blue": Fore.BLUE,
            "magenta": Fore.MAGENTA,
            "cyan": Fore.CYAN,
            "white": Fore.WHITE,
            "black": Fore.BLACK,
            "reset": Style.RESET_ALL,
            "lightblack": Fore.LIGHTBLACK_EX,
            "lightred": Fore.LIGHTRED_EX,
            "lightgreen": Fore.LIGHTGREEN_EX,
            "lightyellow": Fore.LIGHTYELLOW_EX,
            "lightblue": Fore.LIGHTBLUE_EX,
            "lightmagenta": Fore.LIGHTMAGENTA_EX,
            "lightcyan": Fore.LIGHTCYAN_EX,
            "lightwhite": Fore.LIGHTWHITE_EX
        }
    
    def timestamp(self):
        return datetime.datetime.now().strftime("%H:%M:%S")
    
    def _format_message(self, level, level_color, message, fields=None):
        if fields is None:
            fields = {}
        
        ts = self.timestamp()
        base = f"{ts} {level_color}{level}{bcolors.ENDC} ● {message}"
        if fields:
            extra = f" {bcolors.TIME}→{bcolors.ENDC} "
            field_strs = [f"{key}: [{level_color}{value}{bcolors.ENDC}]" for key, value in fields.items()]
            extra += f" {bcolors.TIME}|{bcolors.ENDC} ".join(field_strs)
            return f"{base}{extra}"
        else:
            return base

    def error(self, message="", **kwargs):
        msg = self._format_message("ERROR", bcolors.FAIL, message, kwargs)
        safe_print(msg)
    
    def success(self, message="", **kwargs):
        msg = self._format_message("SUCCESS", bcolors.SUCCESS, message, kwargs)
        safe_print(msg)
    
    def redeemed(self, message="", **kwargs):
        msg = self._format_message("REDEEMED", bcolors.PINK, message, kwargs)
        safe_print(msg)

    def warning(self, message="", **kwargs):
        msg = self._format_message("WARNING", bcolors.WARNING, message, kwargs)
        safe_print(msg)
    
    def info(self, message="", **kwargs):
        msg = self._format_message("INFO", bcolors.OKBLUE, message, kwargs)
        safe_print(msg)

    def input(self, message="", **kwargs):
        msg = self._format_message("INPUT", bcolors.OKBLUE, message, kwargs)
        return input(msg)

    def clear(self):
        os.system("cls" if os.name == "nt" else "clear")