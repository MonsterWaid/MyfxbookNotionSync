import requests
import json
import schedule
import time
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

from notion import *
from config import myfxbook_account_id, myfxbook_email, myfxbook_password, filter_old_data



def get_last_weekend():
    """Get the date of last weekend (Sunday)"""
    today = datetime.now()
    last_sunday = today - timedelta(days=today.weekday() + 1)  # Sunday is considered the last day of the week
    return last_sunday.replace(hour=23, minute=59, second=59, microsecond=0)


# Myfxbook API Class
class Myfxbook:
    base_url = 'https://www.myfxbook.com/api/'
    session = None

    def __init__(self, email, password):
        self.email = email
        self.password = password

    def login(self):
        login = requests.get(self.base_url + 'login.json', params={'email': self.email, 'password': self.password}).json()
        if login['error'] != True:
            self.session = login['session']
            print("Login successful, session ID:", self.session)
        else:
            print("Login failed:", login['message'])
        return login

    def logout(self):
        if self.session is not None:
            logout = requests.get(self.base_url + 'logout.json', params={'session': self.session}).json()
            self.session = None
            print("Logged out")
            return logout
        else:
            print("No active session to logout.")
            return None

    def get_my_accounts(self):
        if self.session is not None:
            return requests.get(self.base_url + 'get-my-accounts.json', params={'session': self.session}).json()
        else:
            print("No active session. Please login first.")
            return None

    def get_open_trades(self, id):
        if self.session is not None:
            return requests.get(self.base_url + 'get-open-trades.json', params={'session': self.session, 'id': id}).json()
        else:
            print("No active session. Please login first.")
            return None
    
    def get_history(self, id):
        """Get historical trade records"""
        return requests.get(self.base_url + 'get-history.json', params={'session': self.session, 'id': id}).json()



# Job to fetch trades from Myfxbook and update Notion
def job(myfxbook_client):
    # Login to Myfxbook
    myfxbook_client.login()

    # Get existing trades from Notion
    existing_trades = get_existing_trades_from_notion()

    # Get Myfxbook accounts and fetch open trades
    accounts = myfxbook_client.get_my_accounts()
    if accounts is None or accounts.get('error') == True:
        print("Failed to fetch accounts.")
        myfxbook_client.logout()
        return
    
    for account in accounts['accounts']:
        
        account_id = account['accountId']
        _id = account['id']
        if account_id != myfxbook_account_id:
            continue

        # Fetch the balance of the account
        balance = account['balance']  # Get the balance field




        # handle open trades
        open_trades = myfxbook_client.get_open_trades(_id)
        if open_trades and not open_trades.get('error'):
            for trade in open_trades['openTrades']:
                # Insert or update open trades
                upsert_trade_to_notion(existing_trades, trade, balance, 'open')



        # Get historical trade data
        history_trades = myfxbook_client.get_history(_id)
        
        if history_trades.get('error') != True:
            # If filtering out trades before last weekend is needed
            if filter_old_data:
                last_sunday = get_last_weekend()
                history_trades['history'] = [
                    trade for trade in history_trades['history']
                    if datetime.strptime(trade['closeTime'], "%m/%d/%Y %H:%M") >= last_sunday
                ]
            
            for trade in history_trades['history']:
                # Pass balance when upserting the trade
                upsert_trade_to_notion(existing_trades, trade, balance, 'history')
        else:
            print(f"Failed to fetch history trades for account {_id}: {history_trades['message']}")

    myfxbook_client.logout()

# Schedule the job to run every 10 seconds
myfxbook_client = Myfxbook(myfxbook_email, myfxbook_password)
schedule.every(30).seconds.do(job, myfxbook_client)

# Main loop to keep the script running
while True:
    schedule.run_pending()
    time.sleep(10)

