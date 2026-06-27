#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phone Number Bulk OTP Tool
==========================
এটি একটি অটোমেটিক টুল যা numbers.txt ফাইল থেকে ফোন নম্বর পড়ে,
প্রতিটি নম্বরের জন্য ChatGPT সাইন-আপ ফর্ম পূরণ করে "Send OTP" ক্লিক করে।

কীভাবে ব্যবহার করবেন:
1. numbers.txt ফাইল বানান (প্রতি লাইনে একটি ফোন নম্বর)
2. python main.py রান করুন
3. আউটপুট দেখুন success.txt এবং failed.txt ফাইলে
"""

import json
import logging
import os
import random
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================================
# কনফিগারেশন লোড করুন
# ============================================================
_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")


def load_config() -> Dict[str, Any]:
    """কনফিগ.yaml ফাইল লোড করুন"""
    if not os.path.exists(_CONFIG_FILE):
        # ডিফল্ট কনফিগ তৈরি করুন
        default_config = {
            "total_accounts": 1,
            "temp_mail": {
                "worker_domain": "",
                "email_domains": ["tempmail.com"],
                "admin_password": ""
            },
            "output": {
                "accounts_file": "accounts.txt",
                "invite_tracker_file": "invite_tracker.json",
                "results_file": "results.txt"
            },
            "teams": []
        }
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(default_config, f, allow_unicode=True)
        print(f"✅ ডিফল্ট config.yaml তৈরি করা হয়েছে: {_CONFIG_FILE}")
        print("⚠️ দয়া করে config.yaml এ আপনার temp_mail সেটিংস দিন")
        return default_config

    with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


cfg = load_config()

# ============================================================
# লগিং সেটআপ
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("otp-tool")

# ============================================================
# HTTP সেশন
# ============================================================
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)


def create_session(proxy: str = "") -> requests.Session:
    """HTTP সেশন তৈরি করুন"""
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    return s


http_session = create_session()

# ============================================================
# ফোন নম্বর লিস্ট পড়ুন
# ============================================================
def load_phone_numbers(filename: str = "numbers.txt") -> List[str]:
    """numbers.txt ফাইল থেকে ফোন নম্বর লিস্ট পড়ুন"""
    if not os.path.exists(filename):
        # ডিফল্ট ফাইল তৈরি করুন
        with open(filename, "w", encoding="utf-8") as f:
            f.write("# ফোন নম্বর লিস্ট (প্রতি লাইনে একটি নম্বর)\n")
            f.write("# ফরম্যাট: +কান্ট্রিকোড নম্বর (যেমন: +8801712345678)\n")
            f.write("+8801712345678\n")
            f.write("+8801712345679\n")
            f.write("+8801712345680\n")
        print(f"✅ {filename} তৈরি করা হয়েছে। দয়া করে এতে আপনার ফোন নম্বর দিন।")
        return []

    with open(filename, "r", encoding="utf-8") as f:
        numbers = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return numbers


# ============================================================
# OTP সেন্ড ফাংশন (HTTP প্রটোকল) - আপডেটেড
# ============================================================
def send_otp_via_http(phone_number: str, email: str = "") -> Tuple[bool, str]:
    """
    HTTP প্রটোকলের মাধ্যমে ফোন নম্বরে OTP সেন্ড করুন
    
    এটি ChatGPT-এর সাইন-আপ API কল করে:
    1. প্রথমে authorize/continue কল করে login_session পান
    2. তারপর phone OTP সেন্ড API কল করে
    """
    try:
        device_id = str(uuid.uuid4())
        session = create_session()

        # Step 1: OAuth authorize পেজে যান (login_session পেতে)
        auth_url = "https://auth.openai.com/oauth/authorize"
        params = {
            "response_type": "code",
            "client_id": "pdlLIX2Y72MIl2rhLhTE9VV9bN905kBh",
            "redirect_uri": "https://chatgpt.com/api/auth/callback/openai",
            "scope": "openid profile email offline_access",
            "state": str(uuid.uuid4()),
            "screen_hint": "signup"
        }
        
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "user-agent": USER_AGENT,
            "sec-ch-ua": '"Google Chrome";v="145"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "upgrade-insecure-requests": "1"
        }
        
        session.get(auth_url, params=params, headers=headers, allow_redirects=True, timeout=30)

        # Step 2: authorize/continue কল করুন (ফোন নম্বর সহ)
        api_url = "https://auth.openai.com/api/accounts/authorize/continue"
        payload = {
            "username": {
                "kind": "phone_num",          # ✅ ফিক্স: 'phone' থেকে 'phone_num' করা হয়েছে
                "value": phone_number
            },
            "screen_hint": "signup"
        }
        
        headers_api = {
            "accept": "application/json",
            "content-type": "application/json",
            "origin": "https://auth.openai.com",
            "referer": "https://auth.openai.com/create-account",
            "user-agent": USER_AGENT,
            "oai-device-id": device_id,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin"
        }
        
        response = session.post(api_url, json=payload, headers=headers_api, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            continue_url = data.get("continue_url", "")
            page_type = data.get("page", {}).get("type", "")
            
            # চেক করুন ফোন OTP পেজে রিডাইরেক্ট করেছে কিনা
            if "phone" in str(page_type).lower() or "phone" in continue_url:
                logger.info(f"✅ OTP সেন্ড হয়েছে: {phone_number}")
                return True, f"OTP পাঠানো হয়েছে {phone_number} এ"
            else:
                logger.info(f"⚠️ অন্য পেজে রিডাইরেক্ট: {page_type}")
                return False, f"রিডাইরেক্ট: {page_type}"
        else:
            logger.warning(f"❌ API কল ফেল: {response.status_code} | {response.text[:200]}")
            return False, f"HTTP {response.status_code}"

    except Exception as e:
        logger.error(f"❌ Error sending OTP to {phone_number}: {e}")
        return False, str(e)


# ============================================================
# ফোন নম্বর চেক (বেসিক ভ্যালিডেশন)
# ============================================================
def validate_phone_number(phone: str) -> bool:
    """ফোন নম্বর ভ্যালিড কিনা চেক করুন"""
    # সরল ভ্যালিডেশন: + দিয়ে শুরু এবং 10-15 ডিজিট
    if not phone:
        return False
    if not phone.startswith("+"):
        return False
    digits = ''.join(filter(str.isdigit, phone))
    return 10 <= len(digits) <= 15


# ============================================================
# ফলাফল সেভ করা
# ============================================================
def save_success(phone: str, message: str = ""):
    """সফল নম্বর সেভ করুন"""
    os.makedirs("output", exist_ok=True)
    with open("output/success.txt", "a", encoding="utf-8") as f:
        f.write(f"{phone} | {message} | {time.strftime('%Y-%m-%d %H:%M:%S')}\n")


def save_failed(phone: str, reason: str = ""):
    """ব্যর্থ নম্বর সেভ করুন"""
    os.makedirs("output", exist_ok=True)
    with open("output/failed.txt", "a", encoding="utf-8") as f:
        f.write(f"{phone} | {reason} | {time.strftime('%Y-%m-%d %H:%M:%S')}\n")


def save_progress(phone: str, status: str):
    """প্রোগ্রেস লগ সেভ করুন (JSON ফরম্যাটে)"""
    progress_file = "output/progress.json"
    os.makedirs("output", exist_ok=True)
    try:
        if os.path.exists(progress_file):
            with open(progress_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"processed": [], "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
        
        data["processed"].append({"phone": phone, "status": status, "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"প্রোগ্রেস সেভ করতে ব্যর্থ: {e}")


# ============================================================
# মেইন ফাংশন - পুরো প্রক্রিয়া চালান
# ============================================================
def main():
    """মেইন ফাংশন - ফোন নম্বর লিস্ট পড়ে প্রতিটি নম্বরে OTP সেন্ড করে"""
    
    print("\n" + "="*60)
    print("📱 Phone Number Bulk OTP Tool v1.1")
    print("="*60)
    print("📋 ফোন নম্বর লিস্ট পড়া হচ্ছে...")
    
    # ফোন নম্বর লিস্ট লোড করুন
    numbers = load_phone_numbers()
    
    if not numbers:
        print("❌ numbers.txt ফাইল খালি বা পাওয়া যায়নি।")
        print("📝 numbers.txt ফাইলে প্রতি লাইনে একটি ফোন নম্বর দিন (যেমন: +8801712345678)")
        return
    
    print(f"✅ মোট {len(numbers)} টি নম্বর পাওয়া গেছে")
    print("-"*60)
    
    # কাউন্টার
    total = len(numbers)
    success_count = 0
    failed_count = 0
    
    # প্রতি নম্বরের জন্য OTP সেন্ড করুন
    for idx, phone in enumerate(numbers, 1):
        print(f"\n[{idx}/{total}] 📱 নম্বর: {phone}")
        
        # ভ্যালিডেশন
        if not validate_phone_number(phone):
            logger.warning(f"⚠️ অবৈধ ফোন নম্বর: {phone} (স্কিপ করা হচ্ছে)")
            save_failed(phone, "Invalid phone number format")
            save_progress(phone, "failed")
            failed_count += 1
            continue
        
        # OTP সেন্ড করুন
        print(f"⏳ {phone} এ OTP পাঠানো হচ্ছে...")
        success, message = send_otp_via_http(phone)
        
        if success:
            print(f"✅ OTP সফলভাবে পাঠানো হয়েছে: {phone}")
            save_success(phone, message)
            save_progress(phone, "success")
            success_count += 1
        else:
            print(f"❌ OTP পাঠাতে ব্যর্থ: {phone} | কারণ: {message}")
            save_failed(phone, message)
            save_progress(phone, "failed")
            failed_count += 1
        
        # রেট লিমিট এড়ানোর জন্য অপেক্ষা
        if idx < total:
            wait_time = random.randint(3, 8)
            print(f"⏳ {wait_time} সেকেন্ড অপেক্ষা করছি (রেট লিমিট এড়াতে)...")
            time.sleep(wait_time)
    
    # সারাংশ
    print("\n" + "="*60)
    print("📊 সারাংশ")
    print("="*60)
    print(f"✅ সফল: {success_count}")
    print(f"❌ ব্যর্থ: {failed_count}")
    print(f"📝 মোট: {total}")
    print("\n📁 আউটপুট ফাইল:")
    print(f"   output/success.txt - সফল নম্বরের লিস্ট")
    print(f"   output/failed.txt - ব্যর্থ নম্বরের লিস্ট")
    print(f"   output/progress.json - সম্পূর্ণ প্রোগ্রেস লগ")
    print("="*60)


# ============================================================
# প্রোগ্রাম এন্ট্রি
# ============================================================
if __name__ == "__main__":
    main()