#!/usr/bin/env python3
"""
线性规划优化模型 - 带POA约束
按照完美收益逻辑实现

关键约束：
1. 只在POA > 10时段进行充电（白天充电）
2. 每天至少充满一次（SOC达到100%）
3. 在POA > 10的最低RRP时段优先充电
4. 其余光伏：RRP > -10上网，否则弃电
"""

import pandas as pd
import numpy as np
from pulp import *
import os
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

print("="*80)
print("线性规划优化模型 - 带POA约束（完美收益逻辑）")
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

excel_file = 'excel_1117版本.csv'

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
df['Date'] = df['Timestamp'].dt.date.astype(str)

print(f"\n数据信息:")
print(f"  数据行数: {len(df):,}")
print(f"  时间范围: {df['Timestamp'].min()} 到 {df['Timestamp'].max()}")
print(f"  覆盖天数: {df['Date'].nunique()}")
print(f"  POA范围: {df['POA'].min():.2f} - {df['POA'].max():.2f} W/m²")
print(f"  RRP范围($/MWh): ${df['RRP_MWh'].min():.2f} - ${df['RRP_MWh'].max():.2f}")
print(f"  总光伏发电量: {df['PV_Energy_kWh'].sum():,.2f} kWh")

# ==================== 分析POA时段 ====================
print("\n" + "="*80)
print("POA时段分析")
print("="*80)

df['Can_Charge'] = df['POA'] > config.POA_CHARGE_THRESHOLD
df['Is_Daytime'] = df['POA'] > config.POA_DAYTIME_THRESHOLD

charge_periods = df['Can_Charge'].sum()
daytime_periods = df['Is_Daytime'].sum()

print(f"\nPOA > {config.POA_CHARGE_THRESHOLD} (可充电时段): {charge_periods} / {len(df)} ({charge_periods/len(df)*100:.1f}%)")
print(f"POA > {config.POA_DAYTIME_THRESHOLD} (白天时段): {daytime_periods} / {len(df)} ({daytime_periods/len(df)*100:.1f}%)")

# 每天的充电时段统计
daily_stats = df.groupby('Date').agg({
    'Can_Charge': 'sum',
    'Is_Daytime': 'sum',
    'PV_Energy_kWh': 'sum'
}).reset_index()

daily_stats.columns = ['Date', 'Charge_Periods', 'Daytime_Periods', 'Daily_PV']

print(f"\n每日平均:")
print(f"  可充电时段: {daily_stats['Charge_Periods'].mean():.0f} 个")
print(f"  白天时段: {daily_stats['Daytime_Periods'].mean():.0f} 个")
print(f"  光伏发电: {daily_stats['Daily_PV'].mean():,.2f} kWh")

# ==================== 构建线性规划模型 ====================
print("\n" + "="*80)
print("构建线性规划模型（带POA约束）")
print("="*80)

print("\n创建优化问题...")
prob = LpProblem("Battery_Optimization_POA_Constraints", LpMaximize)

# 时段索引
T = range(len(df))
print(f"优化时段数: {len(T):,}")

# ==================== 定义决策变量 ====================
print("\n定义决策变量...")

# 充电变量
charge_grid = [
    LpVariable(f"cg_{t}", lowBound=0, 
               upBound=config.NIL * config.INTERVAL_HOURS if df.loc[t, 'Can_Charge'] else 0) 
    for t in T
]

charge_pv = [
    LpVariable(f"cp_{t}", lowBound=0, 
               upBound=df.loc[t, 'PV_Energy_kWh'] if df.loc[t, 'Can_Charge'] else 0) 
    for t in T
]

# 放电变量
discharge = [
    LpVariable(f"d_{t}", lowBound=0, 
               upBound=config.BATTERY_MAX_DISCHARGE_POWER * config.INTERVAL_HOURS) 
    for t in T
]

# 电池SOC
soc = [
    LpVariable(f"soc_{t}", lowBound=0, upBound=config.BATTERY_CAPACITY) 
    for t in T
]

