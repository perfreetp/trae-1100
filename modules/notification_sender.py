import os
import json
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
        self.batch_id = datetime.now().strftime('%Y%m%d_%H%M%S')

    def generate_message_content(self, manager, manager_anomalies, stat_month):
        high_count = len(manager_anomalies[manager_anomalies['严重程度'] == '高'])
        mid_count = len(manager_anomalies[manager_anomalies['严重程度'] == '中'])
        low_count = len(manager_anomalies[manager_anomalies['严重程度'] == '低'])
        total = len(manager_anomalies)
        
        parkings = manager_anomalies['车场名称'].unique()
        anomaly_types = manager_anomalies['异常类型'].unique()
        
        subject = f"【智慧停车运营月报】{stat_month.strftime('%Y年%m月')} 待处理异常提醒 - {manager}"
        
        body = f"""尊敬的 {manager} 您好：

您负责的车场在 {stat_month.strftime('%Y年%m月')} 运营检查中发现以下待处理问题：

━━━━━━━━━━━━━━━━━━━━━━━
📊 问题概览
━━━━━━━━━━━━━━━━━━━━━━━
  总计异常: {total} 项
  🔴 高优先级: {high_count} 项
  🟡 中优先级: {mid_count} 项
  🟢 低优先级: {low_count} 项

🏢 涉及车场: {', '.join(parkings)}
📋 问题类型: {', '.join(anomaly_types)}

━━━━━━━━━━━━━━━━━━━━━━━
📝 异常明细
━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        for idx, (_, row) in enumerate(manager_anomalies.iterrows(), 1):
            priority_icon = '🔴' if row['严重程度'] == '高' else '🟡' if row['严重程度'] == '中' else '🟢'
            body += f"\n{priority_icon} [{idx}] {row['异常类型']}\n"
            body += f"    车场: {row['车场名称']}\n"
            body += f"    描述: {row['异常描述']}\n"
            if '异常详情' in row and pd.notna(row['异常详情']):
                body += f"    详情: {row['异常详情']}\n"
            if '异常日期' in row and pd.notna(row['异常日期']):
                body += f"    日期: {row['异常日期']}\n"
            body += "    ─────────────────────────────\n"
        
        body += f"""
━━━━━━━━━━━━━━━━━━━━━━━
📌 处理要求
━━━━━━━━━━━━━━━━━━━━━━━
  • 高优先级问题请在 3 个工作日内处理
  • 中优先级问题请在 7 个工作日内处理
  • 处理完成后请在系统中更新状态

如有疑问请联系运营管理部门。

--
智慧停车月度运营自动化工具
发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        return subject, body

    def preview_messages(self, manager_todos, anomalies_df, stat_month):
        print("\n" + "="*60)
        print("                 📧 消息预览模式")
        print("="*60)
        print(f"\n统计月份: {stat_month.strftime('%Y年%m月')}")
        print(f"发送批次: {self.batch_id}")
        print(f"待发送: {len(manager_todos)} 位负责人\n")
        
        previews = []
        for _, manager_row in manager_todos.iterrows():
            manager = manager_row['负责人']
            if manager == '待分配':
                continue
            
            manager_anomalies = anomalies_df[anomalies_df['负责人'] == manager]
            subject, body = self.generate_message_content(manager, manager_anomalies, stat_month)
            
            previews.append({
                '负责人': manager,
                '问题数量': len(manager_anomalies),
                '主题': subject,
                '内容': body
            })
            
            print(f"{'─'*60}")
            print(f"👤 负责人: {manager}")
            print(f"📋 问题数: {len(manager_anomalies)}")
            print(f"📧 主题: {subject}")
            print(f"\n{'-'*60}")
            print(body[:500] + "..." if len(body) > 500 else body)
            print(f"\n")
        
        print(f"{'='*60}")
        print(f"预览完成，共 {len(previews)} 条消息")
        print(f"{'='*60}\n")
        
        return previews

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
        except Exception as e:
            return False, str(e)

    def _simulate_send(self, manager, subject, body):
        return True, "模拟发送成功（配置中禁用真实发送）"

    def send_notifications(self, manager_todos, anomalies_df, stat_month, send_mode='preview'):
        print(f"\n开始发送负责人待办通知 (模式: {send_mode})...")
        self.send_records = []
        
        if anomalies_df is None or anomalies_df.empty:
            print("  ℹ 没有待发送的异常事项")
            return pd.DataFrame()
        
        if send_mode == 'preview':
            return self.preview_messages(manager_todos, anomalies_df, stat_month)
        
        success_count = 0
        fail_count = 0
        
        for _, manager_row in manager_todos.iterrows():
            manager = manager_row['负责人']
            if manager == '待分配':
                self.send_records.append({
                    '批次ID': self.batch_id,
                    '发送时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    '负责人': manager,
                    '问题数量': 0,
                    '发送状态': '跳过',
                    '失败原因': '未分配负责人',
                    '统计月份': stat_month.strftime('%Y-%m')
                })
                continue
            
            manager_anomalies = anomalies_df[anomalies_df['负责人'] == manager]
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
        
        print(f"\n发送完成: 成功 {success_count} 条，失败 {fail_count} 条")
        return pd.DataFrame(self.send_records)

    def save_send_records(self, stat_month):
        if not self.send_records:
            return None
        
        records_df = pd.DataFrame(self.send_records)
        
        record_dir = ensure_dir(os.path.join(
            self.history_dir,
            stat_month.strftime('%Y-%m')
        ))
        record_path = os.path.join(
            record_dir,
            f"发送记录_{self.batch_id}.csv"
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
        
        return records_df
