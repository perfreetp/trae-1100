import pandas as pd
from datetime import datetime
from utils.common import load_config, get_month_days


class RuleValidator:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.anomalies = []
        self.validation_config = self.config.get('validation', {})

    def check_missing_dates(self, data_dict, year, month):
        expected_dates = get_month_days(year, month)
        missing_report = []

        for parking_name, df in data_dict.items():
            if 'date' not in df.columns:
                continue
            
            actual_dates = set(df['date'].dt.date)
            missing_dates = [d for d in expected_dates if d.date() not in actual_dates]
            
            if missing_dates:
                missing_report.append({
                    '车场名称': parking_name,
                    '异常类型': '缺失日期',
                    '异常描述': f"缺失 {len(missing_dates)} 天数据",
                    '异常详情': ', '.join([d.strftime('%Y-%m-%d') for d in missing_dates[:5]]) + 
                               ('...' if len(missing_dates) > 5 else ''),
                    '严重程度': '高' if len(missing_dates) > 5 else '中',
                    '负责人': df['manager'].iloc[0] if 'manager' in df.columns else '待分配'
                })

        return missing_report

    def check_revenue_drop(self, data_dict):
        drop_threshold = self.validation_config.get('revenue_drop_threshold', 0.3)
        drop_report = []

        for parking_name, df in data_dict.items():
            if 'date' not in df.columns or 'temp_revenue' not in df.columns:
                continue
            
            daily_revenue = df.groupby('date')['temp_revenue'].sum().reset_index()
            daily_revenue = daily_revenue.sort_values('date')
            
            if len(daily_revenue) < 7:
                continue
            
            daily_revenue['7d_avg'] = daily_revenue['temp_revenue'].rolling(7, min_periods=3).mean()
            daily_revenue['drop_ratio'] = (daily_revenue['7d_avg'] - daily_revenue['temp_revenue']) / daily_revenue['7d_avg']
            
            drops = daily_revenue[daily_revenue['drop_ratio'] >= drop_threshold]
            
            for _, row in drops.iterrows():
                drop_pct = row['drop_ratio'] * 100
                drop_report.append({
                    '车场名称': parking_name,
                    '异常类型': '收入突降',
                    '异常日期': row['date'].strftime('%Y-%m-%d'),
                    '异常描述': f"当日收入较7日均值下降 {drop_pct:.1f}%",
                    '异常详情': f"当日收入: ¥{row['temp_revenue']:.2f}, 7日均值: ¥{row['7d_avg']:.2f}",
                    '严重程度': '高' if drop_pct >= 50 else '中',
                    '负责人': df['manager'].iloc[0] if 'manager' in df.columns else '待分配'
                })

        return drop_report

    def check_abnormal_free_pass(self, data_dict):
        free_threshold = self.validation_config.get('free_pass_threshold', 0.1)
        free_report = []

        for parking_name, df in data_dict.items():
            if 'free_pass' not in df.columns or 'total_visits' not in df.columns:
                continue
            
            total_free = df['free_pass'].sum()
            total_visits = df['total_visits'].sum()
            
            if total_visits == 0:
                continue
            
            free_ratio = total_free / total_visits
            
            if free_ratio >= free_threshold:
                free_report.append({
                    '车场名称': parking_name,
                    '异常类型': '异常免费放行',
                    '异常描述': f"免费放行率达 {free_ratio*100:.1f}%",
                    '异常详情': f"免费车次: {total_free:.0f}, 总车次: {total_visits:.0f}",
                    '严重程度': '高' if free_ratio >= 0.2 else '中',
                    '负责人': df['manager'].iloc[0] if 'manager' in df.columns else '待分配'
                })

        return free_report

    def validate_all(self, data_dict, year, month):
        print("开始数据校验...")
        
        all_anomalies = []
        
        missing = self.check_missing_dates(data_dict, year, month)
        print(f"  ✓ 缺失日期检查: 发现 {len(missing)} 项异常")
        all_anomalies.extend(missing)
        
        drops = self.check_revenue_drop(data_dict)
        print(f"  ✓ 收入突降检查: 发现 {len(drops)} 项异常")
        all_anomalies.extend(drops)
        
        free_pass = self.check_abnormal_free_pass(data_dict)
        print(f"  ✓ 免费放行检查: 发现 {len(free_pass)} 项异常")
        all_anomalies.extend(free_pass)
        
        self.anomalies = all_anomalies
        
        df_anomalies = pd.DataFrame(all_anomalies) if all_anomalies else pd.DataFrame()
        
        return df_anomalies

    def get_anomaly_summary(self):
        if not self.anomalies:
            return pd.DataFrame()
        
        df = pd.DataFrame(self.anomalies)
        summary = df.groupby(['异常类型', '严重程度']).size().reset_index(name='数量')
        return summary