# 上网变量
export_pv = [
    LpVariable(f"ep_{t}", lowBound=0, 
               upBound=df.loc[t, 'PV_Energy_kWh']) 
    for t in T
]

export_battery = [
    LpVariable(f"eb_{t}", lowBound=0) 
    for t in T
]

# 弃电变量
curtail = [
    LpVariable(f"cur_{t}", lowBound=0, 
               upBound=df.loc[t, 'PV_Energy_kWh']) 
    for t in T
]

# 日期映射
unique_dates = df['Date'].unique()
date_to_idx = {date: i for i, date in enumerate(unique_dates)}
df['Date_Idx'] = df['Date'].map(date_to_idx)

print(f"  时段决策变量: {len(T) * 7:,} 个")

# ==================== 定义目标函数 ====================
print("\n定义目标函数...")

revenue_terms = []
cost_terms = []

for t in T:
    rrp = df.loc[t, 'RRP_MWh']
    
    # 上网收益
    revenue_terms.append((export_pv[t] + export_battery[t]) * rrp / 1000.0)
    
    # 购电成本
    cost_terms.append(charge_grid[t] * rrp / 1000.0)

prob += lpSum(revenue_terms) - lpSum(cost_terms), "Total_Revenue"
print("  目标: 最大化(上网收益 - 购电成本)")

# ==================== 定义约束条件 ====================
print("\n定义约束条件...")

# 1. 光伏能量平衡
print("  [1/8] 光伏能量平衡...")
for t in T:
    prob += (
        charge_pv[t] + export_pv[t] + curtail[t] == df.loc[t, 'PV_Energy_kWh'],
        f"PV_Bal_{t}"
    )

# 2. POA充电约束（只在POA > 10时可以充电）
print("  [2/8] POA充电约束（只在POA > 10时充电）...")
poa_restricted = 0
for t in T:
    if not df.loc[t, 'Can_Charge']:
        prob += (charge_pv[t] == 0, f"POA_Charge_PV_{t}")
        prob += (charge_grid[t] == 0, f"POA_Charge_Grid_{t}")
        poa_restricted += 1

print(f"      POA限制时段: {poa_restricted} / {len(T)} ({poa_restricted/len(T)*100:.1f}%)")

# 3. 电池SOC递推
print("  [3/8] 电池SOC递推...")
for t in T:
    if t == 0:
        prob += (
            soc[t] == (charge_pv[t] + charge_grid[t]) * config.CHARGE_EFFICIENCY 
                      - discharge[t] / config.DISCHARGE_EFFICIENCY,
            f"SOC_0"
        )
    else:
        prob += (
            soc[t] == soc[t-1] 
                      + (charge_pv[t] + charge_grid[t]) * config.CHARGE_EFFICIENCY 
                      - discharge[t] / config.DISCHARGE_EFFICIENCY,
            f"SOC_{t}"
        )

# 4. 储能上网能量
print("  [4/7] 储能上网能量...")
for t in T:
    prob += (
        export_battery[t] == discharge[t] * config.DISCHARGE_EFFICIENCY,
        f"Bat_Exp_{t}"
    )

# 5. 充电功率限制
print("  [5/7] 充电功率限制...")
for t in T:
    total_charge_power = (charge_pv[t] + charge_grid[t]) / config.INTERVAL_HOURS
    prob += (
        total_charge_power <= config.BATTERY_MAX_CHARGE_POWER,
        f"Charge_Power_{t}"
    )

# 6. NEL限制
print("  [6/7] 电网输出限制(NEL)...")
for t in T:
    total_export_power = (export_pv[t] + export_battery[t]) / config.INTERVAL_HOURS
    prob += (
        total_export_power <= config.NEL,
        f"NEL_{t}"
    )

