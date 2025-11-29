#!/usr/bin/env python3
"""
线性规划优化模型 - 使用Excel数据和新参数
基于Excel 1117版本的POA和PV数据

新参数：
- 电池容量: 5504 kWh
- 最大充电功率: 2752 kW
- 最大放电功率: 2752 kW
- NEL: 4440 kW
- NIL: 670 kW
- 充放电效率: 95% / 95%
"""

import pandas as pd
import numpy as np
from pulp import *
import os
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

print("="*80)
print("线性规划优化模型 - 使用Excel数据和新参数")
print("="*80)

# ==================== 配置参数 ====================
class OptimizationConfig:
    """优化模型配置参数（新参数）"""
    
    # 电网限制
    NEL = 4440.0  # kW - 对电网最大输出功率（新）
    NIL = 670.0   # kW - 从电网最大输入功率
    
    # 电池参数（新）
    BATTERY_CAPACITY = 5504.0  # kWh - 电池储能总量
    BATTERY_MAX_CHARGE_POWER = 2752.0  # kW - 电池最大充电功率
    BATTERY_MAX_DISCHARGE_POWER = 2752.0  # kW - 电池最大放电功率
    
    # 效率
    CHARGE_EFFICIENCY = 0.95   # 充电效率
    DISCHARGE_EFFICIENCY = 0.95  # 放电效率
    
    # 价格限制
    LGC = -10.0  # AUD/MWh - 对电网放电的最低价格
    
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
        print(f"  数据间隔: {self.INTERVAL_MINUTES} 分钟")

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

# 查看列名
print(f"\n数据列名:")
for i, col in enumerate(df.columns[:10], 1):
    print(f"  {i}. {col}")

# 重命名列（去掉可能的空格）
df.columns = df.columns.str.strip()

# 确保必要的列存在
required_cols = ['日期', 'POA', '光伏发电量', '电价RRP']
missing_cols = [col for col in required_cols if col not in df.columns]
if missing_cols:
    print(f"\n错误: 缺少必要的列: {missing_cols}")
    print(f"实际列名: {list(df.columns)}")
    exit(1)

# 转换时间
df['Timestamp'] = pd.to_datetime(df['日期'])
df = df.sort_values('Timestamp').reset_index(drop=True)

print(f"\n数据信息:")
print(f"  数据行数: {len(df):,}")
print(f"  时间范围: {df['Timestamp'].min()} 到 {df['Timestamp'].max()}")
print(f"  POA范围: {df['POA'].min():.2f} - {df['POA'].max():.2f} W/m²")
print(f"  RRP范围: ${df['电价RRP'].min():.4f} - ${df['电价RRP'].max():.4f} $/kWh")

# 注意：Excel中的电价RRP可能已经是$/kWh，需要转换为$/MWh
# 检查RRP的数量级
if df['电价RRP'].mean() < 1:
    print("\n  注意: 电价RRP看起来是$/kWh，转换为$/MWh")
    df['RRP_MWh'] = df['电价RRP'] * 1000
else:
    print("\n  注意: 电价RRP已经是$/MWh")
    df['RRP_MWh'] = df['电价RRP']

print(f"  RRP范围($/MWh): ${df['RRP_MWh'].min():.2f} - ${df['RRP_MWh'].max():.2f}")

# 使用Excel中的光伏发电量（已经是kWh）
df['PV_Energy_kWh'] = df['光伏发电量']

print(f"  总光伏发电量: {df['PV_Energy_kWh'].sum():,.2f} kWh")

# ==================== 构建线性规划模型 ====================
print("\n" + "="*80)
print("构建线性规划模型")
print("="*80)

print("\n创建优化问题...")
prob = LpProblem("Battery_Optimization_Excel_Data", LpMaximize)

# 时段索引
T = range(len(df))
print(f"优化时段数: {len(T):,}")

# ==================== 定义决策变量 ====================
print("\n定义决策变量...")

# 充电变量
charge_grid = [
    LpVariable(f"cg_{t}", lowBound=0, 
               upBound=config.NIL * config.INTERVAL_HOURS) 
    for t in T
]

