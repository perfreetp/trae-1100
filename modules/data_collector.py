import os
import pandas as pd
from datetime import datetime
from utils.common import load_config, ensure_dir, get_file_list


class DataCollector:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.input_dir = ensure_dir(self.config['paths']['input_dir'])
        self.stat_month = None
        self.parking_data = {}

    def select_month(self, year=None, month=None):
        if year is None or month is None:
            now = datetime.now()
            year = year or now.year
            month = month or (now.month - 1 if now.month > 1 else 12)
            if month == 12 and now.month == 1:
                year = now.year - 1
        self.stat_month = datetime(year, month, 1)
        return self.stat_month

    def read_parking_file(self, file_path):
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == '.csv':
                df = pd.read_csv(file_path, encoding='utf-8-sig')
            else:
                df = pd.read_excel(file_path)
            return df
        except Exception as e:
            print(f"读取文件失败 {file_path}: {e}")
            return None

    def extract_parking_name(self, file_path):
        filename = os.path.basename(file_path)
        name = os.path.splitext(filename)[0]
        if '_' in name:
            parts = name.split('_')
            for part in parts:
                if '车场' in part or '停车场' in part:
                    return part
        return name

    def detect_parking_type(self, parking_name):
        if '直营' in parking_name:
            return '直营'
        elif '委托' in parking_name:
            return '委托'
        return '直营'

    def standardize_columns(self, df):
        column_mapping = {
            '日期': 'date', '时间': 'time', '入场时间': 'entry_time', '出场时间': 'exit_time',
            '停车时长': 'duration', '时长': 'duration', '小时': 'duration',
            '临停收入': 'temp_revenue', '临时收入': 'temp_revenue', '临停金额': 'temp_revenue',
            '月卡收入': 'monthly_revenue', '月卡续费': 'monthly_revenue', '月卡金额': 'monthly_revenue',
            '免费放行': 'free_pass', '免费车次': 'free_pass',
            '总车次': 'total_visits', '车流量': 'total_visits', '入场车次': 'total_visits',
            '会员数量': 'member_count', '会员数': 'member_count',
            '车位数量': 'total_spots', '总车位': 'total_spots',
            '负责人': 'manager', '车场负责人': 'manager'
        }
        df = df.rename(columns={col: column_mapping.get(col, col) for col in df.columns})
        
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        if 'entry_time' in df.columns:
            df['entry_time'] = pd.to_datetime(df['entry_time'])
            if 'date' not in df.columns:
                df['date'] = df['entry_time'].dt.date
                df['date'] = pd.to_datetime(df['date'])
        
        return df

    def batch_load_data(self):
        files = get_file_list(self.input_dir)
        if not files:
            print(f"在 {self.input_dir} 中未找到数据文件")
            return {}

        print(f"找到 {len(files)} 个数据文件，开始读取...")
        
        for file_path in files:
            parking_name = self.extract_parking_name(file_path)
            df = self.read_parking_file(file_path)
            if df is not None and not df.empty:
                df = self.standardize_columns(df)
                df['parking_name'] = parking_name
                df['parking_type'] = self.detect_parking_type(parking_name)
                df['source_file'] = os.path.basename(file_path)
                self.parking_data[parking_name] = df
                print(f"  ✓ {parking_name}: {len(df)} 条记录")

        return self.parking_data

    def filter_by_month(self, year=None, month=None):
        target_date = self.stat_month or self.select_month(year, month)
        filtered_data = {}
        
        for name, df in self.parking_data.items():
            if 'date' in df.columns:
                mask = (df['date'].dt.year == target_date.year) & \
                       (df['date'].dt.month == target_date.month)
                filtered_df = df[mask].copy()
                if not filtered_df.empty:
                    filtered_data[name] = filtered_df
                else:
                    print(f"  ⚠ {name}: 当月无数据")
            else:
                filtered_data[name] = df
        
        return filtered_data

    def get_collected_summary(self):
        summary = []
        for name, df in self.parking_data.items():
            summary.append({
                '车场名称': name,
                '车场类型': df['parking_type'].iloc[0] if 'parking_type' in df.columns else '未知',
                '记录数': len(df),
                '日期范围': f"{df['date'].min().strftime('%Y-%m-%d')} 至 {df['date'].max().strftime('%Y-%m-%d')}"
                if 'date' in df.columns else '未知'
            })
        return pd.DataFrame(summary)
