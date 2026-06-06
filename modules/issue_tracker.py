import os
import pandas as pd
from datetime import datetime, timedelta
from utils.common import load_config, ensure_dir, get_file_list


class IssueTracker:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.tracking_dir = ensure_dir(os.path.join(
            self.config['paths']['history_dir'],
            'issue_tracking'
        ))
        self.feedback_dir = ensure_dir('./data/feedback')
        self.lifecycle_dir = ensure_dir(os.path.join(self.tracking_dir, 'lifecycle'))
        self.all_issues_path = os.path.join(self.tracking_dir, '所有问题台账.csv')
        self.lifecycle_path = os.path.join(self.tracking_dir, '问题生命周期.csv')
        self._load_all_issues()
        self._load_lifecycle()

        self.default_deadlines = {
            '高': 3,
            '中': 7,
            '低': 15
        }

    def _load_all_issues(self):
        if os.path.exists(self.all_issues_path):
            self.all_issues = pd.read_csv(self.all_issues_path, encoding='utf-8-sig')
            self.all_issues['问题ID'] = self.all_issues['问题ID'].astype(str)
            if '发现日期' not in self.all_issues.columns:
                self.all_issues['发现日期'] = ''
            if '建议处理期限' not in self.all_issues.columns:
                self.all_issues['建议处理期限'] = ''
            if '严重程度' not in self.all_issues.columns:
                self.all_issues['严重程度'] = '中'
        else:
            self.all_issues = pd.DataFrame(columns=[
                '问题ID', '首次发现月份', '最近出现月份', '重复出现次数',
                '车场名称', '异常类型', '异常描述', '严重程度', '负责人',
                '当前状态', '处理人', '处理时间', '备注',
                '发现日期', '建议处理期限'
            ])

    def _load_lifecycle(self):
        if os.path.exists(self.lifecycle_path):
            self.lifecycle = pd.read_csv(self.lifecycle_path, encoding='utf-8-sig')
            self.lifecycle['问题ID'] = self.lifecycle['问题ID'].astype(str)
        else:
            self.lifecycle = pd.DataFrame(columns=[
                '问题ID', '事件类型', '事件时间', '事件描述',
                '操作人', '关联批次', '车场名称', '异常类型'
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

    def _add_lifecycle_event(self, issue_id, event_type, event_desc, event_time=None,
                             operator='', batch_id='', parking='', issue_type=''):
        if event_time is None:
            event_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        new_event = {
            '问题ID': str(issue_id),
            '事件类型': event_type,
            '事件时间': event_time,
            '事件描述': event_desc,
            '操作人': operator,
            '关联批次': batch_id,
            '车场名称': parking,
            '异常类型': issue_type
        }
        self.lifecycle = pd.concat([self.lifecycle, pd.DataFrame([new_event])], ignore_index=True)

    def _get_all_issues_for_match(self, current_anomalies=None):
        all_data = self.all_issues.copy()
        if current_anomalies is not None and not current_anomalies.empty:
            curr = current_anomalies.copy()
            if '问题ID' not in curr.columns:
                curr['问题ID'] = curr.apply(self._generate_issue_id, axis=1)
            for col in all_data.columns:
                if col not in curr.columns:
                    curr[col] = ''
            curr = curr[all_data.columns]
            all_data = pd.concat([all_data, curr], ignore_index=True)
            all_data = all_data.drop_duplicates(subset=['问题ID'], keep='first')
        return all_data

    def _fuzzy_match_feedback(self, feedback_row, all_issues_df):
        issue_id = str(feedback_row.get('问题ID', '')).strip()
        if issue_id and issue_id != 'nan' and issue_id in all_issues_df['问题ID'].values:
            matches = all_issues_df[all_issues_df['问题ID'] == issue_id]
            return matches.to_dict('records')

        candidates = all_issues_df.copy()
        score = pd.Series([0] * len(candidates), index=candidates.index)

        parking = str(feedback_row.get('车场名称', '')).strip()
        if parking and parking != 'nan':
            mask = candidates['车场名称'].astype(str).str.contains(parking, case=False, na=False)
            score[mask] += 10

        manager = str(feedback_row.get('负责人', '')).strip()
        if manager and manager != 'nan':
            mask = candidates['负责人'].astype(str).str.contains(manager, case=False, na=False)
            score[mask] += 5

        itype = str(feedback_row.get('异常类型', '')).strip()
        if itype and itype != 'nan':
            mask = candidates['异常类型'].astype(str).str.contains(itype, case=False, na=False)
            score[mask] += 8

        desc = str(feedback_row.get('异常描述', '')).strip()
        if desc and desc != 'nan':
            keywords = [k.strip() for k in desc.split() if k.strip()]
            for kw in keywords:
                mask = candidates['异常描述'].astype(str).str.contains(kw, case=False, na=False)
                score[mask] += 3

        valid_mask = score >= 8
        if not valid_mask.any():
            return []

        candidates = candidates[valid_mask].copy()
        candidates['匹配分数'] = score[valid_mask]
        candidates = candidates.sort_values('匹配分数', ascending=False)

        max_score = candidates['匹配分数'].iloc[0]
        best_matches = candidates[candidates['匹配分数'] == max_score]

        return best_matches.to_dict('records')

    def load_feedback_file(self, feedback_path=None, current_anomalies=None):
        if feedback_path is None:
            files = get_file_list(self.feedback_dir, ['.xlsx', '.xls', '.csv'])
            if not files:
                return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
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
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        return self._process_feedback(feedback_df, current_anomalies)

    def _process_feedback(self, feedback_df, current_anomalies=None):
        if feedback_df is None or feedback_df.empty:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        if '处理状态' not in feedback_df.columns:
            print(f"  ⚠ 反馈文件缺少必要列: 处理状态")
            return pd.DataFrame(), pd.DataFrame(), feedback_df

        all_issues_for_match = self._get_all_issues_for_match(current_anomalies)

        matched_single = []
        matched_multi = []
        unmatched = []

        for _, row in feedback_df.iterrows():
            candidates = self._fuzzy_match_feedback(row, all_issues_for_match)

            if len(candidates) == 1:
                row_copy = row.copy()
                row_copy['匹配问题ID'] = candidates[0]['问题ID']
                row_copy['匹配分数'] = candidates[0].get('匹配分数', 100)
                matched_single.append(row_copy)
            elif len(candidates) > 1:
                row_copy = row.copy()
                row_copy['候选问题数'] = len(candidates)
                row_copy['候选问题ID'] = ';'.join([c['问题ID'] for c in candidates])
                matched_multi.append(row_copy)
            else:
                unmatched.append(row)

        matched_df = pd.DataFrame(matched_single) if matched_single else pd.DataFrame()
        pending_df = pd.DataFrame(matched_multi) if matched_multi else pd.DataFrame()
        unmatched_df = pd.DataFrame(unmatched) if unmatched else pd.DataFrame()

        if not pending_df.empty:
            print(f"  ⚠ 发现 {len(pending_df)} 条反馈匹配到多个候选问题，已记录到反馈待确认")
        if not unmatched_df.empty:
            print(f"  ⚠ 发现 {len(unmatched_df)} 条反馈无法匹配到任何问题")
        if not matched_df.empty:
            print(f"  ✓ 成功匹配 {len(matched_df)} 条处理反馈")

        return matched_df, pending_df, unmatched_df

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
            issue_id = str(row.get('匹配问题ID', row.get('问题ID', '')))
            feedback_dict[issue_id] = {
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

    def update_history_from_feedback(self, matched_feedback, stat_month):
        if matched_feedback is None or matched_feedback.empty:
            return

        stat_month_str = stat_month.strftime('%Y-%m')
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for _, row in matched_feedback.iterrows():
            issue_id = str(row.get('匹配问题ID', row.get('问题ID', '')))
            if not issue_id or issue_id == 'nan':
                continue

            status = str(row.get('处理状态', '')).strip()
            handler = str(row.get('处理人', '')).strip()
            handle_time = str(row.get('处理时间', now)).strip()
            remark = str(row.get('备注', '')).strip()

            if issue_id in self.all_issues['问题ID'].values:
                idx = self.all_issues[self.all_issues['问题ID'] == issue_id].index[0]
                old_status = str(self.all_issues.at[idx, '当前状态'])
                self.all_issues.at[idx, '当前状态'] = status
                self.all_issues.at[idx, '处理人'] = handler
                self.all_issues.at[idx, '处理时间'] = handle_time
                self.all_issues.at[idx, '备注'] = remark

                event_desc = f"状态变更: {old_status} → {status}"
                if remark:
                    event_desc += f"，备注: {remark}"
                parking = self.all_issues.at[idx, '车场名称']
                itype = self.all_issues.at[idx, '异常类型']
                self._add_lifecycle_event(issue_id, '处理反馈', event_desc,
                                         handle_time, handler, parking=parking, issue_type=itype)
            else:
                pass

        self._save_all_issues()
        self._save_lifecycle()

    def update_issue_history(self, current_anomalies, stat_month):
        stat_month_str = stat_month.strftime('%Y-%m')
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if current_anomalies is None or current_anomalies.empty:
            self._save_all_issues()
            self._save_lifecycle()
            return self.all_issues

        current_with_id = current_anomalies.copy()
        if '问题ID' not in current_with_id.columns:
            current_with_id['问题ID'] = current_with_id.apply(self._generate_issue_id, axis=1)

        for _, row in current_with_id.iterrows():
            issue_id = str(row['问题ID'])
            parking = row.get('车场名称', '')
            itype = row.get('异常类型', '')
            desc = row.get('异常描述', '')
            severity = row.get('严重程度', '中')
            manager = row.get('负责人', '待分配')

            if issue_id in self.all_issues['问题ID'].values:
                idx = self.all_issues[self.all_issues['问题ID'] == issue_id].index[0]
                old_count = int(self.all_issues.at[idx, '重复出现次数'])
                self.all_issues.at[idx, '最近出现月份'] = stat_month_str
                self.all_issues.at[idx, '重复出现次数'] = old_count + 1
                self.all_issues.at[idx, '负责人'] = manager
                self.all_issues.at[idx, '严重程度'] = severity

                if old_count == 0:
                    event_desc = f"首次发现: {itype} - {desc[:30]}"
                    self._add_lifecycle_event(issue_id, '首次发现', event_desc,
                                             now, parking=parking, issue_type=itype)
                else:
                    event_desc = f"第{old_count + 1}次出现: {itype}"
                    self._add_lifecycle_event(issue_id, '重复出现', event_desc,
                                             now, parking=parking, issue_type=itype)
            else:
                deadline_days = self.default_deadlines.get(severity, 7)
                find_date = row.get('异常日期', stat_month_str + '-01')
                try:
                    find_dt = pd.to_datetime(find_date)
                    if pd.isna(find_dt):
                        find_dt = stat_month
                except:
                    find_dt = stat_month
                deadline = (find_dt + timedelta(days=deadline_days)).strftime('%Y-%m-%d')

                new_issue = {
                    '问题ID': issue_id,
                    '首次发现月份': stat_month_str,
                    '最近出现月份': stat_month_str,
                    '重复出现次数': 1,
                    '车场名称': parking,
                    '异常类型': itype,
                    '异常描述': desc,
                    '严重程度': severity,
                    '负责人': manager,
                    '当前状态': row.get('处理状态', '待处理'),
                    '处理人': row.get('处理人', ''),
                    '处理时间': row.get('处理时间', ''),
                    '备注': row.get('备注', ''),
                    '发现日期': find_date,
                    '建议处理期限': deadline
                }
                self.all_issues = pd.concat([self.all_issues, pd.DataFrame([new_issue])], ignore_index=True)

                event_desc = f"首次发现: {itype} - {desc[:30]}"
                self._add_lifecycle_event(issue_id, '首次发现', event_desc,
                                         now, parking=parking, issue_type=itype)

        self._save_all_issues()
        self._save_lifecycle()
        return self.all_issues

    def add_notification_event(self, issue_ids, batch_id, stat_month):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for issue_id in issue_ids:
            issue_id = str(issue_id)
            issue_info = self.all_issues[self.all_issues['问题ID'] == issue_id]
            parking = issue_info['车场名称'].iloc[0] if not issue_info.empty else ''
            itype = issue_info['异常类型'].iloc[0] if not issue_info.empty else ''
            self._add_lifecycle_event(issue_id, '发送通知',
                                     f"发送负责人待办通知", now,
                                     batch_id=batch_id, parking=parking, issue_type=itype)
        self._save_lifecycle()

    def _calculate_deadline_info(self, issue_row, today=None):
        if today is None:
            today = datetime.now()

        deadline_str = str(issue_row.get('建议处理期限', ''))
        if not deadline_str or deadline_str == 'nan':
            severity = str(issue_row.get('严重程度', '中'))
            days = self.default_deadlines.get(severity, 7)
            find_date_str = str(issue_row.get('发现日期', ''))
            try:
                find_date = pd.to_datetime(find_date_str)
                if pd.isna(find_date):
                    find_date = today
            except:
                find_date = today
            deadline = find_date + timedelta(days=days)
        else:
            try:
                deadline = pd.to_datetime(deadline_str)
                if pd.isna(deadline):
                    deadline = today + timedelta(days=7)
            except:
                deadline = today + timedelta(days=7)

        try:
            days_left = (deadline.date() - today.date()).days
        except:
            days_left = 7

        status = str(issue_row.get('当前状态', '待处理')).strip()
        is_closed = status in ['已处理', '已关闭']

        if is_closed:
            overdue_status = '已关闭'
        elif days_left < 0:
            overdue_status = '已超期'
        elif days_left <= 2:
            overdue_status = '即将超期'
        else:
            overdue_status = '正常'

        return {
            '截止日期': deadline.strftime('%Y-%m-%d'),
            '剩余天数': days_left,
            '超期状态': overdue_status
        }

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
        result['超期状态'] = '正常'
        result['剩余天数'] = 0
        result['建议处理期限'] = ''

        today = datetime.now()

        for idx, row in result.iterrows():
            issue_id = str(row['问题ID'])

            deadline_info = self._calculate_deadline_info(row, today)
            result.at[idx, '超期状态'] = deadline_info['超期状态']
            result.at[idx, '剩余天数'] = deadline_info['剩余天数']
            result.at[idx, '建议处理期限'] = deadline_info['截止日期']

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

    def get_closed_loop_summary(self, current_anomalies, stat_month, matched_feedback=None):
        stat_month_str = stat_month.strftime('%Y-%m')
        today = datetime.now()

        all_issues_list = []

        if current_anomalies is not None and not current_anomalies.empty:
            for _, row in current_anomalies.iterrows():
                issue_id = str(row.get('问题ID', ''))
                all_issues_list.append({
                    '问题ID': issue_id,
                    '负责人': row.get('负责人', '待分配'),
                    '问题来源': row.get('问题来源', '新增问题'),
                    '处理状态': row.get('处理状态', '待处理'),
                    '严重程度': row.get('严重程度', '中'),
                    '发现日期': row.get('发现日期', stat_month_str + '-01'),
                    '建议处理期限': row.get('建议处理期限', '')
                })

        if matched_feedback is not None and not matched_feedback.empty:
            for _, row in matched_feedback.iterrows():
                issue_id = str(row.get('匹配问题ID', row.get('问题ID', '')))
                status = str(row.get('处理状态', '')).strip()
                if status in ['已处理', '已关闭']:
                    existing_ids = [i['问题ID'] for i in all_issues_list]
                    if issue_id not in existing_ids:
                        issue_info = self.all_issues[self.all_issues['问题ID'] == issue_id]
                        if not issue_info.empty:
                            info = issue_info.iloc[0]
                            all_issues_list.append({
                                '问题ID': issue_id,
                                '负责人': info.get('负责人', '待分配'),
                                '问题来源': '历史关闭',
                                '处理状态': status,
                                '严重程度': info.get('严重程度', '中'),
                                '发现日期': info.get('发现日期', ''),
                                '建议处理期限': info.get('建议处理期限', '')
                            })

        if not all_issues_list:
            summary_data = [{
                '负责人': '无',
                '本月新增问题数': 0,
                '历史未关闭数': 0,
                '本月已关闭数': 0,
                '复发问题数': 0,
                '超期未处理数': 0,
                '即将超期数': 0,
                '平均处理天数': 0,
                '最长未处理天数': 0,
                '问题总数': 0,
                '本月闭环率(%)': 0
            }]
            return pd.DataFrame(summary_data)

        issues_df = pd.DataFrame(all_issues_list)
        issues_df['负责人'] = issues_df['负责人'].apply(
            lambda x: '待分配' if pd.isna(x) or str(x).strip() == '' else str(x).strip()
        )

        summary_data = []
        for manager, group in issues_df.groupby('负责人'):
            new_count = len(group[group['问题来源'] == '新增问题'])
            history_count = len(group[group['问题来源'] == '历史未关闭'])
            recurrence_count = len(group[group['问题来源'] == '复发问题'])

            closed_count = len(group[group['处理状态'].isin(['已处理', '已关闭'])])

            open_issues = group[~group['处理状态'].isin(['已处理', '已关闭'])]

            overdue_count = 0
            soon_overdue_count = 0
            process_days_list = []
            max_open_days = 0

            for _, issue in open_issues.iterrows():
                dl_info = self._calculate_deadline_info(issue, today)
                if dl_info['超期状态'] == '已超期':
                    overdue_count += 1
                elif dl_info['超期状态'] == '即将超期':
                    soon_overdue_count += 1

                try:
                    find_date = pd.to_datetime(issue.get('发现日期', today))
                    days_open = (today.date() - find_date.date()).days
                    if days_open > max_open_days:
                        max_open_days = days_open
                except:
                    pass

            closed_issues = group[group['处理状态'].isin(['已处理', '已关闭'])]
            for _, issue in closed_issues.iterrows():
                try:
                    find_date = pd.to_datetime(issue.get('发现日期', today))
                    handle_time_str = str(issue.get('处理时间', ''))
                    if handle_time_str and handle_time_str != 'nan':
                        handle_date = pd.to_datetime(handle_time_str)
                        days = (handle_date.date() - find_date.date()).days
                        if days > 0:
                            process_days_list.append(days)
                except:
                    pass

            avg_process_days = round(sum(process_days_list) / len(process_days_list), 1) if process_days_list else 0

            total = len(group)
            close_rate = (closed_count / total * 100) if total > 0 else 0

            summary_data.append({
                '负责人': manager,
                '本月新增问题数': new_count,
                '历史未关闭数': history_count,
                '本月已关闭数': closed_count,
                '复发问题数': recurrence_count,
                '超期未处理数': overdue_count,
                '即将超期数': soon_overdue_count,
                '平均处理天数': avg_process_days,
                '最长未处理天数': max_open_days,
                '问题总数': total,
                '本月闭环率(%)': round(close_rate, 2)
            })

        df = pd.DataFrame(summary_data)

        total_row = {
            '负责人': '合计',
            '本月新增问题数': df['本月新增问题数'].sum(),
            '历史未关闭数': df['历史未关闭数'].sum(),
            '本月已关闭数': df['本月已关闭数'].sum(),
            '复发问题数': df['复发问题数'].sum(),
            '超期未处理数': df['超期未处理数'].sum(),
            '即将超期数': df['即将超期数'].sum(),
            '平均处理天数': round(df['平均处理天数'].mean(), 1) if not df.empty else 0,
            '最长未处理天数': df['最长未处理天数'].max() if not df.empty else 0,
            '问题总数': df['问题总数'].sum(),
            '本月闭环率(%)': round((df['本月已关闭数'].sum() / df['问题总数'].sum() * 100) if df['问题总数'].sum() > 0 else 0, 2)
        }
        df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)

        return df

    def get_lifecycle_sheet(self):
        if self.lifecycle.empty:
            return pd.DataFrame(columns=[
                '问题ID', '事件类型', '事件时间', '事件描述',
                '操作人', '关联批次', '车场名称', '异常类型'
            ])
        return self.lifecycle.sort_values(['问题ID', '事件时间'], ascending=[True, True])

    def export_feedback_template(self, current_anomalies, stat_month, output_path=None):
        if current_anomalies is None or current_anomalies.empty:
            print("  ⚠ 当前无异常问题，无法生成模板")
            return None

        if output_path is None:
            template_dir = ensure_dir(self.feedback_dir)
            filename = f"反馈模板_{stat_month.strftime('%Y%m')}.xlsx"
            output_path = os.path.join(template_dir, filename)

        template_data = []
        for _, row in current_anomalies.iterrows():
            issue_id = str(row.get('问题ID', ''))
            if not issue_id or issue_id == 'nan':
                issue_id = self._generate_issue_id(row)

            severity = row.get('严重程度', '中')
            deadline_days = self.default_deadlines.get(severity, 7)
            find_date_str = str(row.get('异常日期', stat_month.strftime('%Y-%m-01')))
            try:
                find_date = pd.to_datetime(find_date_str)
                if pd.isna(find_date):
                    find_date = stat_month
            except:
                find_date = stat_month
            deadline = (find_date + timedelta(days=deadline_days)).strftime('%Y-%m-%d')

            template_data.append({
                '问题ID': issue_id,
                '车场名称': row.get('车场名称', ''),
                '负责人': row.get('负责人', ''),
                '异常类型': row.get('异常类型', ''),
                '异常描述': row.get('异常描述', ''),
                '严重程度': severity,
                '建议处理期限': deadline,
                '处理状态': '',
                '处理人': '',
                '处理时间': '',
                '备注': ''
            })

        template_df = pd.DataFrame(template_data)
        template_df.to_excel(output_path, index=False)
        print(f"  ✓ 反馈模板已生成: {output_path}")
        return output_path

    def _save_all_issues(self):
        self.all_issues.to_csv(self.all_issues_path, index=False, encoding='utf-8-sig')

    def _save_lifecycle(self):
        self.lifecycle.to_csv(self.lifecycle_path, index=False, encoding='utf-8-sig')
