import sys
import argparse
import pandas as pd
from datetime import datetime
from utils.common import load_config
from modules.data_collector import DataCollector
from modules.rule_validator import RuleValidator
from modules.revenue_analyzer import RevenueAnalyzer
from modules.parking_utilization import ParkingUtilization
from modules.member_analyzer import MemberAnalyzer
from modules.report_generator import ReportGenerator
from modules.notification_sender import NotificationSender
from modules.issue_tracker import IssueTracker


def print_header():
    print("=" * 60)
    print("        智慧停车月度运营自动化工具 v1.3")
    print("=" * 60)
    print()


def main():
    parser = argparse.ArgumentParser(description='智慧停车月度运营自动化工具')
    parser.add_argument('--year', type=int, help='统计年份 (默认: 上个月所属年份)')
    parser.add_argument('--month', type=int, help='统计月份 (默认: 上个月)')
    parser.add_argument('--generate-sample', action='store_true', help='生成示例数据')
    parser.add_argument('--send-mode', 
                       choices=['none', 'preview', 'simulate', 'real'], 
                       default='none',
                       help='发送模式: none(不发送), preview(预览), simulate(模拟发送), real(真实发送)')
    parser.add_argument('--managers', nargs='*', default=None,
                       help='指定发送给部分负责人，例如 --managers 张三 李四')
    parser.add_argument('--review-only', action='store_true',
                       help='只生成闭环复盘，不重新发送通知')
    parser.add_argument('--feedback', type=str, default=None,
                       help='处理反馈文件路径 (Excel/CSV)')
    args = parser.parse_args()

    print_header()
    config = load_config()

    if args.generate_sample:
        print("生成示例数据模式...")
        from generate_sample_data import main as generate_sample
        generate_sample()
        print("\n示例数据生成完成！请重新运行工具进行分析。")
        return

    try:
        collector = DataCollector(config)
        
        stat_month = collector.select_month(args.year, args.month)
        print(f"统计月份: {stat_month.strftime('%Y年%m月')}")
        print(f"发送模式: {args.send_mode}")
        print(f"仅复盘模式: {'是' if args.review_only else '否'}")
        if args.managers:
            print(f"指定负责人: {', '.join(args.managers)}")
        if args.feedback:
            print(f"反馈文件: {args.feedback}")
        print()

        parking_data = collector.batch_load_data()
        if not parking_data:
            print("\n未找到任何数据文件，请先准备数据或使用 --generate-sample 生成示例数据")
            sys.exit(0)

        filtered_data = collector.filter_by_month()
        print()

        collector_summary = collector.get_collected_summary()
        print("数据采集概览:")
        print(collector_summary.to_string(index=False))
        print()

        validator = RuleValidator(config)
        anomalies_df = validator.validate_all(
            filtered_data, 
            stat_month.year, 
            stat_month.month
        )
        print()

        revenue_analyzer = RevenueAnalyzer(config)
        revenue_summary = revenue_analyzer.summarize_by_parking(filtered_data)
        type_comparison = revenue_analyzer.get_type_comparison(filtered_data)
        print()

        utilization_analyzer = ParkingUtilization(config)
        utilization_df = utilization_analyzer.get_combined_analysis(filtered_data)
        
        data_issues = utilization_analyzer.get_data_issues()
        if not data_issues.empty:
            print("数据质量问题:")
            print(data_issues.to_string(index=False))
            print()
            if anomalies_df is None or anomalies_df.empty:
                anomalies_df = data_issues
            else:
                anomalies_df = pd.concat([anomalies_df, data_issues], ignore_index=True)
        print()

        member_analyzer = MemberAnalyzer(config)
        member_summary = member_analyzer.analyze_members(filtered_data)
        ranking_df = member_analyzer.generate_ranking(filtered_data, revenue_summary)
        type_compare = member_analyzer.compare_parking_types(filtered_data, revenue_summary)
        print()

        total_revenue = revenue_summary['总收入'].sum() if not revenue_summary.empty else 0
        temp_revenue = revenue_summary['临停收入'].sum() if not revenue_summary.empty else 0
        monthly_revenue = revenue_summary['月卡收入'].sum() if not revenue_summary.empty else 0
        total_visits = revenue_summary['总车次'].sum() if not revenue_summary.empty else 0
        
        direct_count = len(revenue_summary[revenue_summary['车场类型'] == '直营']) if not revenue_summary.empty else 0
        entrusted_count = len(revenue_summary[revenue_summary['车场类型'] == '委托']) if not revenue_summary.empty else 0

        anomaly_count = len(anomalies_df) if anomalies_df is not None and not anomalies_df.empty else 0

        issue_tracker = IssueTracker(config)
        
        if anomalies_df is not None and not anomalies_df.empty:
            anomalies_df = issue_tracker.enrich_current_issues(anomalies_df, stat_month)
        
        feedback_errors = pd.DataFrame()
        if args.feedback or os.path.exists('./data/feedback'):
            print("加载处理反馈文件...")
            current_for_match = anomalies_df if anomalies_df is not None and not anomalies_df.empty else None
            matched_feedback, unmatched_feedback = issue_tracker.load_feedback_file(args.feedback, current_for_match)
            
            if not unmatched_feedback.empty:
                unmatched_feedback['错误原因'] = '问题ID不存在或不匹配'
                feedback_errors = unmatched_feedback
                print(f"  ⚠ 发现 {len(feedback_errors)} 条反馈无法匹配，已记录到反馈异常工作表")
            
            if not matched_feedback.empty:
                print(f"  ✓ 成功匹配 {len(matched_feedback)} 条处理反馈")
                anomalies_df = issue_tracker.merge_feedback_to_current(anomalies_df, matched_feedback)
            print()
        
        if anomalies_df is not None and not anomalies_df.empty:
            issue_tracker.update_issue_history(anomalies_df, stat_month)

        if anomaly_count == 0:
            print("✅ 本月无待处理异常")
            print()

        closed_loop_summary = issue_tracker.get_closed_loop_summary(anomalies_df, stat_month)
        
        results = {
            'parking_count': len(filtered_data),
            'direct_count': direct_count,
            'entrusted_count': entrusted_count,
            'total_revenue': total_revenue,
            'temp_revenue': temp_revenue,
            'monthly_revenue': monthly_revenue,
            'total_visits': total_visits,
            'anomaly_count': anomaly_count,
            'revenue_summary': revenue_summary,
            'type_comparison': type_compare,
            'utilization': utilization_df,
            'member_summary': member_summary,
            'ranking': ranking_df,
            'anomalies': anomalies_df if anomalies_df is not None else pd.DataFrame(),
            'closed_loop_summary': closed_loop_summary,
            'feedback_errors': feedback_errors
        }

        send_records_df = None
        preview_records_df = None
        notification_review_df = None
        
        if not args.review_only and args.send_mode != 'none':
            sender = NotificationSender(config)
            
            report_gen = ReportGenerator(config)
            todo_list, manager_todos = report_gen.generate_issue_list(anomalies_df)
            
            if anomalies_df is not None and not anomalies_df.empty:
                if '统计月份' not in anomalies_df.columns:
                    anomalies_df = anomalies_df.copy()
                    anomalies_df['统计月份'] = stat_month.strftime('%Y-%m')
            
            if args.send_mode == 'preview':
                preview_records_df, notification_review_df = sender.send_notifications(
                    manager_todos, anomalies_df, stat_month, 
                    send_mode='preview', target_managers=args.managers
                )
                results['preview_records'] = preview_records_df
                results['notification_review'] = notification_review_df
                sender.save_send_records(stat_month)
            else:
                send_records_df, notification_review_df = sender.send_notifications(
                    manager_todos, anomalies_df, stat_month, 
                    send_mode=args.send_mode, target_managers=args.managers
                )
                results['send_records'] = send_records_df if send_records_df is not None else pd.DataFrame()
                results['notification_review'] = notification_review_df
                sender.save_send_records(stat_month)
        else:
            if anomalies_df is not None and not anomalies_df.empty:
                anomalies_df_copy = anomalies_df.copy()
                anomalies_df_copy['统计月份'] = stat_month.strftime('%Y-%m')
            else:
                anomalies_df_copy = pd.DataFrame()
            
            sender = NotificationSender(config)
            notification_review_df = sender._generate_review_summary(
                anomalies_df_copy, pd.DataFrame(), args.managers, stat_month
            )
            results['notification_review'] = notification_review_df

        report_gen = ReportGenerator(config)
        output_path, version_path = report_gen.generate_report(
            filtered_data, results, stat_month
        )
        print()

        print("=" * 60)
        print("                    分析完成！")
        print("=" * 60)
        print(f"\n报告文件: {output_path}")
        print(f"历史版本: {version_path}")
        print(f"\n核心指标:")
        print(f"  - 车场总数: {len(filtered_data)} 个")
        print(f"  - 直营车场: {direct_count} 个")
        print(f"  - 委托车场: {entrusted_count} 个")
        print(f"  - 总收入: ¥{total_revenue:,.2f}")
        print(f"  - 总车次: {total_visits:,}")
        print(f"  - 发现异常: {anomaly_count} 项")
        
        if not feedback_errors.empty:
            print(f"  - 反馈异常: {len(feedback_errors)} 条")
        
        print()

        if anomalies_df is not None and not anomalies_df.empty:
            print("异常摘要:")
            if '问题来源' in anomalies_df.columns:
                source_summary = anomalies_df.groupby(['问题来源', '异常类型']).size().reset_index(name='数量')
                print(source_summary.to_string(index=False))
            else:
                anomaly_summary = validator.get_anomaly_summary()
                if not anomaly_summary.empty:
                    print(anomaly_summary.to_string(index=False))
            print()

        if send_records_df is not None and not send_records_df.empty:
            print("发送记录:")
            if '发送状态' in send_records_df.columns:
                send_summary = send_records_df.groupby('发送状态').size().reset_index(name='数量')
                print(send_summary.to_string(index=False))
            print()
        
        if preview_records_df is not None and not preview_records_df.empty:
            print(f"预览记录: 共 {len(preview_records_df)} 位负责人的消息已生成并保存到报告")
            print()

        print("闭环复盘摘要:")
        print(closed_loop_summary[['负责人', '本月新增问题数', '历史未关闭数', 
                                    '本月已关闭数', '复发问题数', '本月闭环率(%)']].to_string(index=False))
        print()

        print("报告包含以下工作表:")
        sheets = ['概览', '收入汇总', '车场排名', '直营vs委托', 
                  '车位利用', '会员分析', '异常清单', '待办事项', 
                  '负责人待办', '通知复盘', '闭环复盘']
        if send_records_df is not None and not send_records_df.empty:
            sheets.append('发送记录')
        if preview_records_df is not None and not preview_records_df.empty:
            sheets.append('消息预览')
        if not feedback_errors.empty:
            sheets.append('反馈异常')
        for sheet in sheets:
            print(f"  ✓ {sheet}")
        print()

    except Exception as e:
        print(f"\n❌ 程序运行出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    import os
    main()
