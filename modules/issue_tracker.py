import os
import pandas as pd
from datetime import datetime
from utils.common import load_config, ensure_dir, get_file_list


class IssueTracker:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.tracking_dir = ensure_dir(os.path.join(
            self.config['paths']['history_dir'],
            'issue_tracking'
        ))
        self.feedback_dir = ensure_dir('./data/feedback')
        self.all_issues_path = os.path.join(self.tracking_dir, '所有问题台账.csv')
        self._load_all_issues()

    def _load_all_issues(self):
        if os.path.exists(self.all_issues_path):
            self.all_issues = pd.read_csv(self.all_issues_path, encoding='utf-8-sig')
            self.all_issues['问题ID'] = self.all_issues['问题ID'].astype(str)
        else:
            self.all_issues = pd.DataFrame(columns=[
                '问题ID', '首次发现月份', '最近出现月份', '重复出现次数',
                '车场名称', '异常类型', '异常描述', '负责人',
                '当前状态', '处理人', '处理时间', '备注'
            ])

    def _generate_issue_id(self, row):
        import hashlib
        key_parts = [
            str(row.get('车场名称', '')),
            str(row.get('异常类型', '')),
            str(row.get('异常描述', '')[:50])
        ]
        key = '|'.join(key_parts)
        return hashlib.md5(key.encode('utf-8')).hexdigest()[:8].upper()

    def load_feedback_file(self, feedback_path=None, current_anomalies=None):
        if feedback_path is None:
            files = get_file_list(self.feedback_dir, ['.xlsx', '.xls', '.csv'])
            if not files:
                return pd.DataFrame(), pd.DataFrame()
            feedback_path = files[0]
        
        print(f"  读取处理反馈文件: {os.path.basename(feedback_path)}")
        
        ext = os.path.splitext(feedback_path)[1].lower()
        try:
            if ext == '.csv':
                feedback_df = pd.read_csv(feedback_path, encoding='utf-8-sig')
            else:
                feedback_df = pd.read_excel(feedback_path)
        except Exception as e:
            print(f"  ⚠ 读取反馈文件失败: {e}")
            return pd.DataFrame(), pd.DataFrame()
        
        return self._process_feedback(feedback_df, current_anomalies)

    def _process_feedback(self, feedback_df, current_anomalies=None):
        if feedback_df is None or feedback_df.empty:
            return pd.DataFrame(), pd.DataFrame()
        
        required_cols = ['问题ID', '处理状态']
        missing_cols = [col for col in required_cols if col not in feedback_df.columns]
        if missing_cols:
            print(f"  ⚠ 反馈文件缺少必要列: {', '.join(missing_cols)}")
            return pd.DataFrame(), feedback_df
        
        feedback_df['问题ID'] = feedback_df['问题ID'].astype(str)
        
        all_valid_ids = set(self.all_issues['问题ID'].values)
        if current_anomalies is not None and not current_anomalies.empty:
            if '问题ID' in current_anomalies.columns:
                current_ids = set(current_anomalies['问题ID'].astype(str).values)
                all_valid_ids.update(current_ids)
        
        matched = []
        unmatched = []
        
        for _, row in feedback_df.iterrows():
            issue_id = str(row['问题ID'])
            if issue_id in all_valid_ids:
                matched.append(row)
            else:
                unmatched.append(row)
        
        matched_df = pd.DataFrame(matched) if matched else pd.DataFrame()
        unmatched_df = pd.DataFrame(unmatched) if unmatched else pd.DataFrame()
        
        if not unmatched_df.empty:
            print(f"  ⚠ 发现 {len(unmatched_df)} 条反馈无法匹配到已有问题")
        
        return matched_df, unmatched_df

    def merge_feedback_to_current(self, current_anomalies, matched_feedback):
        if current_anomalies is None or current_anomalies.empty:
            return current_anomalies
        
        result = current_anomalies.copy()
        
        if '问题ID' not in result.columns:
            result['问题ID'] = result.apply(self._generate_issue_id, axis=1)
        
        if matched_feedback is None or matched_feedback.empty:
            return result
        
        feedback_dict = {}
        for _, row in matched_feedback.iterrows():
            feedback_dict[str(row['问题ID'])] = {
                '处理状态': row.get('处理状态', '待处理'),
                '处理人': row.get('处理人', ''),
                '处理时间': row.get('处理时间', ''),
                '备注': row.get('备注', '')
            }
        
        for idx, row in result.iterrows():
            issue_id = str(row['问题ID'])
            if issue_id in feedback_dict:
                fb = feedback_dict[issue_id]
                result.at[idx, '处理状态'] = fb['处理状态']
                result.at[idx, '处理人'] = fb['处理人']
                result.at[idx, '处理时间'] = fb['处理时间']
                result.at[idx, '备注'] = fb['备注']
            else:
                if '处理状态' not in result.columns or pd.isna(result.at[idx, '处理状态']):
                    result.at[idx, '处理状态'] = '待处理'
        
        return result

    def update_issue_history(self, current_anomalies, stat_month):
        stat_month_str = stat_month.strftime('%Y-%m')
        
        if current_anomalies is None or current_anomalies.empty:
            self._save_all_issues()
            return self.all_issues
        
        current_with_id = current_anomalies.copy()
        if '问题ID' not in current_with_id.columns:
            current_with_id['问题ID'] = current_with_id.apply(self._generate_issue_id, axis=1)
        
        for _, row in current_with_id.iterrows():
            issue_id = str(row['问题ID'])
            
            if issue_id in self.all_issues['问题ID'].values:
                idx = self.all_issues[self.all_issues['问题ID'] == issue_id].index[0]
                self.all_issues.at[idx, '最近出现月份'] = stat_month_str
                self.all_issues.at[idx, '重复出现次数'] = int(self.all_issues.at[idx, '重复出现次数']) + 1
                self.all_issues.at[idx, '负责人'] = row.get('负责人', self.all_issues.at[idx, '负责人'])
            else:
                new_issue = {
                    '问题ID': issue_id,
                    '首次发现月份': stat_month_str,
                    '最近出现月份': stat_month_str,
                    '重复出现次数': 1,
                    '车场名称': row.get('车场名称', ''),
                    '异常类型': row.get('异常类型', ''),
                    '异常描述': row.get('异常描述', ''),
                    '负责人': row.get('负责人', '待分配'),
                    '当前状态': row.get('处理状态', '待处理'),
                    '处理人': row.get('处理人', ''),
                    '处理时间': row.get('处理时间', ''),
                    '备注': row.get('备注', '')
                }
                self.all_issues = pd.concat([self.all_issues, pd.DataFrame([new_issue])], ignore_index=True)
        
        self._save_all_issues()
        return self.all_issues

    def enrich_current_issues(self, current_anomalies, stat_month):
        if current_anomalies is None or current_anomalies.empty:
            return current_anomalies
        
        result = current_anomalies.copy()
        stat_month_str = stat_month.strftime('%Y-%m')
        
        if '问题ID' not in result.columns:
            result['问题ID'] = result.apply(self._generate_issue_id, axis=1)
        
        result['问题来源'] = ''
        result['重复出现次数'] = 1
        result['首次发现月份'] = stat_month_str
        
        for idx, row in result.iterrows():
            issue_id = str(row['问题ID'])
            
            if issue_id in self.all_issues['问题ID'].values:
                hist = self.all_issues[self.all_issues['问题ID'] == issue_id].iloc[0]
                result.at[idx, '重复出现次数'] = int(hist['重复出现次数']) + 1
                result.at[idx, '首次发现月份'] = hist['首次发现月份']
                
                hist_status = str(hist.get('当前状态', '')).strip()
                if hist_status in ['已处理', '已关闭']:
                    result.at[idx, '问题来源'] = '复发问题'
                elif hist_status in ['处理中', '待处理', '驳回']:
                    result.at[idx, '问题来源'] = '历史未关闭'
                else:
                    result.at[idx, '问题来源'] = '新增问题'
            else:
                result.at[idx, '问题来源'] = '新增问题'
        
        return result

    def _save_all_issues(self):
        self.all_issues.to_csv(self.all_issues_path, index=False, encoding='utf-8-sig')

    def get_closed_loop_summary(self, current_anomalies, stat_month):
        stat_month_str = stat_month.strftime('%Y-%m')
        
        if current_anomalies is None or current_anomalies.empty:
            summary_data = [{
                '负责人': '无',
                '本月新增问题数': 0,
                '历史未关闭数': 0,
                '本月已关闭数': 0,
                '超期未处理数': 0,
                '复发问题数': 0,
                '问题总数': 0,
                '本月闭环率(%)': 0
            }]
            return pd.DataFrame(summary_data)
        
        current_enriched = current_anomalies.copy()
        if '负责人' not in current_enriched.columns:
            current_enriched['负责人'] = '待分配'
        current_enriched['负责人'] = current_enriched['负责人'].apply(
            lambda x: '待分配' if pd.isna(x) or str(x).strip() == '' else str(x).strip()
        )
        
        summary_data = []
        for manager, group in current_enriched.groupby('负责人'):
            new_count = len(group[group.get('问题来源', '') == '新增问题']) if '问题来源' in group.columns else len(group)
            history_count = len(group[group.get('问题来源', '') == '历史未关闭']) if '问题来源' in group.columns else 0
            recurrence_count = len(group[group.get('问题来源', '') == '复发问题']) if '问题来源' in group.columns else 0
            
            closed_count = len(group[group.get('处理状态', '') == '已处理']) if '处理状态' in group.columns else 0
            
            overdue_count = 0
            if '处理状态' in group.columns:
                overdue = group[
                    (group['处理状态'] != '已处理') & 
                    (group['处理状态'] != '已关闭')
                ]
                overdue_count = len(overdue)
            
            total = len(group)
            close_rate = (closed_count / total * 100) if total > 0 else 0
            
            summary_data.append({
                '负责人': manager,
                '本月新增问题数': new_count,
                '历史未关闭数': history_count,
                '本月已关闭数': closed_count,
                '超期未处理数': overdue_count,
                '复发问题数': recurrence_count,
                '问题总数': total,
                '本月闭环率(%)': round(close_rate, 2)
            })
        
        df = pd.DataFrame(summary_data)
        
        total_row = {
            '负责人': '合计',
            '本月新增问题数': df['本月新增问题数'].sum(),
            '历史未关闭数': df['历史未关闭数'].sum(),
            '本月已关闭数': df['本月已关闭数'].sum(),
            '超期未处理数': df['超期未处理数'].sum(),
            '复发问题数': df['复发问题数'].sum(),
            '问题总数': df['问题总数'].sum(),
            '本月闭环率(%)': round((df['本月已关闭数'].sum() / df['问题总数'].sum() * 100) if df['问题总数'].sum() > 0 else 0, 2)
        }
        df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)
        
        return df
