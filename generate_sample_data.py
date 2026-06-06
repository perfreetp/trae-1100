import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from utils.common import ensure_dir


def generate_parking_data(parking_name, parking_type, year, month, total_spots, manager):
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    days_in_month = (next_month - timedelta(days=1)).day
    
    dates = [datetime(year, month, day) for day in range(1, days_in_month + 1)]
    
    base_temp_revenue = 3000 + hash(parking_name) % 5000
    base_monthly_revenue = 8000 + hash(parking_name + 'm') % 10000
    base_visits = 150 + hash(parking_name + 'v') % 200
    base_free = 5 + hash(parking_name + 'f') % 15
    base_member = int(total_spots * 0.4) + hash(parking_name + 'mem') % int(total_spots * 0.3)
    
    data = []
    for date in dates:
        day_factor = 1.0
        if date.weekday() >= 5:
            day_factor = 1.2
        
        temp_revenue = max(0, np.random.normal(base_temp_revenue * day_factor, base_temp_revenue * 0.2))
        monthly_revenue = max(0, np.random.normal(base_monthly_revenue / days_in_month, 500))
        total_visits = max(10, int(np.random.normal(base_visits * day_factor, base_visits * 0.15)))
        free_pass = max(0, int(np.random.normal(base_free, base_free * 0.3)))
        duration = max(0.5, np.random.normal(2.5, 0.8))
        member_count = base_member + np.random.randint(-5, 10)
        
        if date.day == 15 and '异常' in parking_name:
            temp_revenue = temp_revenue * 0.4
        
        data.append({
            '日期': date,
            '临停收入': round(temp_revenue, 2),
            '月卡收入': round(monthly_revenue, 2),
            '总车次': total_visits,
            '免费放行': free_pass,
            '停车时长': round(duration, 2),
            '车位数量': total_spots,
            '会员数量': member_count,
            '负责人': manager
        })
    
    df = pd.DataFrame(data)
    
    if '缺失' in parking_name:
        drop_indices = np.random.choice(df.index, size=3, replace=False)
        df = df.drop(drop_indices).reset_index(drop=True)
    
    return df


def main():
    input_dir = ensure_dir('./data/input')
    
    year = 2025
    month = 5
    
    parkings = [
        ('中心广场直营停车场', '直营', 300, '张三'),
        ('万达广场委托车场', '委托', 500, '李四'),
        ('科技园A区直营', '直营', 200, '王五'),
        ('商业中心委托车场', '委托', 400, '赵六'),
        ('火车站直营停车场', '直营', 600, '钱七'),
        ('居民区委托-缺失日期', '委托', 150, '孙八'),
        ('商业街直营-收入异常', '直营', 250, '周九'),
    ]
    
    print("生成示例数据...")
    for parking_name, parking_type, spots, manager in parkings:
        df = generate_parking_data(parking_name, parking_type, year, month, spots, manager)
        filename = f"{parking_name}_{year}{month:02d}.xlsx"
        filepath = os.path.join(input_dir, filename)
        df.to_excel(filepath, index=False)
        print(f"  ✓ {filename}: {len(df)} 条记录")
    
    print(f"\n示例数据已生成到 {input_dir}")
    print(f"统计月份: {year}年{month}月")


if __name__ == '__main__':
    main()
