# discord.gg/nekos
import time
import uiautomator2 as u2
import subprocess
import sys
import os
import platform
import signal
import adbutils
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import shutil
import ctypes

from console import Console

console = Console()

EMAILS_FILE = "Input/emails.txt"
TOKENS_FILE = "Input/tokens.txt"
TEMPLATE_PATH = "frida_inject_template.js"
OUT_JS_PATH = "frida2.js"
FRIDA_CMD_TEMPLATE = 'frida -U -f {package} -l "{jsfile}"'
PACKAGE_NAME = "com.discord"

datetime_folder = datetime.now().strftime("[%m-%d-%Y] - [%I-%M-%S %p]")
output_base = f"Output/{datetime_folder}"
success_folder = f"{output_base}/Success"
error_folder = f"{output_base}/Error"

os.makedirs(success_folder, exist_ok=True)
os.makedirs(error_folder, exist_ok=True)

device_assignments = {}
device_locks = {}
email_queue = [] 
email_lock = threading.Lock()
assignment_lock = threading.Lock()

stats = {
    "redeemed": 0,
    "failed": 0,
    "errors": 0,
    "current_emails": 0,
    "current_tokens": 0,
    "initial_emails": 0,
    "initial_tokens": 0
}
stats_lock = threading.Lock()

token_queue_lock = threading.Lock()
global_token_queue = []

email_assignment_lock = threading.Lock()
assigned_emails = set()  

def update_title():
    ctypes.windll.kernel32.SetConsoleTitleW(f"Google Play Nitro Redeemer | Redeemed: {stats['redeemed']} | Failed: {stats['failed']} | Error: {stats['errors']} | Materials: [Emails: {stats['current_emails']} | Tokens: {stats['current_tokens']}]")

def increment_redeemed():
    with stats_lock:
        stats["redeemed"] += 1
    update_title()

def increment_failed():
    with stats_lock:
        stats["failed"] += 1
    update_title()

def increment_errors():
    with stats_lock:
        stats["errors"] += 1
    update_title()

def update_materials_count():
    try:
        available_emails, available_tokens, _ = check_resources_available()
        with stats_lock:
            stats["current_emails"] = available_emails
            stats["current_tokens"] = available_tokens
        update_title()
    except Exception as e:
        pass

def get_next_token():
    global global_token_queue
    
    with token_queue_lock:
        if not global_token_queue:
            try:
                tokens = read_tokens(TOKENS_FILE)
                global_token_queue = tokens
            except:
                return None
        
        if global_token_queue:
            return global_token_queue.pop(0)
        else:
            return None

def initialize_token_queue():
    global global_token_queue
    
    with token_queue_lock:
        tokens = read_tokens(TOKENS_FILE)
        global_token_queue = tokens.copy()



