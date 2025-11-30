#!/usr/bin/env python3
"""
贪心放电策略优化模型
按照RRP从高到低排序进行储能放电
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("="*80)
print("贪心放电策略优化模型（按RRP排序放电）")
print("="*80)

# ==================== 配置参数 ====================
class OptimizationConfig:
    """优化模型配置参数"""
    
    # 电网限制
    NEL = 4440.0  # kW - 对电网最大输出功率
    NIL = 670.0   # kW - 从电网最大输入功率
    
    # 电池参数
    BATTERY_CAPACITY = 5504.0  # kWh - 电池储能总量
    BATTERY_MAX_CHARGE_POWER = 2752.0  # kW - 电池最大充电功率
    BATTERY_MAX_DISCHARGE_POWER = 2752.0  # kW - 电池最大放电功率
    
    # 效率
    CHARGE_EFFICIENCY = 0.95   # 充电效率
    DISCHARGE_EFFICIENCY = 0.95  # 放电效率
    
    # 价格限制
    LGC = -10.0  # AUD/MWh - 对电网放电的最低价格
    
    # POA阈值
    POA_CHARGE_THRESHOLD = 10.0  # POA > 10 才能充电
    POA_DAYTIME_THRESHOLD = 5.0  # POA > 5 认为是白天
    
    # 时间参数
    INTERVAL_MINUTES = 5  # 数据间隔（分钟）
    INTERVAL_HOURS = INTERVAL_MINUTES / 60.0  # 数据间隔（小时）
    
    def print_config(self):
        """打印配置信息"""
        print("\n配置参数:")
        print(f"  电网输出限制(NEL): {self.NEL} kW")
        print(f"  电网输入限制(NIL): {self.NIL} kW")
        print(f"  电池容量: {self.BATTERY_CAPACITY} kWh")
        print(f"  电池充电功率: {self.BATTERY_MAX_CHARGE_POWER} kW")
        print(f"  电池放电功率: {self.BATTERY_MAX_DISCHARGE_POWER} kW")
        print(f"  充电效率: {self.CHARGE_EFFICIENCY * 100}%")
        print(f"  放电效率: {self.DISCHARGE_EFFICIENCY * 100}%")
        print(f"  LGC限制: {self.LGC} AUD/MWh")
        print(f"  POA充电阈值: {self.POA_CHARGE_THRESHOLD} W/m²")
        print(f"  POA白天阈值: {self.POA_DAYTIME_THRESHOLD} W/m²")

config = OptimizationConfig()
config.print_config()

# ==================== 加载Excel数据 ====================
print("\n" + "="*80)
print("加载Excel数据")
print("="*80)

excel_file = 'excel_1117.csv'

if not os.path.exists(excel_file):
    print(f"\n错误: 找不到文件 {excel_file}")
    exit(1)

print(f"\n加载文件: {excel_file}")
df = pd.read_csv(excel_file)

# 重命名列
df.columns = df.columns.str.strip()

# 转换时间
df['Timestamp'] = pd.to_datetime(df['日期'])
df = df.sort_values('Timestamp').reset_index(drop=True)

# 转换电价
if df['电价RRP'].mean() < 1:
    df['RRP_MWh'] = df['电价RRP'] * 1000
else:
    df['RRP_MWh'] = df['电价RRP']

# 使用Excel中的光伏发电量
df['PV_Energy_kWh'] = df['光伏发电量']
df['PV_Power_kW'] = df['PV功率']

# 添加日期列
df['Date'] = df['Timestamp'].dt.date
df['Date_Str'] = df['Date'].astype(str)

# POA标识
df['Can_Charge'] = df['POA'] > config.POA_CHARGE_THRESHOLD
df['Is_Daytime'] = df['POA'] > config.POA_DAYTIME_THRESHOLD

print(f"\n数据信息:")
print(f"  数据行数: {len(df):,}")
print(f"  时间范围: {df['Timestamp'].min()} 到 {df['Timestamp'].max()}")
print(f"  覆盖天数: {df['Date_Str'].nunique()}")
print(f"  POA范围: {df['POA'].min():.2f} - {df['POA'].max():.2f} W/m²")
print(f"  RRP范围($/MWh): ${df['RRP_MWh'].min():.2f} - ${df['RRP_MWh'].max():.2f}")
print(f"  总光伏发电量: {df['PV_Energy_kWh'].sum():,.2f} kWh")

# ==================== 定义充电逻辑 ====================
def charge_battery(day_data, soc_start):
    """
    白天充电逻辑：在POA>10的时段，选择最低RRP时段充电
    """
    chargeable = day_data[day_data['Can_Charge']].copy()
    
    if len(chargeable) == 0:
        return pd.DataFrame(), soc_start
    
    # 按RRP从低到高排序（低价充电）
    chargeable = chargeable.sort_values('RRP_MWh').reset_index()
    
    soc = soc_start
    charge_results = []
    
    for idx in range(len(chargeable)):
        row = chargeable.iloc[idx]
        original_idx = row['index']
        
        if soc >= config.BATTERY_CAPACITY:
            # 已充满
            charge_results.append({
                'index': original_idx,
                'Charge_PV_kWh': 0,
                'Charge_Grid_kWh': 0,
                'SOC_kWh': soc,
                'Action': 'Battery_Full'
            })
            continue
        
        # 计算可充电量
        available_capacity = config.BATTERY_CAPACITY - soc
        max_charge_energy = config.BATTERY_MAX_CHARGE_POWER * config.INTERVAL_HOURS
        
        # 优先使用光伏充电
        pv_available = row['PV_Energy_kWh']
        charge_from_pv = min(pv_available, max_charge_energy, available_capacity / config.CHARGE_EFFICIENCY)
        
        # 如果还有容量，从电网充电
        remaining_charge_power = max_charge_energy - charge_from_pv
        remaining_capacity = available_capacity - charge_from_pv * config.CHARGE_EFFICIENCY
        
        charge_from_grid = 0
        if remaining_capacity > 0.01 and remaining_charge_power > 0.01:
            max_grid_charge = config.NIL * config.INTERVAL_HOURS
            charge_from_grid = min(max_grid_charge, remaining_charge_power, 
                                  remaining_capacity / config.CHARGE_EFFICIENCY)
        
        # 更新SOC
        total_charge = charge_from_pv + charge_from_grid
        soc += total_charge * config.CHARGE_EFFICIENCY
        
        charge_results.append({
            'index': original_idx,
            'Charge_PV_kWh': charge_from_pv,
            'Charge_Grid_kWh': charge_from_grid,
            'SOC_kWh': soc,
            'Action': 'Charging'
        })
        
        if soc >= config.BATTERY_CAPACITY * 0.999:
            # 充满了，后续时段不充电
            for remaining_idx in range(idx + 1, len(chargeable)):
                remaining_row = chargeable.iloc[remaining_idx]
                charge_results.append({
                    'index': remaining_row['index'],
                    'Charge_PV_kWh': 0,
                    'Charge_Grid_kWh': 0,
                    'SOC_kWh': soc,
                    'Action': 'Battery_Full'
                })
            break
    
    charge_df = pd.DataFrame(charge_results)
    return charge_df, soc

# ==================== 定义放电逻辑（贪心策略） ====================
def discharge_battery_greedy(day_data, next_day_data, soc_start):
    """
    贪心放电逻辑：
    1. 从当天POA>5到次日POA>5，按RRP从高到低排序
    2. 优先在最高RRP时段放电
    3. 如果POA>5且光伏功率>=NEL，则只用光伏发电
    4. 如果POA>5且光伏功率<NEL，则光伏+储能一起发电至NEL
    5. 如果POA<=5，则按最大放电功率放电
    """
    # 合并当天和次日数据，找到POA>5的范围
    combined = pd.concat([day_data, next_day_data], ignore_index=False)
    
    # 找到第一个POA>5和最后一个POA>5的时刻
    daytime_mask = combined['Is_Daytime']
    if daytime_mask.sum() == 0:
        return pd.DataFrame(), soc_start
    
    first_daytime_idx = combined[daytime_mask].index[0]
    last_daytime_idx = combined[daytime_mask].index[-1]
    
    # 提取这段时间的数据
    discharge_window = combined.loc[first_daytime_idx:last_daytime_idx].copy()
    
    # 只对当天的数据进行放电（次日数据只用于定义窗口）
    day_indices = day_data.index
    discharge_candidates = discharge_window[discharge_window.index.isin(day_indices)].copy()
    
    if len(discharge_candidates) == 0:
        return pd.DataFrame(), soc_start
    
    # 按RRP从高到低排序（高价放电）
    discharge_candidates = discharge_candidates.sort_values('RRP_MWh', ascending=False).reset_index()
    
    soc = soc_start
    discharge_results = []
    
    for idx in range(len(discharge_candidates)):
        row = discharge_candidates.iloc[idx]
        original_idx = row['index']
        
        if soc <= 0.01:
            # 电池已空
            discharge_results.append({
                'index': original_idx,
                'Discharge_kWh': 0,
                'Export_PV_kWh': 0,
                'Export_Battery_kWh': 0,
                'SOC_kWh': 0,
                'Action': 'Battery_Empty'
            })
            continue
        
        rrp = row['RRP_MWh']
        pv_power = row['PV_Power_kW']
        is_daytime = row['Is_Daytime']
        
        # 检查是否低于LGC限制
        if rrp <= config.LGC:
            discharge_results.append({
                'index': original_idx,
                'Discharge_kWh': 0,
                'Export_PV_kWh': 0,
                'Export_Battery_kWh': 0,
                'SOC_kWh': soc,
                'Action': 'Price_Too_Low'
            })
            continue
        
        discharge_energy = 0
        export_pv = 0
        
        if is_daytime:
            # 白天：POA > 5
            if pv_power >= config.NEL:
                # 光伏功率足够，只用光伏
                export_pv = config.NEL * config.INTERVAL_HOURS
                discharge_energy = 0
                action = 'PV_Only'
            else:
                # 光伏不足，储能补充至NEL
                export_pv = pv_power * config.INTERVAL_HOURS
                
                # 计算储能需要补充的功率
                needed_power = config.NEL - pv_power
                max_discharge_power = min(config.BATTERY_MAX_DISCHARGE_POWER, needed_power)
                
                # 计算实际放电量（考虑SOC限制）
                max_discharge_energy = max_discharge_power * config.INTERVAL_HOURS
                available_discharge = soc * config.DISCHARGE_EFFICIENCY  # 可放出的能量
                
                discharge_energy = min(max_discharge_energy, available_discharge / config.DISCHARGE_EFFICIENCY)
                action = 'PV_Battery_Mix'
        else:
            # 夜间：POA <= 5，按最大功率放电
            max_discharge_energy = config.BATTERY_MAX_DISCHARGE_POWER * config.INTERVAL_HOURS
            available_discharge = soc * config.DISCHARGE_EFFICIENCY
            
            discharge_energy = min(max_discharge_energy, available_discharge / config.DISCHARGE_EFFICIENCY)
            export_pv = 0
            action = 'Battery_Only'
        
        # 更新SOC
        soc -= discharge_energy / config.DISCHARGE_EFFICIENCY
        soc = max(0, soc)
        
        export_battery = discharge_energy * config.DISCHARGE_EFFICIENCY
        
        discharge_results.append({
            'index': original_idx,
            'Discharge_kWh': discharge_energy,
            'Export_PV_kWh': export_pv,
            'Export_Battery_kWh': export_battery,
            'SOC_kWh': soc,
            'Action': action
        })
        
        if soc <= 0.01:
            # 电池已空，后续时段不放电
            for remaining_idx in range(idx + 1, len(discharge_candidates)):
                remaining_row = discharge_candidates.iloc[remaining_idx]
                discharge_results.append({
                    'index': remaining_row['index'],
                    'Discharge_kWh': 0,
                    'Export_PV_kWh': 0,
                    'Export_Battery_kWh': 0,
                    'SOC_kWh': 0,
                    'Action': 'Battery_Empty'
                })
            break
    
    discharge_df = pd.DataFrame(discharge_results)
    return discharge_df, soc

# ==================== 运行优化 ====================
print("\n" + "="*80)
print("运行贪心放电策略优化")
print("="*80)

results = []
dates = sorted(df['Date_Str'].unique())

# 初始SOC
soc = config.BATTERY_CAPACITY * 0.5  # 从50%开始

for day_idx, date in enumerate(dates):
    print(f"\n处理 {date} ({day_idx+1}/{len(dates)})...")
    
    # 当天数据
    day_data = df[df['Date_Str'] == date].copy()
    
    # 次日数据（用于定义放电窗口）
    if day_idx + 1 < len(dates):
        next_date = dates[day_idx + 1]
        next_day_data = df[df['Date_Str'] == next_date].copy()
    else:
        next_day_data = pd.DataFrame()
    
    # 第1步：充电阶段（POA>10的低价时段）
    charge_df, soc_after_charge = charge_battery(day_data, soc)
    
    # 第2步：放电阶段（按RRP排序贪心放电）
    discharge_df, soc_after_discharge = discharge_battery_greedy(
        day_data, next_day_data, soc_after_charge
    )
    
    # 合并充电和放电结果
    for idx, row in day_data.iterrows():
        result = {
            'Timestamp': row['Timestamp'],
            'Date': row['Date_Str'],
            'RRP_MWh': row['RRP_MWh'],
            'POA': row['POA'],
            'PV_Power_kW': row['PV_Power_kW'],
            'PV_Energy_kWh': row['PV_Energy_kWh'],
            'Charge_PV_kWh': 0,
            'Charge_Grid_kWh': 0,
            'Discharge_kWh': 0,
            'Export_PV_kWh': 0,
            'Export_Battery_kWh': 0,
            'Curtail_kWh': 0,
            'SOC_kWh': soc,
            'Action': 'Idle'
        }
        
        # 查找充电记录
        if len(charge_df) > 0 and idx in charge_df['index'].values:
            charge_row = charge_df[charge_df['index'] == idx].iloc[0]
            result['Charge_PV_kWh'] = charge_row['Charge_PV_kWh']
            result['Charge_Grid_kWh'] = charge_row['Charge_Grid_kWh']
            result['SOC_kWh'] = charge_row['SOC_kWh']
            result['Action'] = charge_row['Action']
            
            # 剩余光伏直接上网或弃电
            remaining_pv = row['PV_Energy_kWh'] - charge_row['Charge_PV_kWh']
            if row['RRP_MWh'] > config.LGC:
                result['Export_PV_kWh'] = min(remaining_pv, config.NEL * config.INTERVAL_HOURS)
                result['Curtail_kWh'] = max(0, remaining_pv - config.NEL * config.INTERVAL_HOURS)
            else:
                result['Curtail_kWh'] = remaining_pv
        
        # 查找放电记录
        if len(discharge_df) > 0 and idx in discharge_df['index'].values:
            discharge_row = discharge_df[discharge_df['index'] == idx].iloc[0]
            result['Discharge_kWh'] = discharge_row['Discharge_kWh']
            result['Export_PV_kWh'] = discharge_row['Export_PV_kWh']
            result['Export_Battery_kWh'] = discharge_row['Export_Battery_kWh']
            result['SOC_kWh'] = discharge_row['SOC_kWh']
            result['Action'] = discharge_row['Action']
            
            # 计算未使用的光伏
            used_pv = discharge_row['Export_PV_kWh']
            remaining_pv = row['PV_Energy_kWh'] - used_pv
            if remaining_pv > 0:
                if row['RRP_MWh'] > config.LGC:
                    result['Curtail_kWh'] = remaining_pv  # 已达到NEL限制，只能弃电
                else:
                    result['Curtail_kWh'] = remaining_pv
        
        # 如果既不充电也不放电，处理光伏
        if result['Action'] == 'Idle':
            if row['RRP_MWh'] > config.LGC:
                result['Export_PV_kWh'] = min(row['PV_Energy_kWh'], config.NEL * config.INTERVAL_HOURS)
                result['Curtail_kWh'] = max(0, row['PV_Energy_kWh'] - config.NEL * config.INTERVAL_HOURS)
            else:
                result['Curtail_kWh'] = row['PV_Energy_kWh']
        
        results.append(result)
    
    # 更新SOC到下一天
    soc = soc_after_discharge
    print(f"  日终SOC: {soc:.2f} kWh ({soc/config.BATTERY_CAPACITY*100:.1f}%)")

# ==================== 计算结果 ====================
print("\n" + "="*80)
print("计算收益")
print("="*80)

results_df = pd.DataFrame(results)

# 计算收益
results_df['Export_Revenue'] = (
    (results_df['Export_PV_kWh'] + results_df['Export_Battery_kWh']) 
    * results_df['RRP_MWh'] / 1000.0
)
results_df['Charge_Cost'] = results_df['Charge_Grid_kWh'] * results_df['RRP_MWh'] / 1000.0
results_df['Net_Revenue'] = results_df['Export_Revenue'] - results_df['Charge_Cost']
results_df['SOC_Percent'] = results_df['SOC_kWh'] / config.BATTERY_CAPACITY * 100

# ==================== 统计分析 ====================
print("\n收益统计:")
print("-"*80)

total_revenue = results_df['Net_Revenue'].sum()
total_export_revenue = results_df['Export_Revenue'].sum()
total_charge_cost = results_df['Charge_Cost'].sum()

print(f"累计净收益: ${total_revenue:,.2f}")
print(f"  上网收益: ${total_export_revenue:,.2f}")
print(f"  购电成本: ${total_charge_cost:,.2f}")

print("\n能量统计:")
print("-"*80)

total_pv = results_df['PV_Energy_kWh'].sum()
total_charge_pv = results_df['Charge_PV_kWh'].sum()
total_charge_grid = results_df['Charge_Grid_kWh'].sum()
total_charge = total_charge_pv + total_charge_grid
total_discharge = results_df['Discharge_kWh'].sum()
total_export_pv = results_df['Export_PV_kWh'].sum()
total_export_battery = results_df['Export_Battery_kWh'].sum()
total_export = total_export_pv + total_export_battery
total_curtail = results_df['Curtail_kWh'].sum()

print(f"光伏总发电: {total_pv:,.2f} kWh")
print(f"  用于充电: {total_charge_pv:,.2f} kWh ({total_charge_pv/total_pv*100:.1f}%)")
print(f"  直接上网: {total_export_pv:,.2f} kWh ({total_export_pv/total_pv*100:.1f}%)")
print(f"  弃电: {total_curtail:,.2f} kWh ({total_curtail/total_pv*100:.1f}%)")

print(f"\n从电网购电: {total_charge_grid:,.2f} kWh")
print(f"总充电量: {total_charge:,.2f} kWh")
print(f"总放电量: {total_discharge:,.2f} kWh")
print(f"储能上网: {total_export_battery:,.2f} kWh")
print(f"总上网量: {total_export:,.2f} kWh")

# 动作统计
print("\n动作统计:")
print("-"*80)
action_counts = results_df['Action'].value_counts()
for action, count in action_counts.items():
    print(f"  {action}: {count} 时段 ({count/len(results_df)*100:.1f}%)")

# ==================== 每日汇总 ====================
print("\n每日统计:")
print("-"*80)

daily = results_df.groupby('Date').agg({
    'Net_Revenue': 'sum',
    'Export_Revenue': 'sum',
    'Charge_Cost': 'sum',
    'PV_Energy_kWh': 'sum',
    'Charge_PV_kWh': 'sum',
    'Charge_Grid_kWh': 'sum',
    'Discharge_kWh': 'sum',
    'Export_Battery_kWh': 'sum',
    'Curtail_kWh': 'sum',
    'SOC_kWh': 'last'
}).reset_index()

daily.columns = [
    'Date', 'Net_Revenue', 'Export_Revenue', 'Charge_Cost',
    'PV_Total', 'Charge_PV', 'Charge_Grid', 'Discharge', 
    'Export_Battery', 'Curtail', 'End_SOC_kWh'
]

daily['End_SOC_Percent'] = daily['End_SOC_kWh'] / config.BATTERY_CAPACITY * 100

print(f"覆盖天数: {len(daily)}")
print(f"平均日收益: ${daily['Net_Revenue'].mean():,.2f}")
print(f"最高日收益: ${daily['Net_Revenue'].max():,.2f} ({daily.loc[daily['Net_Revenue'].idxmax(), 'Date']})")
print(f"最低日收益: ${daily['Net_Revenue'].min():,.2f} ({daily.loc[daily['Net_Revenue'].idxmin(), 'Date']})")

annual_estimate = (total_revenue / len(daily)) * 365
print(f"\n年化估算: ${annual_estimate:,.2f}/年")

# ==================== 保存结果 ====================
print("\n" + "="*80)
print("保存结果")
print("="*80)

output_folder = 'optimization_results_greedy_discharge'
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# 保存详细结果
detail_file = f'{output_folder}/detailed_results.csv'
results_df.to_csv(detail_file, index=False, encoding='utf-8-sig')
print(f"\n[1] {detail_file} ({len(results_df):,} 行)")

# 保存每日汇总
daily_file = f'{output_folder}/daily_summary.csv'
daily.to_csv(daily_file, index=False, encoding='utf-8-sig')
print(f"[2] {daily_file} ({len(daily)} 天)")

# Excel格式
excel_file = f'{output_folder}/optimization_results_贪心放电.xlsx'
with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
    results_df.to_excel(writer, sheet_name='详细数据', index=False)
    daily.to_excel(writer, sheet_name='每日汇总', index=False)
    
    # 汇总统计
    summary = pd.DataFrame({
        '指标': [
            '累计净收益',
            '平均日收益',
            '年化估算',
            '总光伏发电',
            '光伏用于充电',
            '光伏直接上网',
            '光伏弃电',
            '从电网购电',
            '总充电量',
            '总放电量',
            '储能上网',
            '总上网量'
        ],
        '数值': [
            f"${total_revenue:,.2f}",
            f"${daily['Net_Revenue'].mean():,.2f}",
            f"${annual_estimate:,.2f}",
            f"{total_pv:,.2f} kWh",
            f"{total_charge_pv:,.2f} kWh ({total_charge_pv/total_pv*100:.1f}%)",
            f"{total_export_pv:,.2f} kWh ({total_export_pv/total_pv*100:.1f}%)",
            f"{total_curtail:,.2f} kWh ({total_curtail/total_pv*100:.1f}%)",
            f"{total_charge_grid:,.2f} kWh",
            f"{total_charge:,.2f} kWh",
            f"{total_discharge:,.2f} kWh",
            f"{total_export_battery:,.2f} kWh",
            f"{total_export:,.2f} kWh"
        ]
    })
    summary.to_excel(writer, sheet_name='汇总统计', index=False)

print(f"[3] {excel_file} (3个工作表)")

print("\n" + "="*80)
print("优化完成！")
print("="*80)
print(f"\n关键指标:")
print(f"  累计净收益: ${total_revenue:,.2f}")
print(f"  平均日收益: ${daily['Net_Revenue'].mean():,.2f}")
print(f"  年化估算: ${annual_estimate:,.2f}")
print(f"  储能利用率: {total_discharge/total_charge*100:.2f}%" if total_charge > 0 else "  储能利用率: N/A")
print(f"  弃电率: {total_curtail/total_pv*100:.1f}%")
print("\n" + "="*80)