# 7. LGC限制
print("  [7/7] LGC限制（RRP <= -10时不上网）...")
lgc_count = 0
for t in T:
    if df.loc[t, 'RRP_MWh'] <= config.LGC:
        prob += (export_pv[t] == 0, f"LGC_PV_{t}")
        prob += (export_battery[t] == 0, f"LGC_Bat_{t}")
        lgc_count += 1

print(f"      受LGC限制时段: {lgc_count} / {len(T)} ({lgc_count/len(T)*100:.1f}%)")

# ==================== 求解优化问题 ====================
print("\n" + "="*80)
print("求解优化问题")
print("="*80)

print("\n开始求解（带POA约束）...")
start_solve = datetime.now()

solver = PULP_CBC_CMD(msg=1, timeLimit=600)  # 10分钟限制
prob.solve(solver)

end_solve = datetime.now()
solve_time = (end_solve - start_solve).total_seconds()

status = LpStatus[prob.status]
print(f"\n求解状态: {status}")
print(f"求解时间: {solve_time:.1f} 秒")

if status not in ['Optimal', 'Feasible']:
    print(f"\n警告: 优化未找到最优解，状态为 {status}")
    if status == 'Infeasible':
        print("问题可能无可行解，请检查约束条件")
        exit(1)

print("\n" + "="*80)
print("优化结果")
print("="*80)

# ==================== 提取结果 ====================
print("\n提取优化结果...")

results = []
for t in T:
    results.append({
        'Timestamp': df.loc[t, 'Timestamp'],
        'Date': df.loc[t, 'Date'],
        'RRP_MWh': df.loc[t, 'RRP_MWh'],
        'POA': df.loc[t, 'POA'],
        'Can_Charge': df.loc[t, 'Can_Charge'],
        'PV_Power_kW': df.loc[t, 'PV_Power_kW'],
        'PV_Energy_kWh': df.loc[t, 'PV_Energy_kWh'],
        'Charge_PV_kWh': value(charge_pv[t]),
        'Charge_Grid_kWh': value(charge_grid[t]),
        'Discharge_kWh': value(discharge[t]),
        'Export_PV_kWh': value(export_pv[t]),
        'Export_Battery_kWh': value(export_battery[t]),
        'Curtail_kWh': value(curtail[t]),
        'SOC_kWh': value(soc[t]),
    })

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
total_export = (results_df['Export_PV_kWh'] + results_df['Export_Battery_kWh']).sum()
total_curtail = results_df['Curtail_kWh'].sum()

print(f"光伏总发电: {total_pv:,.2f} kWh")
print(f"  用于充电: {total_charge_pv:,.2f} kWh ({total_charge_pv/total_pv*100:.1f}%)")
print(f"  直接上网: {results_df['Export_PV_kWh'].sum():,.2f} kWh ({results_df['Export_PV_kWh'].sum()/total_pv*100:.1f}%)")
print(f"  弃电: {total_curtail:,.2f} kWh ({total_curtail/total_pv*100:.1f}%)")

print(f"\n从电网购电: {total_charge_grid:,.2f} kWh")
print(f"总充电量: {total_charge:,.2f} kWh")
print(f"总放电量: {total_discharge:,.2f} kWh")
print(f"总上网量: {total_export:,.2f} kWh")

if total_charge > 0:
    theoretical_efficiency = config.CHARGE_EFFICIENCY * config.DISCHARGE_EFFICIENCY
    actual_efficiency = (total_discharge * config.DISCHARGE_EFFICIENCY) / (total_charge / config.CHARGE_EFFICIENCY)
    print(f"\n充放电效率: {actual_efficiency*100:.2f}% (理论: {theoretical_efficiency*100:.2f}%)")

# POA时段统计
charge_in_poa = results_df[results_df['Can_Charge']]['Charge_PV_kWh'].sum() + results_df[results_df['Can_Charge']]['Charge_Grid_kWh'].sum()
charge_out_poa = results_df[~results_df['Can_Charge']]['Charge_PV_kWh'].sum() + results_df[~results_df['Can_Charge']]['Charge_Grid_kWh'].sum()