def prepare_email_queue():
    global email_queue
    with open(EMAILS_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    email_queue.clear()
    for line in lines:
        line = line.strip()
        if line and ":" in line:
            base_part = line.split("?")[0] if "?" in line else line
            
            yearly_used = False
            monthly_used = False
            
            if "?" in line:
                params_part = line.split("?", 1)[1]
                if "yearly=1" in params_part or "yearly=true" in params_part:
                    yearly_used = True
                if "monthly=1" in params_part or "monthly=true" in params_part:
                    monthly_used = True
            
            if ":" in base_part:
                email, password = base_part.split(":", 1)
                if not (yearly_used and monthly_used):
                    email_queue.append({
                        "email": email, 
                        "password": password, 
                        "yearly_used": yearly_used,
                        "monthly_used": monthly_used,
                        "original_line": line
                    })

def assign_next_available_email(device_serial):
    global device_assignments, email_queue, assigned_emails
    
    with email_assignment_lock:
        prepare_email_queue()
        
        for email_data in email_queue:
            email = email_data["email"]
            if (email_data["yearly_used"] and email_data["monthly_used"]) or email in assigned_emails:
                continue
                
            device_assignments[device_serial] = {
                "email": email_data["email"],
                "password": email_data["password"],
                "yearly_used": email_data["yearly_used"],
                "monthly_used": email_data["monthly_used"],
                "current_plan": None,
                "redeems_count": 0
            }
            
            assigned_emails.add(email)
            
            console.info(f"Assigned new email to device", 
                        email=email_data["email"], 
                        yearly_available=not email_data["yearly_used"],
                        monthly_available=not email_data["monthly_used"],
                        )
            return True
        
        return False

def assign_emails_to_devices(device_serials):
    global device_assignments, email_queue, assigned_emails
    
    with email_assignment_lock:
        available_emails = []
        for email_data in email_queue:
            if not (email_data["yearly_used"] and email_data["monthly_used"]):
                available_emails.append(email_data)
        
        available_emails.sort(key=lambda x: (x["yearly_used"] or x["monthly_used"]))
        
        if len(available_emails) < len(device_serials):
            raise SystemExit(f"Not enough available emails ({len(available_emails)}) for devices ({len(device_serials)})")
        
        assigned_emails.clear()
        
        for i, device_serial in enumerate(device_serials):
            email_data = available_emails[i]
            
            device_assignments[device_serial] = {
                "email": email_data["email"],
                "password": email_data["password"],
                "yearly_used": email_data["yearly_used"],
                "monthly_used": email_data["monthly_used"],
                "current_plan": None,
                "redeems_count": 0
            }
            
            assigned_emails.add(email_data["email"])
            
            console.info(f"Assigned email to device", 
                        email=email_data["email"], 
                        yearly_available=not email_data["yearly_used"],
                        monthly_available=not email_data["monthly_used"],
                        )

def get_device_email_info(device_serial):
    with assignment_lock:
        return device_assignments.get(device_serial)

def get_next_available_plan(device_serial):
    device_info = get_device_email_info(device_serial)
    if not device_info:
        return None
    
    if not device_info["yearly_used"]:
        return "Yearly"
    elif not device_info["monthly_used"]:
        return "Monthly"
    else:
        return None

def update_email_plan_status(email, plan_type, status):
    try:
        with open(EMAILS_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        new_lines = []
        for line in lines:
            line = line.strip()
            if line.startswith(f"{email}:"):
                base_part = line.split("?")[0] if "?" in line else line
                
                yearly_used = False
                monthly_used = False
                
                if "?" in line:
                    params_part = line.split("?", 1)[1]
                    if "yearly=1" in params_part or "yearly=true" in params_part:
                        yearly_used = True
                    if "monthly=1" in params_part or "monthly=true" in params_part:
                        monthly_used = True
                
                if plan_type.lower() == "yearly":
                    yearly_used = status
                elif plan_type.lower() == "monthly":
                    monthly_used = status
                
                new_line = base_part
                if yearly_used or monthly_used:
                    params = []
                    if yearly_used:
                        params.append("yearly=1")
                    if monthly_used:
                        params.append("monthly=1")
                    new_line += "?" + "&".join(params)
                
                new_lines.append(new_line + "\n")
            else:
                new_lines.append(line + "\n" if not line.endswith("\n") else line)
        
        with open(EMAILS_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        
        update_materials_count()
            
    except Exception as e:
        console.error(f"Error updating email plan status: {e}")
        increment_errors()

def mark_plan_used(device_serial, plan_type, success=True):
    global device_assignments, assigned_emails
    
    with assignment_lock:
        if device_serial not in device_assignments:
            return False
            
        device_info = device_assignments[device_serial]
        email = device_info["email"]
        
        if success:
            if plan_type.lower() == "yearly":
                device_info["yearly_used"] = True
            elif plan_type.lower() == "monthly":
                device_info["monthly_used"] = True
                
            device_info["redeems_count"] += 1
            
            update_email_plan_status(email, plan_type, True)
            
            save_completed_email(email, device_info["password"], plan_type)
            
            if device_info["yearly_used"] and device_info["monthly_used"]:
                with email_lock:
                    global email_queue
                    email_queue = [pair for pair in email_queue if pair["email"] != email]
                
                with email_assignment_lock:
                    assigned_emails.discard(email)
                
                remove_fully_used_email_from_file(email)
                return True
                
    return False


def remove_fully_used_email_from_file(email):
    try:
        with open(EMAILS_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        new_lines = []
        for line in lines:
            if not line.strip().startswith(f"{email}:"):
                new_lines.append(line)
        
        with open(EMAILS_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        
        update_materials_count()
            
    except Exception as e:
        console.error(f"Error removing email from file: {e}")
        increment_errors()

def save_completed_email(email, password, plan_type):
    try:
        success_emails_file = f"{success_folder}/redeemed_emails.txt"
        with open(success_emails_file, "a", encoding="utf-8") as f:
            f.write(f"{email}:{password}:{plan_type.lower()}\n")
    except Exception as e:
        console.error(f"Error saving completed email: {e}")
        increment_errors()

def save_error_email(email, password, error_type, plan_type):
    try:
        error_file = f"{error_folder}/error_emails.txt"
        with open(error_file, "a", encoding="utf-8") as f:
            f.write(f"{email}:{password}:{plan_type.lower()}\n")
    except Exception as e:
        console.error(f"Error saving error email: {e}")
        increment_errors()

def save_error_token(token):
    try:
        error_file = f"{error_folder}/error_tokens.txt"
        with open(error_file, "a", encoding="utf-8") as f:
            f.write(f"{token}\n")
    except Exception as e:
        console.error(f"Error saving error email: {e}")
        increment_errors()

def save_already_token(token):
    try:
        error_file = f"{error_folder}/already_redeemed.txt"
        with open(error_file, "a", encoding="utf-8") as f:
            f.write(f"{token}\n")
    except Exception as e:
        console.error(f"Error saving error email: {e}")
        increment_errors()


def save_redeemed_token(token, plan_type):
    try:
        redeemed_file = f"{success_folder}/redeemed.txt"
        with open(redeemed_file, "a", encoding="utf-8") as f:
            f.write(f"{token}\n")
    except Exception as e:
        console.error(f"Error saving redeemed token: {e}")
        increment_errors()

def pop_first_nonempty_line(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    i = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if i is None:
        raise SystemExit("No non-empty lines left in tokens.txt")
    val = lines[i].strip()
    del lines[i]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    
    update_materials_count()
    return val

def perform_gmail_login(device_serial):
    d = u2.connect(device_serial)

    d.shell("am start -a android.settings.SYNC_SETTINGS")
    time.sleep(3)

    if d(text="Add account").exists:
        d(text="Add account").click()
    else:
        console.error("Add account button not found.", )
        increment_errors()
        return False

    d.app_wait("com.google.android.gms", timeout=25)
    
    if not d(textContains="Forgot email?").wait(timeout=30):
        console.error("Gmail login screen not found", )
        increment_errors()
        return False

    time.sleep(2)
    if d(className="android.widget.EditText").wait(timeout=15):
        time.sleep(2)
        d(className="android.widget.EditText").click()
    else:
        ex1, ey1, ex2, ey2 = 444, 460, 1478, 556
        d.click((ex1 + ex2) // 2, (ey1 + ey2) // 2)

    device_info = get_device_email_info(device_serial)
    if not device_info:
        console.error(f"No email assigned to device {device_serial}")
        increment_errors()
        return False
    
    email = device_info["email"]
    d.send_keys(email, clear=True)
    time.sleep(1)

    if d(text="Next").exists:
        d(text="Next").click()
    else:
        nx1, ny1, nx2, ny2 = 1338, 679, 1478, 743
        d.click((nx1 + nx2) // 2, (ny1 + ny2) // 2)

    if d(textContains="robot").wait(timeout=7):
        remove_first_gmail_account(device_serial)
        remove_fully_used_email_from_file(email)
        time.sleep(3)

        if not assign_next_available_email(device_serial):
            return "no_emails"

        if not perform_gmail_login(device_serial):
            return "login_failed"

        return "gmail_switched"


    if not d(textContains="Show password").wait(timeout=30):
        console.error("Password field not found", )
        increment_errors()
        return False

    time.sleep(2)
    if d(className="android.widget.EditText").wait(timeout=15):
        time.sleep(2)
        d(className="android.widget.EditText").click()
    else:
        px1, py1, px2, py2 = 446, 421, 1475, 514
        d.click((px1 + px2) // 2, (py1 + py2) // 2)

    password = device_info["password"]
    d.send_keys(password, clear=True)
    time.sleep(1)

    if d(text="Next").exists:
        d(text="Next").click()
    else:
        nx1, ny1, nx2, ny2 = 1338, 661, 1478, 726
        d.click((nx1 + nx2) // 2, (ny1 + ny2) // 2)

    time.sleep(5)
    d.shell("input swipe 600 800 600 300 300")

    if d(textContains="Skip").wait(timeout=5):
        time.sleep(0.5)
        d(textContains="Skip").click()

    if d(textContains="Have Google Contacts automatically sync device").wait(timeout=5):
        for _ in range(3): 
            d.shell("input keyevent 61")  
            time.sleep(0.2)

    d.shell("input keyevent 66")

    if d(text="I agree").wait(timeout=35):
        time.sleep(2)
        d(text="I agree").click()
    else:
        ax1, ay1, ax2, ay2 = 1312, 715, 1478, 780
        time.sleep(2)
        d.click((ax1 + ax2) // 2, (ay1 + ay2) // 2)

    if d(textContains="Never lose your contacts").wait(timeout=7):
        if d(className="android.widget.Button", text="Don't turn on").exists:
            time.sleep(0.5)
            d(className="android.widget.Button", text="Don't turn on").click()
        else:
            d(className="android.widget.Button", packageName="com.google.android.gms").click()

    if d(text="MORE").wait(timeout=6):
        time.sleep(0.5)
        d(text="MORE").click()
    elif d(text="More").wait(timeout=6):
        time.sleep(0.5)
        d(text="More").click()
    elif d(textContains="MORE").wait(timeout=6):
        time.sleep(0.5)
        d(textContains="MORE").click()
    elif d(textContains="More").wait(timeout=6):
        time.sleep(0.5)
        d(textContains="More").click()
    else:
        mx1, my1, mx2, my2 = 1312, 715, 1478, 780
        d.click((mx1 + mx2) // 2, (my1 + my2) // 2)

    if d(text="ACCEPT").wait(timeout=6):
        time.sleep(0.5)
        d(text="ACCEPT").click()
    elif d(text="Accept").wait(timeout=6):
        time.sleep(0.5)
        d(text="Accept").click()
    elif d(textContains="ACCEPT").wait(timeout=6):
        time.sleep(0.5)
        d(textContains="ACCEPT").click()
    elif d(textContains="Accept").wait(timeout=6):
        time.sleep(0.5)
        d(textContains="Accept").click()
    else:
        ax1, ay1, ax2, ay2 = 1312, 715, 1478, 780
        d.click((ax1 + ax2) // 2, (ay1 + ay2) // 2)

        
    time.sleep(3)
    console.success(f"Successfully logged into gmail account", email=email) 
    return True


def read_tokens(path):
    if not os.path.isfile(path):
        print(f"Tokens file not found: {path}")
        sys.exit(1)
    toks = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            token = ln.split(":")[-1]
            toks.append((ln, token))
    return toks

def ensure_template(path):
    if os.path.isfile(path):
        return
    template = '''Java.perform(() => {
    const SharedPreferences = Java.use("android.app.SharedPreferencesImpl");
    SharedPreferences.getString.overload('java.lang.String', 'java.lang.String').implementation = function(key, defValue) {
        if (key === "token") {
            console.log("[*] getString called for token. Returning injected token.");
            return "__INJECTED_TOKEN__";
        }
        return this.getString(key, defValue);
    };
});'''
    with open(path, "w", encoding="utf-8") as f:
        f.write(template)

def write_js_with_token(template_path, out_path, token, device_serial):
    with open(template_path, "r", encoding="utf-8") as f:
        t = f.read()
    safe_token = token.replace("\\", "\\\\").replace("\"", "\\\"")
    js = t.replace("__INJECTED_TOKEN__", safe_token)
    
    device_out_path = f"{device_serial}_{out_path}"
    with open(device_out_path, "w", encoding="utf-8") as f:
        f.write(js)
    return device_out_path

def start_frida(js_path, package, device_serial):
    cmd = f'frida -D {device_serial} -f {package} -l "{js_path}"'
    creationflags = 0
    kw = {"shell": True}
    if platform.system() == "Windows":
        creationflags = subprocess.CREATE_NEW_CONSOLE
        kw["creationflags"] = creationflags
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
    time.sleep(4) 

    try:
        out, err = proc.communicate(timeout=2)
        if out:
            console.info(f"Frida stdout for {device_serial}", log=out.decode(errors="ignore"))
        if err:
            console.error(f"Frida stderr for {device_serial}", log=err.decode(errors="ignore"))
            increment_errors()
    except subprocess.TimeoutExpired:
        pass 

    return proc

def kill_proc(proc):
    if proc is None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    except Exception as e:
        print("Error terminating process:", e)
        increment_errors()

def open_discord_settings(device_serial):
    d = u2.connect(device_serial) 
    
    d.click(1700, 500)
    time.sleep(3)
    
    x = (469 + 553) // 2
    y = (980 + 1080) // 2
    d.click(x, y)
    time.sleep(2)


def redeem_trial(token, device_serial, plan_type):
    d = u2.connect(device_serial)
    display_token = token if len(token) <= 40 else token[:26] + "..."

    if d(textContains="You won't be charged until after your free 1 month").wait(timeout=30):
        time.sleep(1)

        if plan_type == "Monthly":
            if d(descriptionContains="Monthly").exists:
                time.sleep(0.5)
                d(descriptionContains="Monthly").click()
            else:
                console.error(f"Monthly plan option not found", token=display_token, )
                increment_errors()
                return None
        else:
            if d(descriptionContains="Yearly").exists:
                time.sleep(0.5)
                d(descriptionContains="Yearly").click()
            else:
                console.error(f"Yearly plan option not found", token=display_token, )
                increment_errors()
                return None

        time.sleep(2)
        if d(text="Continue on Google Play").wait(timeout=20):
            time.sleep(0.5)
            d(text="Continue on Google Play").click()

            if d(text="Add a payment method to your Google Account").wait(timeout=6) \
            or d(text="Add payment method to your Google Account").exists \
            or d(text="Payment method required").exists \
            or d(text="Add card").exists \
            or d(textContains="Add a payment method").exists \
            or d(textContains="Add payment method").exists:
                return "payment_required"

            return plan_type

    console.error(f"Confirmation text not found for trial selection", token=display_token, )
    increment_errors()
    return None



def get_account_name_from_hierarchy(device_serial):
    d = u2.connect(device_serial)
    xml = d.dump_hierarchy()
    
    pattern = r'content-desc="([^"]+)".*?clickable="true".*?bounds="\[0,980\]\[343,1080\]"'
    match = re.search(pattern, xml)
    if match:
        return match.group(1)
    
    pattern2 = r'text="([^"]+)".*?bounds="\[141,1014\]\[343,1049\]"'
    match2 = re.search(pattern2, xml)
    if match2:
        return match2.group(1)
    
    pattern3 = r'content-desc="([A-Za-z0-9_]+)".*?clickable="true".*?class="android\.view\.View"'
    match3 = re.search(pattern3, xml)
    if match3 and len(match3.group(1)) > 5:
        return match3.group(1)
    
    return None


def select_account_if_present(device_serial):
    d = u2.connect(device_serial)
    
    start_time = time.time()
    
    while time.time() - start_time < 40:
        xml = d.dump_hierarchy()
        
        if d(textContains="New").exists or d(textContains="Try Nitro").exists or d(textContains="Try").exists:
            time.sleep(1)
            for _ in range(4):
                d.click(1700, 500)
                time.sleep(1)
            
            popup_check_start = time.time()
            while time.time() - popup_check_start < 5:
                if d(textContains="Find study").exists:
                    d(description="Close").click()
                    break
                time.sleep(0.5)
            
            return True
        
        account_name = get_account_name_from_hierarchy(device_serial)
        if account_name:
            if d(text=account_name).exists:
                time.sleep(1)
                time.sleep(1)
                for _ in range(4):
                    d.click(1700, 500)
                    time.sleep(1)
                
                popup_check_start = time.time()
                while time.time() - popup_check_start < 5:
                    if d(textContains="Find study").exists:
                        d(description="Close").click()
                        break
                    time.sleep(0.5)
                
                return True
            
            if d(descriptionContains=account_name).exists:
                time.sleep(1)
                time.sleep(1)
                for _ in range(4):
                    d.click(1700, 500)
                    time.sleep(1)
                
                popup_check_start = time.time()
                while time.time() - popup_check_start < 5:
                    if d(textContains="Find study").exists:
                        d(description="Close").click()
                        break
                    time.sleep(0.5)
                
                return True
            
            pattern = rf'text="{re.escape(account_name)}".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
            match = re.search(pattern, xml)
            if match:
                x1, y1, x2, y2 = map(int, match.groups())
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                d.click(cx, cy)
                time.sleep(1)
                time.sleep(1)
                for _ in range(4):
                    d.click(1700, 500)
                    time.sleep(1)
                
                popup_check_start = time.time()
                while time.time() - popup_check_start < 5:
                    if d(textContains="Find study").exists:
                        d(description="Close").click()
                        break
                    time.sleep(0.5)
                
                return True
                
            pattern_desc = rf'content-desc="{re.escape(account_name)}".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
            match_desc = re.search(pattern_desc, xml)
            if match_desc:
                x1, y1, x2, y2 = map(int, match_desc.groups())
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                d.click(cx, cy)
                time.sleep(1)
                time.sleep(1)
                for _ in range(4):
                    d.click(1700, 500)
                    time.sleep(1)
                
                popup_check_start = time.time()
                while time.time() - popup_check_start < 5:
                    if d(textContains="Find study").exists:
                        d(description="Close").click()
                        break
                    time.sleep(0.5)
                
                return True
        
        time.sleep(1)
    
    console.error(f"Discord failed to load")
    increment_errors()
    return False



def process_token_with_smart_checks(device_serial, token, token2, plan_type):
    d = u2.connect(device_serial)
    display_token = token if len(token) <= 40 else token[:26] + "..."
    token_consumed = False

    checks = {
        "try_1month": lambda: d(text="Try 1 Month Free").exists,
        "redeem_confirm": lambda: d(textContains="You won't be charged until after your free 1 month").exists,
        "subscribe_or_buy": lambda: d(text="Subscribe").exists or d(text="Continue").exists or d(text="Buy").exists,
        "already_subscribed": lambda: d(textContains="You're already subscribed to Nitro").exists,
        "password_field": lambda: d(className="android.widget.EditText").exists,
        "verify_button": lambda: d(text="Verify").exists or d(text="VERIFY").exists,
        "no_thanks_radio": lambda: d(text="No, thanks").exists,
        "no_thanks_final": lambda: d(text="No thanks").exists,
        "success": lambda: d(textContains="You now have access to your").exists,
        "not_now": lambda: d(text="Get Google Play Points from purchases like this").exists,
        "loading": lambda: d(textContains="Loading").exists,
    }

    if not select_account_if_present(device_serial):
        return False
    
    time.sleep(2)
    for _ in range(4):
        d.click(1700, 500)
        time.sleep(1)

    open_discord_settings(device_serial)
    start_check = time.time()
    found_any_nitro = False
    found_trial = False

    while time.time() - start_check < 5:
        if d(description="Get Nitro, 1 MONTH FREE").exists or d(text="Get Nitro, 1 MONTH FREE").exists:
            found_any_nitro = True
            found_trial = True
            break
        elif d(text="Get Nitro").exists or d(description="Get Nitro").exists:
            found_any_nitro = True
            break
        time.sleep(0.5)

    if not found_any_nitro:
        console.error("Token already has nitro", token=display_token)
        save_already_token(token2)
        pop_first_nonempty_line(TOKENS_FILE)
        return "already_has_nitro"

    if found_trial:
        try:
            if d(description="Get Nitro, 1 MONTH FREE").exists:
                d(description="Get Nitro, 1 MONTH FREE").click()
            else:
                d(text="Get Nitro, 1 MONTH FREE").click()
        except Exception as e:
            console.error(f"Failed to click Get Nitro button: {e}")
            increment_errors()
    else:
        time.sleep(300)
        return "retry_same_token"





    start_time = time.time()
    
    while checks and (time.time() - start_time < 120):
        handled_any = False

        for key, cond in list(checks.items()):
            if cond():
                handled_any = True

                if key == "loading":
                    time.sleep(2)
                    del checks[key]
                    continue

                elif key == "try_1month":
                    time.sleep(1)
                    d(text="Try 1 Month Free").click()
                    del checks[key]
                    continue

                elif key == "redeem_confirm":
                    time.sleep(1)
                    result = redeem_trial(display_token, device_serial, plan_type)
                    if result == "payment_required":
                        console.error(f"Failed to redeem trial, Gmail doesn't have payment method added", )
                        device_info = get_device_email_info(device_serial)
                        if not device_info:
                            console.error(f"No email assigned to device {device_serial}")
                            increment_errors()
                            return False

                        email = device_info["email"]
                        remove_fully_used_email_from_file(email)
                        remove_first_gmail_account(device_serial)
                        time.sleep(3)

                        if not assign_next_available_email(device_serial):
                            console.error(f"No more emails available", )
                            return "no_emails"

                        if not perform_gmail_login(device_serial):
                            console.error(f"Failed to login with new email", )
                            return "login_failed"

                        with token_queue_lock:
                            global_token_queue.insert(0, (token2, token))
                        return "gmail_switched"

                    elif result == "gmail_switched":
                        with token_queue_lock:
                            global_token_queue.insert(0, (token2, token))
                        return "gmail_switched"

                    elif result in ["login_failed"]:
                        increment_failed()
                        return False

                    elif result is None:
                        console.error("Failed to select plan", token=display_token, )
                        increment_errors()
                        return False

                    del checks[key]
                    continue

                elif key == "subscribe_or_buy":
                    time.sleep(1)
                    d.shell("input swipe 600 800 600 300 300")
                    time.sleep(0.5)

                    if d(text="Subscribe").exists:
                        time.sleep(0.5)
                        d(text="Subscribe").click()
                    elif d(text="Buy").exists:
                        time.sleep(0.5)
                        d(text="Buy").click()
                    elif d(text="Continue").exists:
                        time.sleep(0.5)
                        d(text="Continue").click()
                        
                    del checks[key]
                    time.sleep(2)
                    if d(className="android.widget.EditText").exists:
                        device_info = get_device_email_info(device_serial)
                        if device_info:
                            password = device_info["password"]
                            time.sleep(0.5)
                            d(className="android.widget.EditText").click()
                            time.sleep(0.5)
                            d.send_keys(password, clear=True)
                            time.sleep(1)

                            if d(text="Verify").exists:
                                d(text="Verify").click()
                            elif d(text="VERIFY").exists:
                                d(text="VERIFY").click()
                            time.sleep(2)

                            start_auth_check = time.time()
                            while time.time() - start_auth_check < 15:
                                if (
                                    d(text="Purchase Authentication").exists
                                    or d(textContains="We have sent you a text message with a code").exists
                                    or d(text="RESEND CODE").exists
                                    or d(text="Learn more about authentication").exists
                                    or d(text="Need some help?").exists
                                ):
                                    console.error(
                                        "Purchase Authentication detected, removing email and assigning new one",
                                        
                                    )

                                    device_info = get_device_email_info(device_serial)
                                    if not device_info:
                                        console.error(f"No email assigned to device {device_serial}")
                                        increment_errors()
                                        return False

                                    email = device_info["email"]
                                    remove_fully_used_email_from_file(email)
                                    remove_first_gmail_account(device_serial)
                                    time.sleep(3)

                                    if not assign_next_available_email(device_serial):
                                        console.error(f"No more emails available", )
                                        break

                                    if not perform_gmail_login(device_serial):
                                        console.error(f"Failed to login with new email", )
                                        break

                                    with token_queue_lock:
                                        global_token_queue.insert(0, (token2, token))

                                    break
                                time.sleep(1)
                    continue

                elif key == "already_subscribed":
                    console.error(f"Gmail is already subscribed to this nitro plan", 
                                token=display_token, 
                                plan=plan_type, 
                                )
                    
                    mark_plan_used(device_serial, plan_type, success=False)
                    device_info = get_device_email_info(device_serial)
                    if not device_info:
                        console.error(f"No email assigned to device {device_serial}")
                        increment_errors()
                        return False
                        
                    email = device_info["email"]
                    remove_fully_used_email_from_file(email)
                    remove_first_gmail_account(device_serial)
                    time.sleep(3)

                    if not assign_next_available_email(device_serial):
                        console.error(f"No more emails available for reassignment", )
                        return "no_emails"

                    if not perform_gmail_login(device_serial):
                        console.error(f"Failed to login with new Gmail account", )
                        return "login_failed"

                    with token_queue_lock:
                        global_token_queue.insert(0, (token2, token))

                    console.info(f"Switched to a new Gmail after already_subscribed", )
                    return "gmail_switched"

                elif key == "no_thanks_radio":
                    time.sleep(0.5)
                    d(text="No, thanks").click()
                    time.sleep(1)
                    if d(text="OK").exists:
                        time.sleep(0.5)
                        d(text="OK").click()
                    del checks[key]
                    continue

                elif key == "no_thanks_final":
                    time.sleep(0.5)
                    d(text="No thanks").click()
                    del checks[key]
                    continue
                    
                elif key == "not_now":
                    time.sleep(0.5)
                    d(text="Not now").click()
                    del checks[key]
                    continue

                elif key == "success":
                    console.redeemed(f"Successfully redeemed trial", 
                                  type=plan_type, 
                                  token=display_token, 
                                  )
                    
                    save_redeemed_token(token2, plan_type)
                    pop_first_nonempty_line(TOKENS_FILE)
                    token_consumed = True
                    with assignment_lock:
                        if device_serial in device_assignments:
                            device_assignments[device_serial]["failed_attempts"] = 0
                    mark_plan_used(device_serial, plan_type, success=True)
                    increment_redeemed()
                    return True

        if not handled_any:
            time.sleep(2)

    console.error(f"Token processing timed out or failed", 
                 token=display_token, 
                 plan=plan_type,
                 )
    
    with assignment_lock:
        if device_serial in device_assignments:
            device_assignments[device_serial]["failed_attempts"] += 1
            failed_count = device_assignments[device_serial]["failed_attempts"]
        else:
            failed_count = 1

    hierarchy = d.dump_hierarchy()
    failure_indicators = [
        "Insufficient Funds",
        "Payment declined"
    ]
    if any(indicator in hierarchy for indicator in failure_indicators):
        console.info(f"Gmail's payment method appears to be invalid or missing, removing...", )
        remove_first_gmail_account(device_serial)
        with assignment_lock:
            if device_serial in device_assignments:
                device_assignments[device_serial]["failed_attempts"] = 0
        time.sleep(2)
        if not assign_next_available_email(device_serial):
            console.error(f"No more emails available after removing faulty Gmail", )
            return False
        if not perform_gmail_login(device_serial):
            console.error(f"Failed to login with newly assigned email", )
            return False
        with token_queue_lock:
            global_token_queue.insert(0, (token2, token))
        return "gmail_switched"

    if failed_count >= 2:
        remove_first_gmail_account(device_serial)
        with assignment_lock:
            if device_serial in device_assignments:
                device_assignments[device_serial]["failed_attempts"] = 0 
        time.sleep(2)
        if not assign_next_available_email(device_serial):
            console.error(f"No more emails available after 2 failures", )
            return False
        if not perform_gmail_login(device_serial):
            console.error(f"Failed to login with newly assigned email after failure reset", )
            return False
        with token_queue_lock:
            global_token_queue.insert(0, (token2, token))
        return "gmail_switched"

    if not token_consumed:
        save_error_token(token2)
        pop_first_nonempty_line(TOKENS_FILE)
        token_consumed = True

    increment_failed()
    return False


def inject_tokens_for_device_continuous(device_serial):
    try:
        ensure_template(TEMPLATE_PATH)
        device = adbutils.adb.device(device_serial)

        while True:
            available_emails, available_tokens, available_redeems = check_resources_available()

            token_data = get_next_token()
            if not token_data:
                console.info("No more tokens available")
                break

            original_line, token = token_data
            available_plan = get_next_available_plan(device_serial)
            if not available_plan:
                remove_first_gmail_account(device_serial)
                time.sleep(2)

                if not assign_next_available_email(device_serial):
                    console.info("No more emails available")
                    with token_queue_lock:
                        global_token_queue.insert(0, (original_line, token))
                    break

                if not perform_gmail_login(device_serial):
                    console.error("Failed to login with new email")
                    with token_queue_lock:
                        global_token_queue.insert(0, (original_line, token))
                    increment_errors()
                    break

                available_plan = get_next_available_plan(device_serial)
                if not available_plan:
                    with token_queue_lock:
                        global_token_queue.insert(0, (original_line, token))
                    increment_errors()
                    break

            display_token = token if len(token) <= 40 else token[:26] + "..."
            console.info("Processing token", token=display_token, plan=available_plan)

            js_path = write_js_with_token(TEMPLATE_PATH, OUT_JS_PATH, token, device_serial)

            while True:
                proc = None
                try:
                    result = device.shell(["pm", "clear", PACKAGE_NAME])
                    if "Success" not in result and "success" not in result:
                        console.error("Failed to clear discord storage", result=result.strip())
                        increment_errors()

                    time.sleep(5)
                    proc = start_frida(js_path, PACKAGE_NAME, device_serial)

                    console.success("Successfully logged into token",
                                    token=display_token, pid=proc.pid)

                    with assignment_lock:
                        if device_serial in device_assignments:
                            device_assignments[device_serial]["current_plan"] = available_plan

                    result = process_token_with_smart_checks(
                        device_serial,
                        display_token,
                        original_line,
                        available_plan
                    )

                    if result is True:
                        break
                    elif result == "already_has_nitro":
                        break
                    elif result == "retry_same_token":
                        continue
                    else:
                        console.error("Token failed to redeem", token=display_token)
                        break

                except Exception as e:
                    console.error("Error during token processing:", error=str(e))
                    increment_errors()
                finally:
                    if proc:
                        kill_proc(proc)
                    time.sleep(2)

                break

            try:
                os.remove(js_path)
            except:
                pass

    except Exception as e:
        console.error("Error processing tokens continuously", error=str(e))
        increment_errors()

def remove_first_gmail_account(device_serial):
    device = adbutils.adb.device(device_serial)
    d = u2.connect(device_serial)
    device.shell("am start -a android.settings.SYNC_SETTINGS")
    time.sleep(3)

    xml = d.dump_hierarchy()

    gmail_match = re.search(
        r'text="([\w\.\-]+@gmail\.com)".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        xml,
    )

    if not gmail_match:
        return

    email, x1, y1, x2, y2 = gmail_match.groups()
    x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

    device.shell(f"input tap {cx} {cy}")
    time.sleep(2)

    xml = d.dump_hierarchy()
    remove_match = re.search(
        r'resource-id="com\.android\.settings:id/button".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        xml,
    )
    if not remove_match:
        console.error(f"REMOVE ACCOUNT button not found.", )
        increment_errors()
        return

    x1, y1, x2, y2 = map(int, remove_match.groups())
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    device.shell(f"input tap {cx} {cy}")
    time.sleep(1)

    xml = d.dump_hierarchy()
    confirm_match = re.search(
        r'resource-id="android:id/button1".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        xml,
    )
    if confirm_match:
        x1, y1, x2, y2 = map(int, confirm_match.groups())
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        device.shell(f"input tap {cx} {cy}")
    else:
        console.error(f"Confirmation REMOVE ACCOUNT button not found.", )
        increment_errors()

def get_available_devices():
    devices = adbutils.adb.device_list()
    if not devices:
        console.error("No devices found. Make sure LDPlayer instances are running and ADB is enabled.")
        sys.exit(1)
    
    return devices

def check_resources_available():
    try:
        with open(EMAILS_FILE, "r", encoding="utf-8") as f:
            email_lines = [line.strip() for line in f.readlines() if line.strip() and ":" in line]
        
        available_emails = 0
        available_redeems = 0
        
        for line in email_lines:
            base_part = line.split("?")[0] if "?" in line else line
            
            yearly_used = False
            monthly_used = False
            
            if "?" in line:
                params_part = line.split("?", 1)[1]
                if "yearly=1" in params_part or "yearly=true" in params_part:
                    yearly_used = True
                if "monthly=1" in params_part or "monthly=true" in params_part:
                    monthly_used = True
            
            if not (yearly_used and monthly_used):
                available_emails += 1
                
                if not yearly_used:
                    available_redeems += 1
                if not monthly_used:
                    available_redeems += 1
        
        with open(TOKENS_FILE, "r", encoding="utf-8") as f:
            available_tokens = len([line.strip() for line in f.readlines() if line.strip() and not line.startswith("#")])
        
        return available_emails, available_tokens, available_redeems
    except Exception as e:
        console.error(f"Error checking resources: {e}")
        increment_errors()
        return 0, 0, 0

def initialize_stats():
    global stats
    available_emails, available_tokens, available_redeems = check_resources_available()
    
    with stats_lock:
        stats["current_emails"] = available_emails
        stats["current_tokens"] = available_tokens
        stats["initial_emails"] = available_emails
        stats["initial_tokens"] = available_tokens
        stats["redeemed"] = 0
        stats["failed"] = 0
        stats["errors"] = 0
    
    update_title()

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

columns = shutil.get_terminal_size().columns

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

if __name__ == "__main__":
    try:
        initialize_stats()
        
        initialize_stats()
        
        initialize_token_queue()
        clear_console()
        print(f"{bcolors.OKBLUE}Google Play Nitro Redeemer{bcolors.ENDC} v1.5.0".center(columns))
        print()
        
        devices = get_available_devices()
        
        available_emails, available_tokens, available_redeems = check_resources_available()
        
        with stats_lock:
            stats["current_emails"] = available_emails
            stats["current_tokens"] = available_tokens
        update_title()
        
        if available_emails == 0:
            console.error(f"No emails available")
            sys.exit(1)
        
        if available_tokens == 0:
            console.error(f"No tokens available")
            sys.exit(1)
        
        max_possible_instances = min(available_emails, len(devices))
        
        while True:
            try:
                num_instances = int(console.input(f"How many instances do you want to run? (Max: {max_possible_instances}): "))
                if 1 <= num_instances <= max_possible_instances:
                    break
                else:
                    print(f"Please enter a number between 1 and {max_possible_instances}")
            except ValueError:
                print("Please enter a valid number")

        selected_devices = devices[:num_instances]
        
        prepare_email_queue()
        print()
        assign_emails_to_devices([device.serial for device in selected_devices])
        
        def initialize_and_process_device_continuous(device_serial):
            try:
                remove_first_gmail_account(device_serial)
                if perform_gmail_login(device_serial):
                    inject_tokens_for_device_continuous(device_serial)
                else:
                    console.error(f"Failed to login to Gmail on device {device_serial}")
                    increment_errors()
            except Exception as e:
                console.error(f"Error on device {device_serial}: {str(e)}")
                increment_errors()
        
        with ThreadPoolExecutor(max_workers=num_instances) as executor:
            futures = []
            for device in selected_devices:
                future = executor.submit(initialize_and_process_device_continuous, device.serial)
                futures.append(future)
            
            for future in futures:
                future.result()
        
        remaining_emails, remaining_tokens, remaining_redeems = check_resources_available()
        
        with stats_lock:
            stats["current_emails"] = remaining_emails
            stats["current_tokens"] = remaining_tokens
        update_title()
        
        print()
        if remaining_emails == 0 and remaining_tokens == 0:
            console.success("All materials exhausted!")
        elif remaining_emails == 0:
            console.error(f"All emails exhausted, {remaining_tokens} tokens remaining")
        elif remaining_tokens == 0:
            console.error(f"All tokens finished, {remaining_emails} emails with {remaining_redeems} redemptions remaining")
        else:
            console.info(f"Process completed. Remaining: {remaining_emails} emails with {remaining_redeems} redemptions, {remaining_tokens} tokens")
        
    except KeyboardInterrupt:
        console.error("Operation interrupted by user.")
        sys.exit(1)
    except Exception as e:
        console.error("Unexpected error:", error=str(e))
        increment_errors()
        sys.exit(1)