import requests
import json
import time
import random
from datetime import datetime, timedelta
import threading
from typing import List, Dict, Optional
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
import pytz

class SomniaMultiAccountBot:
    def __init__(self):
        self.base_url = "https://quest.somnia.network/api"
        self.accounts = []
        self.proxies = []
        self.use_proxy = False
        self.next_claim_time = None
        self.last_claim_time = None

        # Common headers
        self.headers = {
            'authority': 'quest.somnia.network',
            'accept': 'application/json',
            'accept-language': 'en-US,en;q=0.6',
            'content-type': 'application/json',
            'origin': 'https://quest.somnia.network',
            'referer': 'https://quest.somnia.network/',
            'sec-ch-ua': '"Brave";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'sec-gpc': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
        }

    def generate_signature(self, private_key: str) -> Dict:
        """Generate signature dari private key"""
        try:
            message_dict = {"onboardingUrl":"https://quest.somnia.network"}
            message_str = json.dumps(message_dict, separators=(',', ':'))

            if private_key.startswith('0x'):
                private_key = private_key[2:]

            account = Account.from_key(private_key)
            message_hash = encode_defunct(text=message_str)
            signed_message = account.sign_message(message_hash)
            signature = signed_message.signature.hex()

            return {
                'wallet_address': account.address,
                'signature': signature,
                'message': message_str
            }
        except Exception as e:
            print(f"❌ Error generating signature: {e}")
            return None

    def add_account_with_private_key(self, private_key: str, account_name: str = None):
        """Menambah akun dengan private key"""
        signature_data = self.generate_signature(private_key)
        if not signature_data:
            return False

        account = {
            'wallet_address': signature_data['wallet_address'],
            'signature': signature_data['signature'],
            'private_key': private_key,
            'name': account_name or signature_data['wallet_address'][:8] + "...",
            'token': None,
            'last_claim': None,
            'last_claim_date': None,
            'status': 'ready',
            'points': 0,
            'streak': 0,
            'username': None,
            'discord': None,
            'twitter': None,
            'telegram': None,
            'raw_user_data': {}
        }
        self.accounts.append(account)
        return True

    def load_private_keys_from_txt(self, filename: str = "pk.txt"):
        """Load private keys dari file txt"""
        try:
            with open(filename, 'r') as f:
                lines = f.readlines()

            count = 0
            for i, line in enumerate(lines, 1):
                pk = line.strip()
                if pk and not pk.startswith('#'):
                    if self.add_account_with_private_key(pk, f"Acc{i}"):
                        count += 1

            return count
        except FileNotFoundError:
            print(f"❌ File {filename} tidak ditemukan")
            return 0
        except Exception as e:
            print(f"❌ Error loading private keys: {e}")
            return 0

    def load_proxies_from_txt(self, filename: str = "proxy.txt"):
        """Load proxy dari file txt"""
        try:
            with open(filename, 'r') as f:
                lines = f.readlines()

            count = 0
            for line in lines:
                proxy = line.strip()
                if proxy and not proxy.startswith('#'):
                    if proxy.startswith('http://') or proxy.startswith('https://'):
                        self.proxies.append(proxy)
                        count += 1

            return count
        except FileNotFoundError:
            return 0
        except Exception as e:
            print(f"❌ Error loading proxies: {e}")
            return 0

    def get_random_proxy(self) -> Optional[Dict]:
        """Mendapatkan proxy random dari list"""
        if not self.proxies or not self.use_proxy:
            return None

        proxy_str = random.choice(self.proxies)
        return {
            'http': proxy_str,
            'https': proxy_str
        }

    def create_session(self, account: Dict):
        """Membuat session dengan headers dan proxy"""
        if 'session' in account:
            session = account['session']
        else:
            session = requests.Session()
            session.headers.update(self.headers)

            if self.use_proxy and self.proxies:
                proxy = self.get_random_proxy()
                if proxy:
                    session.proxies.update(proxy)

        if account.get('token'):
            session.headers.update({
                'authorization': f"Bearer {account['token']}"
            })

        return session

    def onboard_account(self, account: Dict, silent: bool = False) -> bool:
        """Sign in untuk satu akun"""
        session = self.create_session(account)
        url = f"{self.base_url}/auth/onboard"

        signature = account['signature']
        if not signature.startswith('0x'):
            signature = '0x' + signature

        payload = {
            "signature": signature,
            "walletAddress": account['wallet_address']
        }

        try:
            response = session.post(url, json=payload, timeout=30)

            if response.status_code == 200:
                response_data = response.json()
                if 'token' in response_data:
                    account['token'] = response_data['token']
                    account['session'] = session
                    return True

            if not silent:
                print(f"❌ Login gagal: HTTP {response.status_code}")
            return False
        except Exception as e:
            if not silent:
                print(f"❌ Error login: {str(e)[:50]}")
            return False

    def safe_int(self, value, default=0):
        """Safely convert value to int"""
        try:
            if value is None:
                return default
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                return int(value.replace(',', ''))
            return default
        except:
            return default

    def extract_points_from_data(self, user_data: dict) -> int:
        """Extract points dari berbagai kemungkinan field di API"""
        possible_fields = [
            'totalPoints',
            'points',
            'total_points',
            'point',
            'finalPoints',
            'accumulatedPoints',
            'userPoints'
        ]

        for field in possible_fields:
            if field in user_data and user_data[field] is not None:
                points = self.safe_int(user_data[field])
                if points > 0:
                    return points

        return 0

    def get_user_info(self, account: Dict, silent: bool = False) -> bool:
        """Mendapatkan user info dengan deteksi points yang lebih baik"""
        session = self.create_session(account)
        url = f"{self.base_url}/users/me"

        try:
            response = session.get(url, timeout=30)

            if response.status_code == 200:
                user_data = response.json()

                account['raw_user_data'] = user_data
                account['user_id'] = user_data.get('id')
                account['referral_code'] = user_data.get('referralCode')
                account['username'] = user_data.get('username')
                account['is_bot'] = user_data.get('isBot')

                socials = user_data.get('socials', {})
                if isinstance(socials, dict):
                    account['discord'] = socials.get('discord', {}).get('username')
                    account['twitter'] = socials.get('twitter', {}).get('username')
                    account['telegram'] = socials.get('telegram', {}).get('username')

                points = self.extract_points_from_data(user_data)
                account['points'] = points
                account['streak'] = self.safe_int(user_data.get('streakCount', 0))

                if 'lastGmAt' in user_data and user_data['lastGmAt']:
                    account['last_claim'] = user_data['lastGmAt']

                if 'nextLogin' in user_data and user_data['nextLogin']:
                    account['next_login'] = user_data['nextLogin']

                if not silent:
                    print(f"   📊 Debug - Points found: {points}")
                    print(f"   📊 Debug - Streak: {account['streak']}")

                return True

            if not silent:
                print(f"❌ Get info gagal: HTTP {response.status_code}")
            return False
        except Exception as e:
            if not silent:
                print(f"❌ Error get info: {str(e)[:50]}")
            return False

    def check_already_claimed_today(self, account: Dict) -> bool:
        """Cek apakah sudah claim hari ini"""
        if not account.get('last_claim'):
            return False

        try:
            last_claim_str = account['last_claim']
            if isinstance(last_claim_str, str):
                last_claim = datetime.fromisoformat(last_claim_str.replace('Z', '+00:00'))
            else:
                return False

            wib = pytz.timezone('Asia/Jakarta')
            now_wib = datetime.now(wib)
            last_claim_wib = last_claim.astimezone(wib)

            account['last_claim_date'] = last_claim_wib.strftime('%d/%m/%Y %H:%M WIB')

            if last_claim_wib.date() == now_wib.date():
                return True

            return False
        except Exception as e:
            return False

    def claim_daily_gm(self, account: Dict, silent: bool = False) -> Dict:
        """Claim daily GM untuk satu akun"""
        session = self.create_session(account)
        url = f"{self.base_url}/users/gm"

        if not account.get('token'):
            return {'success': False, 'message': 'No token'}

        old_points = self.safe_int(account.get('points', 0))

        try:
            response = session.post(url, timeout=30)

            if response.status_code == 200:
                result = response.json()

                new_points = self.safe_int(result.get('finalPoints', 0))

                if new_points == 0:
                    new_points = self.extract_points_from_data(result)

                streak = self.safe_int(result.get('streakCount', 0))
                booster = self.safe_int(result.get('dailyBooster', 0))

                earned = new_points - old_points

                account['last_claim'] = datetime.now().isoformat()
                account['status'] = 'claimed'
                account['points'] = new_points
                account['streak'] = streak

                return {
                    'success': True,
                    'old_points': old_points,
                    'earned': earned,
                    'new_points': new_points,
                    'streak': streak,
                    'booster': booster
                }
            else:
                error_msg = "Unknown error"
                try:
                    error_data = response.json()
                    error_msg = error_data.get('message', 'Unknown error')
                except:
                    error_msg = response.text[:100] if response.text else f"HTTP {response.status_code}"

                return {'success': False, 'message': error_msg}
        except Exception as e:
            return {'success': False, 'message': str(e)[:100]}

    def shorten_text(self, text: str, length: int = 10) -> str:
        """Memendekkan text untuk tampilan"""
        if not text:
            return "-"
        text = str(text)
        if len(text) <= length:
            return text
        return text[:length-3] + "..."

    def display_already_claimed_account(self, account: Dict):
        """Tampilkan info lengkap untuk akun yang sudah claim hari ini"""
        print(f"\n{'='*70}")
        print(f"✅ SUDAH CLAIM HARI INI")
        print(f"{'='*70}")

        print(f"🆔 Wallet Address : {account['wallet_address']}")
        print(f"👤 Username       : {account.get('username') or '-'}")

        if account.get('discord'):
            print(f"💬 Discord        : {account['discord']}")
        if account.get('twitter'):
            print(f"🐦 Twitter        : {account['twitter']}")
        if account.get('telegram'):
            print(f"✈️  Telegram       : {account['telegram']}")

        print(f"💰 Total Points   : {account.get('points', 0):,}")
        print(f"🔥 Streak         : {account.get('streak', 0)}")
        print(f"🎫 Referral Code  : {account.get('referral_code') or '-'}")

        if account.get('last_claim_date'):
            print(f"⏰ Last Claim     : {account['last_claim_date']}")

        print(f"{'='*70}\n")

    def process_single_account(self, account: Dict, delay: int = 0, show_header: bool = True):
        """Process satu akun"""
        if delay > 0:
            time.sleep(delay)

        name = self.shorten_text(account['name'], 8)
        wallet = self.shorten_text(account['wallet_address'], 12)

        if show_header:
            print(f"┌{'─'*68}┐")
            print(f"│ 🔹 {name:<8} │ 📧 {wallet:<42}     │")
            print(f"├{'─'*68}┤")

        print(f"│ ⏳ Logging in...{' '*52}│", end='\r')
        if not self.onboard_account(account, silent=True):
            print(f"│ ❌ Login gagal{' '*54}│")
            print(f"└{'─'*68}┘")
            account['status'] = 'failed'
            return

        time.sleep(1)

        print(f"│ ⏳ Getting info...{' '*50}│", end='\r')
        if not self.get_user_info(account, silent=True):
            print(f"│ ❌ Get info gagal{' '*51}│")
            print(f"└{'─'*68}┘")
            account['status'] = 'failed'
            return

        username = account.get('username') or '-'
        discord = account.get('discord') or '-'
        points = self.safe_int(account.get('points', 0))
        streak = self.safe_int(account.get('streak', 0))

        print(f"│ 👤 User: {username:<20} │ 💬 DC: {discord:<20}   │")
        print(f"│ 💰 Points: {points:<10} │ 🔥 Streak: {streak:<10}            │")

        time.sleep(1)

        if self.check_already_claimed_today(account):
            print(f"│ ✅ SUDAH CLAIM HARI INI{' '*45}│")
            print(f"└{'─'*68}┘")
            self.display_already_claimed_account(account)
            account['status'] = 'already_claimed'
            return

        print(f"│ ⏳ Claiming...{' '*54}│", end='\r')
        result = self.claim_daily_gm(account, silent=True)

        if result['success']:
            old_pts = self.safe_int(result['old_points'])
            earned = self.safe_int(result['earned'])
            new_pts = self.safe_int(result['new_points'])
            streak = self.safe_int(result['streak'])

            points_text = f"{old_pts:,} ➜ +{earned:,} ➜ {new_pts:,}"
            padding = max(0, 58 - len(points_text))

            print(f"│ 🎉 CLAIM BERHASIL!{' '*50}│")
            print(f"│ 📊 Points: {points_text}{' '*padding}│")
            print(f"│ 🔥 Streak: {streak}{' '*58}│")
            account['status'] = 'claimed'
        else:
            error = self.shorten_text(result.get('message', 'Unknown'), 50)
            print(f"│ ❌ Claim gagal: {error:<50}    │")
            account['status'] = 'failed'

        print(f"└{'─'*68}┘")

    def run_all_accounts(self, delay_between: int = 3):
        """Run semua akun sequential"""
        wib = pytz.timezone('Asia/Jakarta')
        now_wib = datetime.now(wib)

        print(f"\n{'═'*70}")
        print(f"🚀 SOMNIA AUTO CLAIM BOT")
        print(f"⏰ {now_wib.strftime('%d/%m/%Y %H:%M:%S WIB')}")
        print(f"👥 Total Accounts: {len(self.accounts)}")
        print(f"🌐 Proxy: {'Yes' if self.use_proxy else 'No'} ({len(self.proxies)} available)")
        print(f"{'═'*70}\n")

        for i, account in enumerate(self.accounts):
            if i > 0:
                time.sleep(delay_between)

            self.process_single_account(account, show_header=True)

        self.print_summary()

    def print_summary(self):
        """Tampilkan summary hasil"""
        claimed = sum(1 for acc in self.accounts if acc['status'] == 'claimed')
        already = sum(1 for acc in self.accounts if acc['status'] == 'already_claimed')
        failed = sum(1 for acc in self.accounts if acc['status'] == 'failed')

        total_points = sum(self.safe_int(acc.get('points', 0)) for acc in self.accounts)

        print(f"\n{'═'*70}")
        print(f"📊 SUMMARY")
        print(f"{'═'*70}")
        print(f"✅ Claimed Today    : {claimed} accounts")
        print(f"⏭️  Already Claimed  : {already} accounts")
        print(f"❌ Failed          : {failed} accounts")
        print(f"💰 Total Points    : {total_points:,}")
        print(f"{'═'*70}")

        print(f"\n{'No':<4} {'Account':<10} {'Username':<15} {'Discord':<15} {'Points':<12} {'Streak':<8} {'Status'}")
        print(f"{'-'*90}")
        for idx, acc in enumerate(self.accounts, 1):
            name = self.shorten_text(acc['name'], 8)
            username = self.shorten_text(acc.get('username') or '-', 13)
            discord = self.shorten_text(acc.get('discord') or '-', 13)

            status_map = {
                'claimed': '✅ Claimed',
                'already_claimed': '⏭️  Already',
                'failed': '❌ Failed',
                'ready': '⏳ Ready'
            }
            status = status_map.get(acc['status'], acc['status'])
            points = f"{acc.get('points', 0):,}"
            streak = str(acc.get('streak', 0))

            print(f"{idx:<4} {name:<10} {username:<15} {discord:<15} {points:<12} {streak:<8} {status}")

        print(f"{'-'*90}\n")

    def clear_private_keys(self):
        """Hapus private key dari memory"""
        for account in self.accounts:
            if 'private_key' in account:
                account['private_key'] = "CLEARED"

    def format_countdown(self, seconds: int) -> str:
        """Format seconds ke HH:MM:SS"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def run_with_countdown(self):
        """Run bot dengan countdown 24 jam + 1 menit"""
        wib = pytz.timezone('Asia/Jakarta')

        print(f"\n{'═'*70}")
        print(f"🤖 SOMNIA AUTO CLAIM BOT - COUNTDOWN MODE")
        print(f"{'═'*70}")
        print(f"⏰ Interval: 24 jam 1 menit setelah claim")
        print(f"👥 Total Accounts: {len(self.accounts)}")
        print(f"🌐 Proxy: {'Enabled' if self.use_proxy else 'Disabled'}")
        print(f"{'═'*70}\n")

        run_now = input("🚀 Run claim sekarang? (y/n): ").strip().lower()
        
        cycle = 1
        
        while True:
            try:
                if run_now == 'y' or self.next_claim_time is None or datetime.now(wib) >= self.next_claim_time:
                    # Waktu untuk claim
                    print(f"\n{'='*70}")
                    print(f"🔄 CYCLE #{cycle}")
                    print(f"{'='*70}")
                    
                    self.last_claim_time = datetime.now(wib)
                    self.run_all_accounts(delay_between=3)
                    
                    # Set next claim time: 24 jam 1 menit dari sekarang
                    self.next_claim_time = self.last_claim_time + timedelta(hours=24, minutes=1)
                    
                    print(f"\n{'═'*70}")
                    print(f"✅ Cycle #{cycle} selesai!")
                    print(f"⏰ Last Claim : {self.last_claim_time.strftime('%d/%m/%Y %H:%M:%S WIB')}")
                    print(f"⏰ Next Claim : {self.next_claim_time.strftime('%d/%m/%Y %H:%M:%S WIB')}")
                    print(f"{'═'*70}\n")
                    
                    cycle += 1
                    run_now = 'n'
                
                # Countdown loop
                while datetime.now(wib) < self.next_claim_time:
                    now = datetime.now(wib)
                    time_diff = (self.next_claim_time - now).total_seconds()
                    
                    if time_diff <= 0:
                        break
                    
                    countdown = self.format_countdown(int(time_diff))
                    current_time = now.strftime('%H:%M:%S WIB')
                    next_time = self.next_claim_time.strftime('%d/%m %H:%M:%S')
                    
                    print(f"⏳ Countdown: {countdown} | Current: {current_time} | Next Claim: {next_time}", end='\r')
                    time.sleep(1)
                
            except KeyboardInterrupt:
                print(f"\n\n🛑 Bot stopped by user")
                self.clear_private_keys()
                break

def create_pk_txt_template():
    """Membuat template file pk.txt"""
    template = """# Somnia Bot - Private Keys
