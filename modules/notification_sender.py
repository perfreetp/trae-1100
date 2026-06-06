import os
import pandas as pd
from datetime import datetime
from utils.common import load_config, ensure_dir


class NotificationSender:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.history_dir = ensure_dir(os.path.join(
            self.config['paths']['history_dir'],
            'notifications'
        ))
        self.notification_config = self.config.get('notification', {})
        self.send_records = []
        self.preview_records = []
        self.batch_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.send_mode = 'none'

    def generate_message_content(self, manager, manager_anomalies, stat_month):
        high_count = len(manager_anomalies[manager_anomalies['严重程度'] == '高'])
        mid_count = len(manager_anomalies[manager_anomalies['严重程度'] == '中'])
        low_count = len(manager_anomalies[manager_anomalies['严重程度'] == '低'])
        total = len(manager_anomalies)
        
        if '问题来源' in manager_anomalies.columns:
            new_count = len(manager_anomalies[manager_anomalies['问题来源'] == '新增问题'])
            history_count = len(manager_anomalies[manager_anomalies['问题来源'] == '历史未关闭'])
            recurrence_count = len(manager_anomalies[manager_anomalies['问题来源'] == '复发问题'])
        else:
            new_count = total
            history_count = 0
            recurrence_count = 0
        
        parkings = manager_anomalies['车场名称'].unique()
        anomaly_types = manager_anomalies['异常类型'].unique()
        
        subject_parts = []
        if new_count > 0:
            subject_parts.append(f"新增{new_count}项")
        if history_count > 0:
            subject_parts.append(f"未关闭{history_count}项")
        if recurrence_count > 0:
            subject_parts.append(f"复发{recurrence_count}项")
        subject_tag = ', '.join(subject_parts) if subject_parts else f"共{total}项"
        
        subject = f"【智慧停车运营月报】{stat_month.strftime('%Y年%m月')} ({subject_tag}) - {manager}"
        
        body = f"""尊敬的 {manager} 您好：

您负责的车场在 {stat_month.strftime('%Y年%m月')} 运营检查中发现以下待处理问题：

━━━━━━━━━━━━━━━━━━━━━━━
📊 问题概览
━━━━━━━━━━━━━━━━━━━━━━━
  总计异常: {total} 项
  🔴 高优先级: {high_count} 项
  🟡 中优先级: {mid_count} 项
  🟢 低优先级: {low_count} 项

  🆕 新增问题: {new_count} 项
  ⏳ 历史未关闭: {history_count} 项
  🔁 复发问题: {recurrence_count} 项

🏢 涉及车场: {', '.join(parkings)}
📋 问题类型: {', '.join(anomaly_types)}

━━━━━━━━━━━━━━━━━━━━━━━
📝 异常明细
━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        for idx, (_, row) in enumerate(manager_anomalies.iterrows(), 1):
            priority_icon = '🔴' if row['严重程度'] == '高' else '🟡' if row['严重程度'] == '中' else '🟢'
            
            source_tag = ''
            if '问题来源' in row and pd.notna(row['问题来源']):
                source = row['问题来源']
                if source == '新增问题':
                    source_tag = ' 🆕'
                elif source == '历史未关闭':
                    source_tag = ' ⏳'
                elif source == '复发问题':
                    source_tag = ' 🔁'
            
            recurrence_tag = ''
            if '重复出现次数' in row and pd.notna(row['重复出现次数']) and int(row['重复出现次数']) > 1:
                recurrence_tag = f" (重复{int(row['重复出现次数'])}次)"
            
            first_found_tag = ''
            if '首次发现月份' in row and pd.notna(row['首次发现月份']):
                first_found_tag = f" [首次发现:{row['首次发现月份']}]"
            
            body += f"\n{priority_icon} [{idx}] {row['异常类型']}{source_tag}{recurrence_tag}{first_found_tag}\n"
            body += f"    车场: {row['车场名称']}\n"
            body += f"    描述: {row['异常描述']}\n"
            if '异常详情' in row and pd.notna(row['异常详情']) and str(row['异常详情']).strip():
                body += f"    详情: {row['异常详情']}\n"
            if '异常日期' in row and pd.notna(row['异常日期']):
                body += f"    日期: {row['异常日期']}\n"
            if '问题ID' in row and pd.notna(row['问题ID']):
                body += f"    问题ID: {row['问题ID']}\n"
            body += "    ─────────────────────────────\n"
        
        body += f"""
