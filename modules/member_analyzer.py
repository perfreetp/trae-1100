import pandas as pd


class MemberAnalyzer:
    def __init__(self, config=None):
        self.config = config

    def analyze_members(self, data_dict):
        print("开始会员分析...")
        
        member_summary = []
        for parking_name, df in data_dict.items():
            parking_type = df['parking_type'].iloc[0] if 'parking_type' in df.columns else '未知'
            member_count = df['member_count'].iloc[-1] if 'member_count' in df.columns else 0
            monthly_revenue = df['monthly_revenue'].sum() if 'monthly_revenue' in df.columns else 0
            total_revenue = (df['temp_revenue'].sum() if 'temp_revenue' in df.columns else 0) + monthly_revenue
            total_visits = df['total_visits'].sum() if 'total_visits' in df.columns else len(df)
            total_spots = df['total_spots'].iloc[0] if 'total_spots' in df.columns else 100
            
            member_ratio = (member_count / total_spots * 100) if total_spots > 0 else 0
            monthly_revenue_ratio = (monthly_revenue / total_revenue * 100) if total_revenue > 0 else 0
            
            member_summary.append({
                '车场名称': parking_name,
                '车场类型': parking_type,
                '会员数量': int(member_count),
                '总车位': int(total_spots),
                '会员覆盖率(%)': round(member_ratio, 2),
                '月卡收入': round(monthly_revenue, 2),
                '月卡收入占比(%)': round(monthly_revenue_ratio, 2),
                '平均会员收入': round(monthly_revenue / member_count, 2) if member_count > 0 else 0
            })
        
        df_summary = pd.DataFrame(member_summary)
        if not df_summary.empty:
            df_summary = df_summary.sort_values('会员覆盖率(%)', ascending=False).reset_index(drop=True)
        
        print(f"  ✓ 完成 {len(df_summary)} 个车场的会员分析")
        return df_summary

    def compare_parking_types(self, data_dict, revenue_summary=None):
        if revenue_summary is None:
            from modules.revenue_analyzer import RevenueAnalyzer
            revenue_analyzer = RevenueAnalyzer(self.config)
            revenue_summary = revenue_analyzer.summarize_by_parking(data_dict)
        
        member_summary = self.analyze_members(data_dict)
        
        if revenue_summary.empty or member_summary.empty:
            return pd.DataFrame()
        
        member_cols = ['车场名称', '车场类型', '会员数量', '总车位', '会员覆盖率(%)']
        combined = pd.merge(
            revenue_summary, 
            member_summary[member_cols], 
            on=['车场名称', '车场类型'], 
            how='left'
        )
        
        type_comparison = combined.groupby('车场类型').agg({
            '车场名称': 'count',
            '总收入': 'sum',
            '临停收入': 'sum',
            '月卡收入': 'sum',
            '总车次': 'sum',
            '会员数量': 'sum',
            '总车位': 'sum'
        }).reset_index()
        
        type_comparison.columns = [
            '车场类型', '车场数量', '总收入', '临停收入', '月卡收入',
            '总车次', '会员总数', '总车位数'
        ]
        
        type_comparison['平均单场收入'] = (type_comparison['总收入'] / type_comparison['车场数量']).round(2)
        type_comparison['会员覆盖率(%)'] = (type_comparison['会员总数'] / type_comparison['总车位数'] * 100).round(2)
        type_comparison['月卡收入占比(%)'] = (type_comparison['月卡收入'] / type_comparison['总收入'] * 100).round(2)
        
        return type_comparison

    def generate_ranking(self, data_dict, revenue_summary=None):
        if revenue_summary is None:
            from modules.revenue_analyzer import RevenueAnalyzer
            revenue_analyzer = RevenueAnalyzer(self.config)
            revenue_summary = revenue_analyzer.summarize_by_parking(data_dict)
        
        if revenue_summary.empty:
            return pd.DataFrame()
        
        ranking = revenue_summary.copy()
        ranking['收入排名'] = ranking['总收入'].rank(ascending=False, method='min').astype(int)
        ranking = ranking.sort_values('收入排名').reset_index(drop=True)
        
        ranking['收入等级'] = pd.cut(
            ranking['总收入'],
            bins=[-float('inf'), 50000, 100000, float('inf')],
            labels=['C级(<5万)', 'B级(5-10万)', 'A级(>10万)']
        )
        
        return ranking