# Format: Satu private key per baris
# Baris yang diawali dengan # akan diabaikan

0xYOUR_PRIVATE_KEY_1
0xYOUR_PRIVATE_KEY_2
0xYOUR_PRIVATE_KEY_3
"""

    with open('pk.txt', 'w') as f:
        f.write(template)

    print("✅ Template pk.txt berhasil dibuat!")
    print("💡 Edit file pk.txt dengan private key Anda")
    print("⚠️  JANGAN SHARE FILE INI!")

def create_proxy_txt_template():
    """Membuat template file proxy.txt"""
    template = """# Somnia Bot - Proxy List
# Format: http://user:pass@ip:port atau https://user:pass@ip:port
# Baris yang diawali dengan # akan diabaikan

http://username:password@proxy1.com:8080
http://username:password@proxy2.com:8080
"""

    with open('proxy.txt', 'w') as f:
        f.write(template)

    print("✅ Template proxy.txt berhasil dibuat!")
    print("💡 Edit file proxy.txt dengan proxy Anda (opsional)")

def main():
    bot = SomniaMultiAccountBot()

    print("="*70)
    print("🤖 SOMNIA MULTI-ACCOUNT AUTO CLAIM BOT")
    print("="*70)
    print("1. Run sekali (Manual)")
    print("2. Run dengan countdown (Auto 24 jam 1 menit)")
    print("3. Buat template pk.txt")
    print("4. Buat template proxy.txt")
    print("="*70)

    choice = input("Pilih opsi (1/2/3/4): ").strip()

    if choice == "3":
        create_pk_txt_template()
        return

    if choice == "4":
        create_proxy_txt_template()
        return

    print("\n📂 Loading private keys from pk.txt...")
    count = bot.load_private_keys_from_txt("pk.txt")
    if count == 0:
        print("❌ Tidak ada private key yang dimuat")
        print("💡 Gunakan opsi 3 untuk membuat template pk.txt")
        return

    print(f"✅ Loaded {count} accounts")

    print("\n📂 Loading proxies from proxy.txt...")
    proxy_count = bot.load_proxies_from_txt("proxy.txt")
    if proxy_count > 0:
        print(f"✅ Loaded {proxy_count} proxies")
        use_proxy = input("🌐 Use proxy? (y/n): ").strip().lower()
        bot.use_proxy = (use_proxy == 'y')
    else:
        print("⚠️  No proxies loaded, running without proxy")
        bot.use_proxy = False

    if choice == "1":
        bot.run_all_accounts(delay_between=3)
        bot.clear_private_keys()
    elif choice == "2":
        bot.run_with_countdown()
    else:
        print("❌ Pilihan tidak valid")
        return

    print("\n✅ Selesai!")

if __name__ == "__main__":
    try:
        from web3 import Web3
        from eth_account import Account
        from eth_account.messages import encode_defunct
        import pytz
    except ImportError:
        print("❌ Library yang diperlukan belum terinstall")
        print("📦 Install dengan: pip install web3 eth-account requests pytz")
        exit(1)

    main()