charge_pv = [
    LpVariable(f"cp_{t}", lowBound=0, 
               upBound=df.loc[t, 'PV_Energy_kWh']) 
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

print(f"  总决策变量: {len(T) * 7:,} 个")

# ==================== 定义目标函数 ====================
print("\n定义目标函数...")

revenue_terms = []
cost_terms = []

for t in T:
    rrp = df.loc[t, 'RRP_MWh']
    
    # 上网收益（RRP是$/MWh，能量是kWh，需要除以1000）
    revenue_terms.append((export_pv[t] + export_battery[t]) * rrp / 1000.0)
    
    # 购电成本
    cost_terms.append(charge_grid[t] * rrp / 1000.0)

prob += lpSum(revenue_terms) - lpSum(cost_terms), "Total_Revenue"
print("  目标: 最大化(上网收益 - 购电成本)")

# ==================== 定义约束条件 ====================
print("\n定义约束条件...")

# 1. 光伏能量平衡
print("  [1/5] 光伏能量平衡...")
for t in T:
    prob += (
        charge_pv[t] + export_pv[t] + curtail[t] == df.loc[t, 'PV_Energy_kWh'],
        f"PV_Bal_{t}"
    )

# 2. 电池SOC递推
print("  [2/5] 电池SOC递推...")
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

# 3. 储能上网能量
print("  [3/5] 储能上网能量...")
for t in T:
    prob += (
        export_battery[t] == discharge[t] * config.DISCHARGE_EFFICIENCY,
        f"Bat_Exp_{t}"
    )

# 4. NEL限制
print("  [4/5] 电网输出限制(NEL)...")
for t in T:
    total_export_power = (export_pv[t] + export_battery[t]) / config.INTERVAL_HOURS
    prob += (
        total_export_power <= config.NEL,
        f"NEL_{t}"
    )

# 5. LGC限制
print("  [5/5] LGC限制...")
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

print("\n开始求解（这可能需要几秒到几分钟）...")
start_solve = datetime.now()

solver = PULP_CBC_CMD(msg=1, timeLimit=600)
prob.solve(solver)

end_solve = datetime.now()
solve_time = (end_solve - start_solve).total_seconds()

status = LpStatus[prob.status]
print(f"\n求解状态: {status}")
print(f"求解时间: {solve_time:.1f} 秒")

if status != 'Optimal':
    print(f"\n错误: 优化失败，状态为 {status}")
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
        'RRP_MWh': df.loc[t, 'RRP_MWh'],
        'POA': df.loc[t, 'POA'],
        'PV_Power_kW': df.loc[t, 'PV功率'] if 'PV功率' in df.columns else df.loc[t, 'PV_Energy_kWh'] / config.INTERVAL_HOURS,
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
results_df['Date'] = results_df['Timestamp'].dt.date.astype(str)

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
    'SOC_kWh': 'max'
}).reset_index()

daily.columns = [
    'Date', 'Net_Revenue', 'Export_Revenue', 'Charge_Cost',
    'PV_Total', 'Charge_PV', 'Charge_Grid', 'Discharge', 'Curtail', 'Max_SOC'
]

print(f"覆盖天数: {len(daily)}")
print(f"平均日收益: ${daily['Net_Revenue'].mean():,.2f}")
print(f"最高日收益: ${daily['Net_Revenue'].max():,.2f} ({daily.loc[daily['Net_Revenue'].idxmax(), 'Date']})")
print(f"最低日收益: ${daily['Net_Revenue'].min():,.2f} ({daily.loc[daily['Net_Revenue'].idxmin(), 'Date']})")

annual_estimate = (total_revenue / len(daily)) * 365
print(f"\n年化估算: ${annual_estimate:,.2f}/年")

# 检查每天是否充满
full_days = (daily['Max_SOC'] >= config.BATTERY_CAPACITY * 0.99).sum()
print(f"\n电池充满天数: {full_days} / {len(daily)} ({full_days/len(daily)*100:.1f}%)")

# ==================== 保存结果 ====================
print("\n" + "="*80)
print("保存结果")
print("="*80)

output_folder = 'optimization_results_new_params'
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

# Excel格式（包含原始Excel中的所有列）
combined = pd.DataFrame()

# 从原始Excel复制的列
combined['日期'] = results_df['Timestamp']
combined['POA'] = results_df['POA']

# 添加原始Excel的PV功率（从原始数据读取）
original_pv_power = df.loc[:, 'PV功率'].values if 'PV功率' in df.columns else results_df['PV_Energy_kWh'] / config.INTERVAL_HOURS
combined['PV功率'] = original_pv_power

