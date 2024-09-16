from datetime import datetime
from zoneinfo import ZoneInfo
import json
import requests

from config import notion_api_token, notion_db_id


notion_headers = {
    'Authorization': f'Bearer ' + notion_api_token,
    'Content-Type': 'application/json',
    'Notion-Version': '2022-06-28'
}


def convert_to_utc(open_time_str):
    try:
        # Assume the input time string is in GMT+2 or GMT+3 format (e.g., "09/13/2024 23:50")
        platform_time = datetime.strptime(open_time_str, "%m/%d/%Y %H:%M")
        
        # Assume platform time is GMT+2 (can be adjusted to the actual time zone if needed)
        platform_time = platform_time.replace(tzinfo=ZoneInfo("Etc/GMT-3"))
        
        # Convert to UTC time
        utc_time = platform_time.astimezone(ZoneInfo("UTC"))
        
        # Return UTC time in ISO 8601 format
        return utc_time.strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError as e:
        print(f"Error parsing open time: {e}")
        return None  # Return None if parsing fails


# Query Notion for existing trades
def get_existing_trades_from_notion():
    notion_query_url = f'https://api.notion.com/v1/databases/{notion_db_id}/query'
    response = requests.post(notion_query_url, headers=notion_headers)
   
    if response.status_code == 200:
        results = response.json()['results']
        existing_trades = {}

        for result in results:
            try:
                open_time = result['properties']['Open Time']['date']['start']
                trade_status = result['properties']['Trade Type']['rich_text'][0]['text']['content']
                page_id = result['id']  # Get the page ID
                existing_trades[open_time] = {'status': trade_status, 'page_id': page_id}
            except (KeyError, IndexError) as e:
                # Handle missing or malformed trade ID or trade type
                print(f"Error parsing trade from Notion: {e}")

        return existing_trades
    else:
        print(f"Failed to query Notion DB: {response.status_code}, {response.text}")
        return {}


def upsert_trade_to_notion(existing_trades, trade, balance, trade_type='open'):
    notion_url = 'https://api.notion.com/v1/pages'
    
    # Convert openTime and closeTime to UTC time (ISO 8601 format)
    open_time_str = trade.get('openTime')  # Get openTime
    open_time = convert_to_utc(open_time_str)  # Convert to UTC

    close_time_str = trade.get('closeTime')  # Get closeTime
    close_time = convert_to_utc(close_time_str) if close_time_str else None  # Convert if closeTime exists

    # Get the action field
    action = trade.get('action', 'No Action')  # Assume action field is 'action'
    if action not in ['Buy', 'Sell']: return

    # Get tp, sl, pips, interest, commission
    tp = trade.get('tp', None)  # Take Profit
    sl = trade.get('sl', None)  # Stop Loss
    pips = trade.get('pips', None)  # Pips
    interest = trade.get('interest', None)  # Interest
    commission = trade.get('commission', None)  # Commission
    comment = trade.get('comment', None)  # Comment

    # Get sizing_type and sizing_value
    sizing_type = trade.get('sizing', {}).get('type', None)
    sizing_value = trade.get('sizing', {}).get('value', None)

    # Dynamically build the notion_data dictionary
    notion_data = {
        'properties': {
            'Trade Type': {'rich_text': [{'text': {'content': trade_type}}]},
            'Open Time': {'date': {'start': open_time}},  # Include Open Time
            'Action': {'select': {'name': action}},  # Set as single-select type
            'Balance': {'number': balance}
        }
    }

    # Dynamically add fields that are not zero
    if trade.get('symbol'):
        notion_data['properties']['Symbol'] = {'rich_text': [{'text': {'content': trade['symbol']}}]}
    
    if trade.get('openPrice', 0) != 0:
        notion_data['properties']['Open Price'] = {'number': trade['openPrice']}
    
    if trade.get('closePrice', 0) != 0:
        notion_data['properties']['Close Price'] = {'number': trade.get('closePrice', 0)}

    if trade.get('profit', 0) != 0:
        notion_data['properties']['Profit'] = {'number': trade['profit']}
    
    if close_time:
        notion_data['properties']['Close Time'] = {'date': {'start': close_time}}  # Include Close Time

    if sizing_type:
        notion_data['properties']['Sizing Type'] = {'rich_text': [{'text': {'content': sizing_type}}]}
    
    if sizing_value and float(sizing_value) != 0:
        notion_data['properties']['Sizing Value'] = {'number': float(sizing_value)}
    
    if tp and tp != 0:
        notion_data['properties']['TP'] = {'number': tp}

    if sl and sl != 0:
        notion_data['properties']['SL'] = {'number': sl}

    if pips and pips != 0:
        notion_data['properties']['Pips'] = {'number': pips}

    if interest and float(interest) != 0:
        notion_data['properties']['Interest'] = {'number': float(interest)}

    if commission and float(commission) != 0:
        notion_data['properties']['Commission'] = {'number': float(commission)}

    if comment:
        notion_data['properties']['Myfxbook Comment'] = {'rich_text': [{'text': {'content': comment}}]}

    # If updating an existing trade
    existing_open_times_short = {ot.split('.')[0]: ot for ot in existing_trades.keys()}  # Create a mapping, shortened time as key, original time as value


    if open_time in existing_open_times_short:
        full_open_time = existing_open_times_short[open_time]  # Get full open_time
        page_id = existing_trades[full_open_time]['page_id']  # Use full open_time to get page_id
        notion_url = f'https://api.notion.com/v1/pages/{page_id}'
        response = requests.patch(notion_url, headers=notion_headers, data=json.dumps(notion_data))

    # If it's a new trade
    else:
        notion_data['parent'] = {'database_id': notion_db_id}
        response = requests.post(notion_url, headers=notion_headers, data=json.dumps(notion_data))

    # Print result
    if response.status_code == 200:
        print(f'Successfully processed {trade.get("symbol", "Unknown")} trade in Notion.')
    else:
        print(f'Failed to process trade: {response.status_code}, {response.text}')

