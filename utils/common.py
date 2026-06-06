import os
import yaml
from datetime import datetime
import pandas as pd


def load_config(config_path=None):
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path


def get_month_days(year, month):
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    last_day = (next_month - pd.Timedelta(days=1)).day
    return [datetime(year, month, day) for day in range(1, last_day + 1)]


def format_number(num, decimals=2):
    if isinstance(num, (int, float)):
        return f"{num:,.{decimals}f}"
    return str(num)


def format_currency(amount):
    return f"¥{format_number(amount)}"


def get_file_list(directory, extensions=None):
    if extensions is None:
        extensions = ['.xlsx', '.xls', '.csv']
    files = []
    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext in extensions:
                files.append(os.path.join(root, filename))
    return files