# 充放电状态
combined['充电状态'] = np.where(
    (results_df['Charge_PV_kWh'] > 0.01) | (results_df['Charge_Grid_kWh'] > 0.01),
    340, np.where(results_df['Discharge_kWh'] > 0.01, 341, 0)
)
combined['电网状态'] = 350

# 能量列
combined['实际充电量'] = results_df['Charge_PV_kWh'] + results_df['Charge_Grid_kWh']
combined['实际放电量'] = results_df['Discharge_kWh']
combined['光伏发电量'] = results_df['PV_Energy_kWh']
combined['电网充电量'] = results_df['Charge_Grid_kWh']

# 辐照状态
combined['辐照状态'] = np.where(results_df['POA'] > 10, 321, 0)

# 收益列
combined['光伏收益'] = results_df['Export_PV_kWh'] * results_df['RRP_MWh'] / 1000.0
combined['电网收益'] = -results_df['Charge_Cost']
combined['电池收益'] = results_df['Export_Battery_kWh'] * results_df['RRP_MWh'] / 1000.0
combined['SOC'] = results_df['SOC_kWh'] / config.BATTERY_CAPACITY
combined['电价RRP'] = results_df['RRP_MWh'] / 1000.0
combined['总收益'] = results_df['Net_Revenue']

# 空列（保持格式）
combined['Unnamed: 16'] = np.nan
combined['Unnamed: 17'] = np.nan

# 总放电量
combined['总放电量'] = results_df['Export_PV_kWh'] + results_df['Export_Battery_kWh']

# 能量平衡检查列
combined['（光伏发电量-电池充电量+电池放电量-电网充电量）'] = (
    results_df['PV_Energy_kWh'] 
    - combined['实际充电量']
    + results_df['Discharge_kWh']
)

# 更多空列
combined['Unnamed: 20'] = np.nan
combined['Unnamed: 21'] = np.nan
combined['Unnamed: 22'] = np.nan
combined['Unnamed: 23'] = np.nan

# Real Export和Revenue
combined['Real Export'] = combined['总放电量']
combined['Revenue'] = results_df['Export_Revenue']
combined['Unnamed: 26'] = np.nan
combined['perfect ratio'] = np.nan

excel_file = f'{output_folder}/optimization_results_新参数.xlsx'
with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
    combined.to_excel(writer, sheet_name='优化结果', index=False)
    results_df.to_excel(writer, sheet_name='详细数据', index=False)
    daily.to_excel(writer, sheet_name='每日汇总', index=False)

print(f"[3] {excel_file} (3个工作表)")

# 生成报告
report_file = f'{output_folder}/optimization_report.txt'
report = []
report.append("="*80)
report.append("线性规划优化结果报告（新参数）")
report.append("="*80)
report.append(f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
report.append(f"数据来源: {excel_file}")
report.append(f"\n参数配置:")
report.append(f"  电池容量: {config.BATTERY_CAPACITY} kWh")
report.append(f"  充电功率: {config.BATTERY_MAX_CHARGE_POWER} kW")
report.append(f"  放电功率: {config.BATTERY_MAX_DISCHARGE_POWER} kW")
report.append(f"  NEL: {config.NEL} kW")
report.append(f"  NIL: {config.NIL} kW")
report.append(f"  效率: {config.CHARGE_EFFICIENCY*100}% / {config.DISCHARGE_EFFICIENCY*100}%")
report.append(f"\n数据行数: {len(results_df):,}")
report.append(f"覆盖天数: {len(daily)}")
report.append(f"求解时间: {solve_time:.1f} 秒")
report.append(f"\n累计净收益: ${total_revenue:,.2f}")
report.append(f"平均日收益: ${daily['Net_Revenue'].mean():,.2f}")
report.append(f"年化估算: ${annual_estimate:,.2f}")
report.append("\n" + "="*80)

with open(report_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(report))

print(f"[4] {report_file}")

print("\n" + "="*80)
print("优化完成！")
print("="*80)
print(f"\n关键指标:")
print(f"  累计净收益: ${total_revenue:,.2f}")
print(f"  平均日收益: ${daily['Net_Revenue'].mean():,.2f}")
print(f"  年化估算: ${annual_estimate:,.2f}")
print(f"  充放电效率: {actual_efficiency*100:.2f}%")
print("\n" + "="*80)

