import sys
import argparse
from datetime import datetime
from utils.common import load_config
from modules.data_collector import DataCollector
from modules.rule_validator import RuleValidator
from modules.revenue_analyzer import RevenueAnalyzer
from modules.parking_utilization import ParkingUtilization
from modules.member_analyzer import MemberAnalyzer
from modules.report_generator import ReportGenerator
from modules.notification_sender import NotificationSender


def print_header():
    print("=" * 60)
    print("        智慧停车月度运营自动化工具 v1.1")
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
    args = parser.parse_args()

    print_header()
    config = load_config()

    if args.generate_sample:
        print("生成示例数据模式...")
        from generate_sample_data import main as generate_sample
        generate_sample()
        print("\n示例数据生成完成！请重新运行工具进行分析。")
        return

    collector = DataCollector(config)
    
    stat_month = collector.select_month(args.year, args.month)
    print(f"统计月份: {stat_month.strftime('%Y年%m月')}")
    print(f"发送模式: {args.send_mode}")
    print()

    parking_data = collector.batch_load_data()
    if not parking_data:
        print("\n未找到任何数据文件，请先准备数据或使用 --generate-sample 生成示例数据")
        sys.exit(1)

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
        if not anomalies_df.empty:
            anomalies_df = pd.concat([anomalies_df, data_issues], ignore_index=True)
        else:
            anomalies_df = data_issues
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

    results = {
        'parking_count': len(filtered_data),
        'direct_count': direct_count,
        'entrusted_count': entrusted_count,
        'total_revenue': total_revenue,
        'temp_revenue': temp_revenue,
        'monthly_revenue': monthly_revenue,
        'total_visits': total_visits,
        'anomaly_count': len(anomalies_df),
        'revenue_summary': revenue_summary,
        'type_comparison': type_compare,
        'utilization': utilization_df,
        'member_summary': member_summary,
        'ranking': ranking_df,
        'anomalies': anomalies_df
    }

    report_gen = ReportGenerator(config)
    
    send_records_df = None
    if args.send_mode != 'none' and not anomalies_df.empty:
        sender = NotificationSender(config)
        
        todo_list, manager_todos = report_gen.generate_issue_list(anomalies_df)
        
        if args.send_mode == 'preview':
            sender.send_notifications(manager_todos, anomalies_df, stat_month, send_mode='preview')
        elif args.send_mode == 'simulate':
            send_records_df = sender.send_notifications(manager_todos, anomalies_df, stat_month, send_mode='simulate')
            send_records_df = sender.save_send_records(stat_month)
        elif args.send_mode == 'real':
            send_records_df = sender.send_notifications(manager_todos, anomalies_df, stat_month, send_mode='real')
            send_records_df = sender.save_send_records(stat_month)
        
        results['send_records'] = send_records_df if send_records_df is not None else pd.DataFrame()
    
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
    print(f"  - 发现异常: {len(anomalies_df)} 项")
    print()

    if not anomalies_df.empty:
        print("异常摘要:")
        anomaly_summary = validator.get_anomaly_summary()
        print(anomaly_summary.to_string(index=False))
        print()

    if send_records_df is not None and not send_records_df.empty:
        print("发送记录:")
        send_summary = send_records_df.groupby('发送状态').size().reset_index(name='数量')
        print(send_summary.to_string(index=False))
        print()

    print("报告包含以下工作表:")
    sheets = ['概览', '收入汇总', '车场排名', '直营vs委托', 
              '车位利用', '会员分析', '异常清单', '待办事项', '负责人待办']
    if send_records_df is not None and not send_records_df.empty:
        sheets.append('发送记录')
    for sheet in sheets:
        print(f"  ✓ {sheet}")
    print()


if __name__ == '__main__':
    import pandas as pd
    main()