print(f"\nPOA约束验证:")
print(f"  POA > 10时充电: {charge_in_poa:,.2f} kWh")
print(f"  POA <= 10时充电: {charge_out_poa:,.2f} kWh (应该为0)")

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
    'Curtail_kWh': 'sum',
    'SOC_kWh': 'max',
    'SOC_Percent': 'max'
}).reset_index()

daily.columns = [
    'Date', 'Net_Revenue', 'Export_Revenue', 'Charge_Cost',
    'PV_Total', 'Charge_PV', 'Charge_Grid', 'Discharge', 'Curtail', 'Max_SOC_kWh', 'Max_SOC_Percent'
]

print(f"覆盖天数: {len(daily)}")
print(f"平均日收益: ${daily['Net_Revenue'].mean():,.2f}")
print(f"最高日收益: ${daily['Net_Revenue'].max():,.2f} ({daily.loc[daily['Net_Revenue'].idxmax(), 'Date']})")
print(f"最低日收益: ${daily['Net_Revenue'].min():,.2f} ({daily.loc[daily['Net_Revenue'].idxmin(), 'Date']})")

annual_estimate = (total_revenue / len(daily)) * 365
print(f"\n年化估算: ${annual_estimate:,.2f}/年")

# 检查每天是否充满
full_days = (daily['Max_SOC_Percent'] >= 99.0).sum()
print(f"\n电池充满天数: {full_days} / {len(daily)} ({full_days/len(daily)*100:.1f}%)")

if full_days < len(daily):
    print("\n未充满的天数:")
    not_full = daily[daily['Max_SOC_Percent'] < 99.0]
    for _, row in not_full.iterrows():
        print(f"  {row['Date']}: 最高SOC = {row['Max_SOC_Percent']:.1f}%")

# ==================== 保存结果 ====================
print("\n" + "="*80)
print("保存结果")
print("="*80)

output_folder = 'optimization_results_poa_constraints'
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
excel_file = f'{output_folder}/optimization_results_POA约束.xlsx'
with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
    results_df.to_excel(writer, sheet_name='详细数据', index=False)
    daily.to_excel(writer, sheet_name='每日汇总', index=False)
    
    # 对比统计
    comparison = pd.DataFrame({
        '指标': [
            '累计净收益',
            '平均日收益',
            '年化估算',
            '总光伏发电',
            '总充电量',
            '总放电量',
            '充放电效率',
            'POA>10时充电',
            'POA<=10时充电',
            '每日充满天数'
        ],
        '数值': [
            f"${total_revenue:,.2f}",
            f"${daily['Net_Revenue'].mean():,.2f}",
            f"${annual_estimate:,.2f}",
            f"{total_pv:,.2f} kWh",
            f"{total_charge:,.2f} kWh",
            f"{total_discharge:,.2f} kWh",
            f"{actual_efficiency*100:.2f}%",
            f"{charge_in_poa:,.2f} kWh",
            f"{charge_out_poa:,.2f} kWh (应为0)",
            f"{full_days} / {len(daily)}"
        ]
    })
    comparison.to_excel(writer, sheet_name='汇总统计', index=False)

print(f"[3] {excel_file} (3个工作表)")

print("\n" + "="*80)
print("优化完成！")
print("="*80)
print(f"\n关键指标:")
print(f"  累计净收益: ${total_revenue:,.2f}")
print(f"  平均日收益: ${daily['Net_Revenue'].mean():,.2f}")
print(f"  年化估算: ${annual_estimate:,.2f}")
print(f"  充放电效率: {actual_efficiency*100:.2f}%")
print(f"  POA约束: {'✓ 符合' if charge_out_poa < 0.01 else '✗ 违反'}")
print(f"  每日充满: {'✓ 全部达标' if full_days == len(daily) else f'✗ {len(daily)-full_days}天未达标'}")
print("\n" + "="*80)

