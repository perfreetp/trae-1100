import pandas as pd
from datetime import datetime, time


class ParkingUtilization:
    def __init__(self, config=None):
        self.config = config
        self.peak_hours = config.get('analysis', {}).get('peak_hours', {}) if config else {}
        self.data_issues = []

    def analyze_duration(self, data_dict):
        print("开始车位利用分析...")
        self.data_issues = []
        
        duration_summary = []
        for parking_name, df in data_dict.items():
            total_spots = df['total_spots'].iloc[0] if 'total_spots' in df.columns else None
            parking_type = df['parking_type'].iloc[0] if 'parking_type' in df.columns else '未知'
            
            if total_spots is None:
                self.data_issues.append({
                    '车场名称': parking_name,
                    '问题类型': '缺少字段',
                    '问题描述': '缺少"车位数量"字段，无法计算车位利用率',
                    '严重程度': '中'
                })
                total_spots = 0
            
            has_duration = 'duration' in df.columns
            has_visits = 'total_visits' in df.columns
            has_date = 'date' in df.columns
            
            if not has_duration:
                self.data_issues.append({
                    '车场名称': parking_name,
                    '问题类型': '缺少字段',
                    '问题描述': '缺少"停车时长"字段，无法计算停车时长指标',
                    '严重程度': '高'
                })
            
            if not has_visits:
                self.data_issues.append({
                    '车场名称': parking_name,
                    '问题类型': '缺少字段',
                    '问题描述': '缺少"总车次"字段，无法准确计算总停车时长',
                    '严重程度': '中'
                })
            
            total_duration = 0
            avg_duration = 0
            total_visits = 0
            unique_days = len(df['date'].unique()) if has_date else len(df)
            
            if has_duration and has_visits and has_date:
                daily_duration = []
                daily_visits = []
                for date, group in df.groupby('date'):
                    day_avg_duration = group['duration'].mean() if len(group) > 0 else 0
                    day_visits = group['total_visits'].sum()
                    day_total_duration = day_avg_duration * day_visits
                    daily_duration.append(day_total_duration)
                    daily_visits.append(day_visits)
                
                total_duration = sum(daily_duration)
                total_visits = sum(daily_visits)
                avg_duration = total_duration / total_visits if total_visits > 0 else 0
            elif has_duration:
                total_duration = df['duration'].sum()
                total_visits = len(df)
                avg_duration = df['duration'].mean() if len(df) > 0 else 0
            
            utilization_rate = 0
            if total_spots > 0 and unique_days > 0:
                utilization_rate = (total_duration / (total_spots * 24 * unique_days)) * 100
                utilization_rate = min(utilization_rate, 100)
            
            duration_summary.append({
                '车场名称': parking_name,
                '车场类型': parking_type,
                '总车位': int(total_spots) if total_spots else 0,
                '总车次': int(total_visits),
                '平均停车时长(小时)': round(avg_duration, 2),
                '总停车时长(小时)': round(total_duration, 2),
                '统计天数': unique_days,
                '车位利用率(%)': round(utilization_rate, 2)
            })
        
        df_summary = pd.DataFrame(duration_summary)
        if not df_summary.empty:
            df_summary = df_summary.sort_values('车位利用率(%)', ascending=False).reset_index(drop=True)
        
        print(f"  ✓ 完成 {len(df_summary)} 个车场的车位利用分析")
        return df_summary

    def _is_in_peak_period(self, entry_time, exit_time, peak_start, peak_end):
        if pd.isna(entry_time) or pd.isna(exit_time):
            return False
        
        peak_start_time = time(int(peak_start.split(':')[0]), int(peak_start.split(':')[1]))
        peak_end_time = time(int(peak_end.split(':')[0]), int(peak_end.split(':')[1]))
        
        entry_date = entry_time.date()
        peak_start_dt = datetime.combine(entry_date, peak_start_time)
        peak_end_dt = datetime.combine(entry_date, peak_end_time)
        
        if entry_time > peak_end_dt:
            return False
        if exit_time < peak_start_dt:
            return False
        
        return True

    def _count_peak_occupancy(self, df, peak_start, peak_end):
        count = 0
        for _, row in df.iterrows():
            entry = row.get('entry_time')
            exit_t = row.get('exit_time')
            if self._is_in_peak_period(entry, exit_t, peak_start, peak_end):
                count += 1
        return count

    def analyze_peak_occupancy(self, data_dict):
        peak_summary = []
        peak_issues = []
        
        morning_start, morning_end = self.peak_hours.get('morning', ['07:00', '09:00'])
        evening_start, evening_end = self.peak_hours.get('evening', ['17:00', '19:00'])
        
        for parking_name, df in data_dict.items():
            total_spots = df['total_spots'].iloc[0] if 'total_spots' in df.columns else 100
            parking_type = df['parking_type'].iloc[0] if 'parking_type' in df.columns else '未知'
            
            has_entry = 'entry_time' in df.columns and df['entry_time'].notna().any()
            has_exit = 'exit_time' in df.columns and df['exit_time'].notna().any()
            
            if has_entry and has_exit:
                morning_count = 0
                evening_count = 0
                
                for date, day_df in df.groupby(df['entry_time'].dt.date):
                    morning_count += self._count_peak_occupancy(day_df, morning_start, morning_end)
                    evening_count += self._count_peak_occupancy(day_df, evening_start, evening_end)
                
                unique_days = len(df['entry_time'].dt.date.unique())
                avg_morning = morning_count / unique_days if unique_days > 0 else 0
                avg_evening = evening_count / unique_days if unique_days > 0 else 0
                
                morning_occupancy = (avg_morning / total_spots) * 100 if total_spots > 0 else 0
                evening_occupancy = (avg_evening / total_spots) * 100 if total_spots > 0 else 0
                data_status = '正常'
            else:
                missing_fields = []
                if not has_entry:
                    missing_fields.append('入场时间(entry_time)')
                if not has_exit:
                    missing_fields.append('出场时间(exit_time)')
                
                peak_issues.append({
                    '车场名称': parking_name,
                    '问题类型': '缺少字段',
                    '问题描述': f"缺少{', '.join(missing_fields)}，无法计算高峰占用率",
                    '严重程度': '中'
                })
                
                morning_occupancy = None
                evening_occupancy = None
                data_status = '数据不足'
            
            peak_summary.append({
                '车场名称': parking_name,
                '车场类型': parking_type,
                '数据状态': data_status,
                '早高峰占用率(%)': round(morning_occupancy, 2) if morning_occupancy is not None else '数据不足',
                '晚高峰占用率(%)': round(evening_occupancy, 2) if evening_occupancy is not None else '数据不足',
                '平均高峰占用率(%)': round((morning_occupancy + evening_occupancy) / 2, 2) 
                                     if (morning_occupancy is not None and evening_occupancy is not None) 
                                     else '数据不足'
            })
        
        self.data_issues.extend(peak_issues)
        return pd.DataFrame(peak_summary)

    def get_data_issues(self):
        return pd.DataFrame(self.data_issues) if self.data_issues else pd.DataFrame()

    def get_combined_analysis(self, data_dict):
        duration_df = self.analyze_duration(data_dict)
        peak_df = self.analyze_peak_occupancy(data_dict)
        
        if duration_df.empty or peak_df.empty:
            return pd.DataFrame()
        
        combined = pd.merge(duration_df, peak_df, on=['车场名称', '车场类型'], how='left')
        return combined
