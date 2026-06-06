import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from utils.common import load_config, ensure_dir, format_currency

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False


class ReportGenerator:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.output_dir = ensure_dir(self.config['paths']['output_dir'])
        self.history_dir = ensure_dir(self.config['paths']['history_dir'])
        self.report_config = self.config.get('report', {})

    def generate_charts(self, data_dict, revenue_summary, stat_month, output_dir):
        print("  生成图表...")
        chart_dir = ensure_dir(os.path.join(output_dir, 'charts'))
        charts = []

        if not revenue_summary.empty:
            fig, ax = plt.subplots(figsize=(12, 6))
            revenue_sorted = revenue_summary.sort_values('总收入', ascending=True)
            bars = ax.barh(revenue_sorted['车场名称'], revenue_sorted['总收入'], color='#3498db')
            ax.set_xlabel('总收入 (元)')
            ax.set_title(f'{stat_month.strftime("%Y年%m月")} 各车场收入排行')
            for i, bar in enumerate(bars):
                width = bar.get_width()
                ax.text(width + 50, bar.get_y() + bar.get_height()/2, 
                       f'{width:,.0f}', va='center')
            plt.tight_layout()
            chart_path = os.path.join(chart_dir, 'revenue_ranking.png')
            plt.savefig(chart_path, dpi=150, bbox_inches='tight')
            plt.close()
            charts.append(chart_path)

            fig, ax = plt.subplots(figsize=(10, 6))
            type_summary = revenue_summary.groupby('车场类型')['总收入'].sum()
            colors = ['#e74c3c', '#3498db']
            wedges, texts, autotexts = ax.pie(
                type_summary.values, labels=type_summary.index,
                autopct='%1.1f%%', colors=colors, startangle=90
            )
            ax.set_title(f'{stat_month.strftime("%Y年%m月")} 直营 vs 委托 收入占比')
            plt.tight_layout()
            chart_path = os.path.join(chart_dir, 'type_comparison.png')
            plt.savefig(chart_path, dpi=150, bbox_inches='tight')
            plt.close()
            charts.append(chart_path)

        daily_data = []
        for name, df in data_dict.items():
            if 'date' in df.columns and 'temp_revenue' in df.columns:
                daily = df.groupby('date')['temp_revenue'].sum().reset_index()
                daily['车场名称'] = name
                daily_data.append(daily)
        
        if daily_data:
            combined = pd.concat(daily_data, ignore_index=True)
            daily_total = combined.groupby('date')['temp_revenue'].sum().reset_index()
            
            fig, ax = plt.subplots(figsize=(14, 6))
            ax.plot(daily_total['date'], daily_total['temp_revenue'], 
                   marker='o', linewidth=2, color='#2ecc71')
            ax.set_xlabel('日期')
            ax.set_ylabel('临停收入 (元)')
            ax.set_title(f'{stat_month.strftime("%Y年%m月")} 临停收入趋势')
            ax.grid(True, alpha=0.3)
            plt.xticks(rotation=45)
            plt.tight_layout()
            chart_path = os.path.join(chart_dir, 'daily_trend.png')
            plt.savefig(chart_path, dpi=150, bbox_inches='tight')
            plt.close()
            charts.append(chart_path)

        if not revenue_summary.empty and '免费率' in revenue_summary.columns:
            fig, ax = plt.subplots(figsize=(12, 6))
            free_sorted = revenue_summary.sort_values('免费率', ascending=False)
            bars = ax.bar(free_sorted['车场名称'], free_sorted['免费率'], color='#f39c12')
            ax.set_ylabel('免费率 (%)')
            ax.set_title(f'{stat_month.strftime("%Y年%m月")} 各车场免费率对比')
            ax.axhline(y=10, color='red', linestyle='--', label='警戒线(10%)')
            plt.xticks(rotation=45)
            plt.legend()
            plt.tight_layout()
            chart_path = os.path.join(chart_dir, 'free_rate.png')
            plt.savefig(chart_path, dpi=150, bbox_inches='tight')
            plt.close()
            charts.append(chart_path)

        print(f"  ✓ 生成 {len(charts)} 张图表")
        return charts

    def _get_empty_anomaly_df(self):
        return pd.DataFrame(columns=[
            '车场名称', '异常类型', '异常描述', '异常详情', 
            '严重程度', '负责人', '异常日期'
        ])
    
    def _get_empty_todo_df(self):
        return pd.DataFrame(columns=[
            '车场名称', '异常类型', '异常描述', '异常详情',
            '严重程度', '负责人', '异常日期', '处理状态',
            '优先级', '截止日期'
        ])
    
    def _get_empty_manager_todo_df(self):
        return pd.DataFrame(columns=[
            '负责人', '待处理问题类型', '涉及车场', '严重程度', '问题数量'
        ])
    
    def _get_empty_notification_review_df(self):
        return pd.DataFrame(columns=[
            '批次ID', '统计月份', '负责人', '应发问题数', '实际发送数',
            '是否未发送问题', '发送状态', '发送范围', '失败原因', '发送时间'
        ])
    
    def _get_empty_preview_record_df(self):
        return pd.DataFrame(columns=[
            '批次ID', '生成时间', '发送模式', '负责人', '问题数量',
            '消息主题', '消息内容', '统计月份'
        ])
    
    def _normalize_manager(self, manager):
        if pd.isna(manager) or str(manager).strip() == '' or manager == 'nan':
            return '待分配'
        return str(manager).strip()
    
    def generate_issue_list(self, anomalies_df):
        if anomalies_df is None or anomalies_df.empty:
            return self._get_empty_todo_df(), self._get_empty_manager_todo_df()
        
        todo_list = anomalies_df.copy()
        todo_list['负责人'] = todo_list['负责人'].apply(self._normalize_manager)
        todo_list['处理状态'] = '待处理'
        todo_list['优先级'] = todo_list['严重程度'].map({'高': 'P0', '中': 'P1', '低': 'P2'})
        todo_list['截止日期'] = (datetime.now() + pd.Timedelta(days=3)).strftime('%Y-%m-%d')
        
        manager_todos = todo_list.groupby('负责人').agg({
            '异常类型': ['count', lambda x: ', '.join(x.unique())],
            '车场名称': lambda x: ', '.join(x.unique()),
            '严重程度': lambda x: ', '.join(x.unique())
        }).reset_index()
        manager_todos.columns = ['负责人', '问题数量', '待处理问题类型', '涉及车场', '严重程度']
        manager_todos = manager_todos[['负责人', '待处理问题类型', '涉及车场', '严重程度', '问题数量']]
        
        return todo_list, manager_todos

    def save_to_excel(self, output_path, results, stat_month):
        print("  生成Excel报告...")
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            overview_data = {
                '项目': ['统计月份', '车场总数', '直营车场', '委托车场', 
                        '总收入', '临停收入', '月卡收入', '总车次', '异常数量'],
                '数值': [
                    stat_month.strftime('%Y年%m月'),
                    results.get('parking_count', 0),
                    results.get('direct_count', 0),
                    results.get('entrusted_count', 0),
                    format_currency(results.get('total_revenue', 0)),
                    format_currency(results.get('temp_revenue', 0)),
                    format_currency(results.get('monthly_revenue', 0)),
                    f"{results.get('total_visits', 0):,}",
                    results.get('anomaly_count', 0)
                ]
            }
            pd.DataFrame(overview_data).to_excel(writer, sheet_name='概览', index=False)
            
            if 'revenue_summary' in results:
                results['revenue_summary'].to_excel(writer, sheet_name='收入汇总', index=False)
            
            if 'ranking' in results:
                results['ranking'].to_excel(writer, sheet_name='车场排名', index=False)
            
            if 'type_comparison' in results:
                results['type_comparison'].to_excel(writer, sheet_name='直营vs委托', index=False)
            
            if 'utilization' in results:
                results['utilization'].to_excel(writer, sheet_name='车位利用', index=False)
            
            if 'member_summary' in results:
                results['member_summary'].to_excel(writer, sheet_name='会员分析', index=False)
            
            anomalies = results.get('anomalies', self._get_empty_anomaly_df())
            anomalies.to_excel(writer, sheet_name='异常清单', index=False)
            
            todo_list = results.get('todo_list', self._get_empty_todo_df())
            todo_list.to_excel(writer, sheet_name='待办事项', index=False)
            
            manager_todos = results.get('manager_todos', self._get_empty_manager_todo_df())
            manager_todos.to_excel(writer, sheet_name='负责人待办', index=False)
            
            review_df = results.get('notification_review', self._get_empty_notification_review_df())
            review_df.to_excel(writer, sheet_name='通知复盘', index=False)
            
            if 'send_records' in results and not results['send_records'].empty:
                results['send_records'].to_excel(writer, sheet_name='发送记录', index=False)
            
            if 'preview_records' in results and not results['preview_records'].empty:
                results['preview_records'].to_excel(writer, sheet_name='消息预览', index=False)

    def save_history_version(self, output_path, stat_month):
        version_dir = ensure_dir(os.path.join(
            self.history_dir, 
            stat_month.strftime('%Y-%m')
        ))
        version_name = f"运营报告_{stat_month.strftime('%Y%m%d_%H%M%S')}.xlsx"
        version_path = os.path.join(version_dir, version_name)
        
        import shutil
        shutil.copy2(output_path, version_path)
        
        keep_versions = self.report_config.get('keep_versions', 12)
        versions = sorted([f for f in os.listdir(version_dir) if f.endswith('.xlsx')], reverse=True)
        for old_version in versions[keep_versions:]:
            os.remove(os.path.join(version_dir, old_version))
        
        return version_path

    def generate_report(self, data_dict, results, stat_month):
        print("开始生成报告...")
        
        report_dir = ensure_dir(os.path.join(
            self.output_dir,
            stat_month.strftime('%Y-%m')
        ))
        
        report_name = f"智慧停车运营报告_{stat_month.strftime('%Y%m')}.xlsx"
        output_path = os.path.join(report_dir, report_name)
        
        revenue_summary = results.get('revenue_summary', pd.DataFrame())
        
        if self.report_config.get('generate_charts', True):
            charts = self.generate_charts(data_dict, revenue_summary, stat_month, report_dir)
            results['charts'] = charts
        
        anomalies = results.get('anomalies', pd.DataFrame())
        todo_list, manager_todos = self.generate_issue_list(anomalies)
        results['todo_list'] = todo_list
        results['manager_todos'] = manager_todos
        
        if self.report_config.get('generate_excel', True):
            self.save_to_excel(output_path, results, stat_month)
            print(f"  ✓ Excel报告已保存: {output_path}")
        
        version_path = self.save_history_version(output_path, stat_month)
        print(f"  ✓ 历史版本已保存: {version_path}")
        
        return output_path, version_path