━━━━━━━━━━━━━━━━━━━━━━━
📌 处理要求
━━━━━━━━━━━━━━━━━━━━━━━
  • 高优先级问题请在 3 个工作日内处理
  • 中优先级问题请在 7 个工作日内处理
  • 处理完成后请在系统中更新状态
  • 🔁标记为复发的问题请重点关注根因分析

如有疑问请联系运营管理部门。

--
智慧停车月度运营自动化工具
生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        return subject, body

    def _normalize_manager(self, manager):
        if pd.isna(manager) or str(manager).strip() == '' or manager == 'nan':
            return '待分配'
        return str(manager).strip()

    def _group_by_manager(self, anomalies_df):
        if anomalies_df is None or anomalies_df.empty:
            return {}
        
        df = anomalies_df.copy()
        df['负责人'] = df['负责人'].apply(self._normalize_manager)
        
        manager_groups = {}
        for manager, group in df.groupby('负责人'):
            manager_groups[manager] = group
        
        return manager_groups

    def preview_messages(self, manager_todos, anomalies_df, stat_month, target_managers=None):
        print("\n" + "="*60)
        print("                 📧 消息预览模式")
        print("="*60)
        print(f"\n统计月份: {stat_month.strftime('%Y年%m月')}")
        print(f"发送批次: {self.batch_id}")
        
        manager_groups = self._group_by_manager(anomalies_df)
        
        if target_managers:
            filtered = {k: v for k, v in manager_groups.items() if k in target_managers}
            manager_groups = filtered
            print(f"指定发送: {', '.join(target_managers)}")
        
        print(f"待发送: {len(manager_groups)} 位负责人\n")
        
        previews = []
        for manager, manager_anomalies in manager_groups.items():
            subject, body = self.generate_message_content(manager, manager_anomalies, stat_month)
            
            preview_record = {
                '批次ID': self.batch_id,
                '生成时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                '发送模式': 'preview',
                '负责人': manager,
                '问题数量': len(manager_anomalies),
                '消息主题': subject,
                '消息内容': body,
                '统计月份': stat_month.strftime('%Y-%m')
            }
            previews.append(preview_record)
            self.preview_records.append(preview_record)
            
            print(f"{'─'*60}")
            print(f"👤 负责人: {manager}")
            print(f"📋 问题数: {len(manager_anomalies)}")
            print(f"📧 主题: {subject}")
            print(f"\n{'-'*60}")
            print(body[:600] + "..." if len(body) > 600 else body)
            print(f"\n")
        
        print(f"{'='*60}")
        print(f"预览完成，共 {len(previews)} 条消息")
        print(f"{'='*60}\n")
        
        return pd.DataFrame(previews)

    def _send_email(self, to_email, subject, body):
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            smtp_config = self.notification_config.get('smtp', {})
            if not smtp_config:
                return False, "未配置SMTP邮件服务器"
            
            msg = MIMEMultipart()
            msg['From'] = smtp_config.get('sender', 'noreply@parking.com')
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            server = smtplib.SMTP(smtp_config.get('host', 'localhost'), smtp_config.get('port', 25))
            if smtp_config.get('use_tls', False):
                server.starttls()
            
            username = smtp_config.get('username')
            password = smtp_config.get('password')
            if username and password:
                server.login(username, password)
            
            server.send_message(msg)
            server.quit()
            
            return True, "发送成功"
        except Exception as e:
            return False, str(e)

    def _send_webhook(self, webhook_url, subject, body):
        try:
            import requests
            
            payload = {
                'msgtype': 'text',
                'text': {
                    'content': f"{subject}\n\n{body}"
                }
            }
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            if response.status_code == 200:
                return True, "发送成功"
            else:
                return False, f"HTTP {response.status_code}: {response.text}"
        except ImportError:
            return False, "未安装requests库"
        except Exception as e:
            return False, str(e)

    def _simulate_send(self, manager, subject, body):
        return True, "模拟发送成功"

    def send_notifications(self, manager_todos, anomalies_df, stat_month, 
                          send_mode='preview', target_managers=None):
        print(f"\n开始发送负责人待办通知 (模式: {send_mode})...")
        self.send_records = []
        self.send_mode = send_mode
        
        if anomalies_df is None or anomalies_df.empty:
            print("  ℹ 没有待发送的异常事项")
            empty_send = pd.DataFrame()
            review_df = self._generate_review_summary(
                anomalies_df if anomalies_df is not None else pd.DataFrame(),
                pd.DataFrame(), 
                target_managers,
                stat_month
            )
            return empty_send, review_df
        
        manager_groups = self._group_by_manager(anomalies_df)
        
        if target_managers:
            filtered = {k: v for k, v in manager_groups.items() if k in target_managers}
            skipped = len(manager_groups) - len(filtered)
            manager_groups = filtered
            print(f"  指定发送: {', '.join(target_managers)} (跳过 {skipped} 位)")
        
        if send_mode == 'preview':
            preview_df = self.preview_messages(manager_todos, anomalies_df, stat_month, target_managers)
            preview_for_review = []
            for rec in self.preview_records:
                preview_for_review.append({
                    '批次ID': rec['批次ID'],
                    '发送时间': rec['生成时间'],
                    '发送模式': 'preview',
                    '负责人': rec['负责人'],
                    '问题数量': rec['问题数量'],
                    '发送状态': '已预览',
                    '失败原因': '',
                    '耗时(秒)': 0,
                    '统计月份': rec['统计月份']
                })
            preview_records_df = pd.DataFrame(preview_for_review)
            return pd.DataFrame(self.preview_records), self._generate_review_summary(anomalies_df, preview_records_df, target_managers, stat_month)
        
        success_count = 0
        fail_count = 0
        skip_count = 0
        
        for manager, manager_anomalies in manager_groups.items():
            if manager == '待分配':
                self.send_records.append({
                    '批次ID': self.batch_id,
                    '发送时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    '发送模式': send_mode,
                    '负责人': manager,
                    '问题数量': len(manager_anomalies),
                    '发送状态': '待分配',
                    '失败原因': '未分配负责人，需手动处理',
                    '耗时(秒)': 0,
                    '统计月份': stat_month.strftime('%Y-%m')
                })
                skip_count += 1
                continue
            
            subject, body = self.generate_message_content(manager, manager_anomalies, stat_month)
            
            start_time = datetime.now()
            
            if send_mode == 'simulate':
                success, message = self._simulate_send(manager, subject, body)
            else:
                send_type = self.notification_config.get('send_type', 'simulate')
                if send_type == 'email':
                    email_map = self.notification_config.get('manager_emails', {})
                    to_email = email_map.get(manager, '')
                    if not to_email:
                        success, message = False, f"未找到{manager}的邮箱配置"
                    else:
                        success, message = self._send_email(to_email, subject, body)
                elif send_type == 'webhook':
                    webhook_url = self.notification_config.get('webhook_url', '')
                    if not webhook_url:
                        success, message = False, "未配置Webhook地址"
                    else:
                        success, message = self._send_webhook(webhook_url, subject, body)
                else:
                    success, message = self._simulate_send(manager, subject, body)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            status = '成功' if success else '失败'
            if success:
                success_count += 1
            else:
                fail_count += 1
            
            self.send_records.append({
                '批次ID': self.batch_id,
                '发送时间': end_time.strftime('%Y-%m-%d %H:%M:%S'),
                '发送模式': send_mode,
                '负责人': manager,
                '问题数量': len(manager_anomalies),
                '发送状态': status,
                '失败原因': '' if success else message,
                '耗时(秒)': round(duration, 2),
                '统计月份': stat_month.strftime('%Y-%m')
            })
            
            status_icon = '✅' if success else '❌'
            print(f"  {status_icon} {manager}: {status} ({len(manager_anomalies)}项问题)")
            if not success:
                print(f"     原因: {message}")
        
        if skip_count > 0:
            print(f"  ⏭  跳过待分配负责人: {skip_count} 位")
        
        print(f"\n发送完成: 成功 {success_count} 条，失败 {fail_count} 条，待分配 {skip_count} 条")
        
        send_records_df = pd.DataFrame(self.send_records)
        review_df = self._generate_review_summary(anomalies_df, send_records_df, target_managers, stat_month)
        
        return send_records_df, review_df

    def _generate_review_summary(self, anomalies_df, send_records_df, target_managers=None, stat_month=None):
        all_managers = set()
        stat_month_str = stat_month.strftime('%Y-%m') if stat_month else ''
        
        if anomalies_df is not None and not anomalies_df.empty:
            df = anomalies_df.copy()
            df['负责人'] = df['负责人'].apply(self._normalize_manager)
            all_managers = set(df['负责人'].unique())
        
        review_data = []
        
        if not all_managers:
            review_data.append({
                '批次ID': self.batch_id,
                '统计月份': stat_month_str,
                '负责人': '无',
                '应发问题数': 0,
                '实际发送数': 0,
                '是否未发送问题': '否',
                '发送状态': '无异常',
                '发送范围': '全部',
                '失败原因': '本月无待处理异常，无需发送',
                '发送时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        else:
            for manager in sorted(all_managers):
                manager_anomalies = anomalies_df[anomalies_df['负责人'].apply(self._normalize_manager) == manager]
                expected = len(manager_anomalies)
                
                if not send_records_df.empty:
                    record = send_records_df[send_records_df['负责人'] == manager]
                    if not record.empty:
                        actual_sent = record['问题数量'].iloc[0]
                        status = record['发送状态'].iloc[0]
                        fail_reason = record['失败原因'].iloc[0] if '失败原因' in record.columns else ''
                        batch_id = record['批次ID'].iloc[0]
                        send_time = record['发送时间'].iloc[0]
                    else:
                        actual_sent = 0
                        status = '未发送'
                        fail_reason = '本次运行未执行发送'
                        batch_id = self.batch_id
                        send_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                else:
                    actual_sent = 0
                    status = '未发送'
                    fail_reason = '本月未执行发送操作'
                    batch_id = self.batch_id
                    send_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                if target_managers and manager not in target_managers:
                    send_scope = '范围外'
                else:
                    send_scope = '目标范围'
                
                review_data.append({
                    '批次ID': batch_id,
                    '统计月份': stat_month_str,
                    '负责人': manager,
                    '应发问题数': expected,
                    '实际发送数': actual_sent,
                    '是否未发送问题': '是' if expected > actual_sent else '否',
                    '发送状态': status,
                    '发送范围': send_scope,
                    '失败原因': fail_reason,
                    '发送时间': send_time
                })
        
        return pd.DataFrame(review_data)

    def save_send_records(self, stat_month):
        all_records = []
        
        if self.send_records:
            all_records.extend(self.send_records)
        if self.preview_records:
            for rec in self.preview_records:
                rec['发送状态'] = '已预览'
                rec['耗时(秒)'] = 0
                all_records.append(rec)
        
        if not all_records:
            return None, None
        
        records_df = pd.DataFrame(all_records)
        
        record_dir = ensure_dir(os.path.join(
            self.history_dir,
            stat_month.strftime('%Y-%m')
        ))
        record_path = os.path.join(
            record_dir,
            f"发送记录_{self.batch_id}_{self.send_mode}.csv"
        )
        records_df.to_csv(record_path, index=False, encoding='utf-8-sig')
        print(f"  ✓ 发送记录已保存: {record_path}")
        
        all_records_path = os.path.join(self.history_dir, '所有发送记录.csv')
        if os.path.exists(all_records_path):
            existing = pd.read_csv(all_records_path, encoding='utf-8-sig')
            combined = pd.concat([existing, records_df], ignore_index=True)
        else:
            combined = records_df
        combined.to_csv(all_records_path, index=False, encoding='utf-8-sig')
        
        return records_df, record_path

    def get_preview_records(self):
        return pd.DataFrame(self.preview_records) if self.preview_records else pd.DataFrame()
