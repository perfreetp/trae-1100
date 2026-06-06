import pandas as pd


class RevenueAnalyzer:
    def __init__(self, config=None):
        self.config = config

    def summarize_by_parking(self, data_dict):
        print("开始收入汇总分析...")
        
        revenue_summary = []
        for parking_name, df in data_dict.items():
            temp_revenue = df['temp_revenue'].sum() if 'temp_revenue' in df.columns else 0
            monthly_revenue = df['monthly_revenue'].sum() if 'monthly_revenue' in df.columns else 0
            total_visits = df['total_visits'].sum() if 'total_visits' in df.columns else 0
            free_pass = df['free_pass'].sum() if 'free_pass' in df.columns else 0
            parking_type = df['parking_type'].iloc[0] if 'parking_type' in df.columns else '未知'
            
            revenue_summary.append({
                '车场名称': parking_name,
                '车场类型': parking_type,
                '临停收入': round(temp_revenue, 2),
                '月卡收入': round(monthly_revenue, 2),
                '总收入': round(temp_revenue + monthly_revenue, 2),
                '总车次': int(total_visits),
                '免费车次': int(free_pass),
                '免费率': round(free_pass / total_visits * 100, 2) if total_visits > 0 else 0
            })
        
        df_summary = pd.DataFrame(revenue_summary)
        if not df_summary.empty:
            df_summary = df_summary.sort_values('总收入', ascending=False).reset_index(drop=True)
        
        print(f"  ✓ 完成 {len(df_summary)} 个车场的收入汇总")
        return df_summary

    def summarize_daily(self, data_dict):
        all_data = []
        for parking_name, df in data_dict.items():
            if 'date' in df.columns:
                df_copy = df.copy()
                df_copy['车场名称'] = parking_name
                all_data.append(df_copy)
        
        if not all_data:
            return pd.DataFrame()
        
        combined = pd.concat(all_data, ignore_index=True)
        
        if 'date' not in combined.columns:
            return pd.DataFrame()
        
        daily_summary = combined.groupby('date').agg({
            'temp_revenue': 'sum',
            'monthly_revenue': 'sum',
            'total_visits': 'sum',
            'free_pass': 'sum'
        }).reset_index()
        
        daily_summary['总收入'] = daily_summary['temp_revenue'] + daily_summary['monthly_revenue']
        daily_summary.columns = ['日期', '临停收入', '月卡收入', '总车次', '免费车次', '总收入']
        
        return daily_summary

    def get_type_comparison(self, data_dict):
        df_summary = self.summarize_by_parking(data_dict)
        if df_summary.empty:
            return pd.DataFrame()
        
        type_summary = df_summary.groupby('车场类型').agg({
            '车场名称': 'count',
            '临停收入': 'sum',
            '月卡收入': 'sum',
            '总收入': 'sum',
            '总车次': 'sum',
            '免费车次': 'sum'
        }).reset_index()
        
        type_summary.columns = ['车场类型', '车场数量', '临停收入', '月卡收入', '总收入', '总车次', '免费车次']
        type_summary['平均车场收入'] = (type_summary['总收入'] / type_summary['车场数量']).round(2)
        type_summary['免费率'] = (type_summary['免费车次'] / type_summary['总车次'] * 100).round(2)
        
        return type_summary
