"""
储能电站完美收益优化模型 - 线性规划
基于历史POA和RRP数据，计算最优充放电策略
"""

import pandas as pd
import numpy as np
from pulp import *
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

class EnergyStorageOptimizer:
    def __init__(self, 
                 lgc_price=10,  # AUD/MWh
                 poa_to_power_ratio=3.79,  # W/(W/m²)
                 battery_max_charge=250,  # kW
                 battery_max_discharge=250,  # kW
                 battery_capacity=1000,  # kWh
                 charge_efficiency=0.95,  # 充电效率
                 discharge_efficiency=0.95,  # 放电效率
                 ramp_rate=16.67,  # kW/s
                 min_arbitrage_spread=0.05,  # AUD/kWh 夜间套利最低价差
                 initial_soc=0.5):  # 初始SOC (0-1)
        
        self.lgc_price = lgc_price
        self.poa_to_power_ratio = poa_to_power_ratio
        self.battery_max_charge = battery_max_charge
        self.battery_max_discharge = battery_max_discharge
        self.battery_capacity = battery_capacity
        self.charge_efficiency = charge_efficiency
        self.discharge_efficiency = discharge_efficiency
        self.ramp_rate = ramp_rate  # kW/s
        self.min_arbitrage_spread = min_arbitrage_spread
        self.initial_soc = initial_soc
        
        # 时间步长（5分钟 = 300秒）
        self.time_step = 300  # seconds
        self.time_step_hours = self.time_step / 3600  # hours
        
        # Ramp rate限制（每个时间步的最大功率变化）
        self.max_ramp_per_step = self.ramp_rate * self.time_step  # kW
        
        print("="*80)
        print("储能优化模型参数设置")
        print("="*80)
        print(f"LGC价格: {self.lgc_price} AUD/MWh")
        print(f"POA转换比: {self.poa_to_power_ratio} W/(W/m²)")
        print(f"电池最大充电功率: {self.battery_max_charge} kW")
        print(f"电池最大放电功率: {self.battery_max_discharge} kW")
        print(f"电池总容量: {self.battery_capacity} kWh")
        print(f"充电效率: {self.charge_efficiency*100}%")
        print(f"放电效率: {self.discharge_efficiency*100}%")
        print(f"Ramp Rate: {self.ramp_rate} kW/s")
        print(f"每5分钟最大功率变化: {self.max_ramp_per_step} kW")
        print(f"夜间套利最低价差: {self.min_arbitrage_spread} AUD/kWh")
        print(f"初始SOC: {self.initial_soc*100}%")
        print("="*80 + "\n")
    
    def load_data(self, csv_file):
        """加载POA和RRP数据"""
        df = pd.read_csv(csv_file, encoding='utf-8')
        
        # 提取需要的列
        self.data = pd.DataFrame({
            'datetime': pd.to_datetime(df['日期']),
            'poa': df['POA'],  # W/m²
            'rrp': df['电价RRP'],  # AUD/kWh
        })
        
        # 计算光伏发电功率 (kW)
        self.data['pv_power'] = self.data['poa'] * self.poa_to_power_ratio / 1000
        
        # 转换RRP为 AUD/kWh (如果需要)
        # 假设RRP已经是 AUD/kWh
        
        self.n_periods = len(self.data)
        
        print(f"数据加载完成:")
        print(f"  时间段数: {self.n_periods}")
        print(f"  时间范围: {self.data['datetime'].min()} 到 {self.data['datetime'].max()}")
        print(f"  POA范围: {self.data['poa'].min():.2f} ~ {self.data['poa'].max():.2f} W/m²")
        print(f"  RRP范围: {self.data['rrp'].min():.4f} ~ {self.data['rrp'].max():.4f} AUD/kWh")
        print(f"  PV功率范围: {self.data['pv_power'].min():.2f} ~ {self.data['pv_power'].max():.2f} kW")
        print()
        
        return self.data
    
    def build_optimization_model(self):
        """构建线性规划优化模型"""
        print("构建优化模型...")
        
        # 创建问题实例
        prob = LpProblem("Energy_Storage_Revenue_Optimization", LpMaximize)
        
        # 决策变量
        # P_charge[t]: 时刻t电池充电功率 (kW)
        P_charge = LpVariable.dicts("P_charge", range(self.n_periods), 
                                     lowBound=0, upBound=self.battery_max_charge)
        
        # P_discharge[t]: 时刻t电池放电功率 (kW)
        P_discharge = LpVariable.dicts("P_discharge", range(self.n_periods), 
                                        lowBound=0, upBound=self.battery_max_discharge)
        
        # P_grid_import[t]: 时刻t从电网导入功率 (NIL) (kW)
        P_grid_import = LpVariable.dicts("P_grid_import", range(self.n_periods), 
                                         lowBound=0)
        
        # P_grid_export[t]: 时刻t向电网输出功率 (NEL) (kW)
        P_grid_export = LpVariable.dicts("P_grid_export", range(self.n_periods), 
                                         lowBound=0)
        
        # SOC[t]: 时刻t电池荷电状态 (kWh)
        SOC = LpVariable.dicts("SOC", range(self.n_periods + 1), 
                               lowBound=0, upBound=self.battery_capacity)
        
        # 二进制变量：是否充电/放电（避免同时充放电）
        is_charging = LpVariable.dicts("is_charging", range(self.n_periods), cat='Binary')
        is_discharging = LpVariable.dicts("is_discharging", range(self.n_periods), cat='Binary')
        
        print(f"  决策变量数量: {5 * self.n_periods + 1}")
        
        # === 目标函数：最大化总收益 ===
        total_revenue = 0
        
        for t in range(self.n_periods):
            rrp = self.data.loc[t, 'rrp']  # AUD/kWh
            
            # 向电网售电收益
            export_revenue = P_grid_export[t] * self.time_step_hours * rrp
            
            # 从电网购电成本（负收益）
            import_cost = P_grid_import[t] * self.time_step_hours * rrp
            
            # LGC收益（光伏发电获得）
            lgc_revenue = self.data.loc[t, 'pv_power'] * self.time_step_hours * (self.lgc_price / 1000)
            
            total_revenue += export_revenue - import_cost + lgc_revenue
        
        prob += total_revenue, "Total_Revenue"
        
        # === 约束条件 ===
        
        # 1. 初始SOC约束
        prob += SOC[0] == self.initial_soc * self.battery_capacity, "Initial_SOC"
        
        # 2. SOC动态平衡约束
        for t in range(self.n_periods):
            prob += (SOC[t+1] == SOC[t] 
                    + P_charge[t] * self.time_step_hours * self.charge_efficiency
                    - P_discharge[t] * self.time_step_hours / self.discharge_efficiency,
                    f"SOC_Balance_{t}")
        
        # 3. 功率平衡约束
        for t in range(self.n_periods):
            pv_power = self.data.loc[t, 'pv_power']
            
            # 光伏发电 + 电池放电 + 电网导入 = 电池充电 + 电网输出
            prob += (pv_power + P_discharge[t] + P_grid_import[t] == 
                    P_charge[t] + P_grid_export[t],
                    f"Power_Balance_{t}")
        
        # 4. 不能同时充电和放电
        for t in range(self.n_periods):
            prob += is_charging[t] + is_discharging[t] <= 1, f"No_Simultaneous_Charge_Discharge_{t}"
            
            # Big M method
            M = max(self.battery_max_charge, self.battery_max_discharge)
            prob += P_charge[t] <= M * is_charging[t], f"Charge_Logic_{t}"
            prob += P_discharge[t] <= M * is_discharging[t], f"Discharge_Logic_{t}"
        
        # 5. Ramp Rate约束（功率变化速率限制）
        for t in range(1, self.n_periods):
            # 电网输出功率的变化率限制
            prob += (P_grid_export[t] - P_grid_export[t-1] <= self.max_ramp_per_step,
                    f"Ramp_Up_{t}")
            prob += (P_grid_export[t-1] - P_grid_export[t] <= self.max_ramp_per_step,
                    f"Ramp_Down_{t}")
        
        # 6. 对电网放电的最低价格约束（不低于 -LGC）
        min_export_price = -self.lgc_price / 1000  # 转换为 AUD/kWh
        for t in range(self.n_periods):
            rrp = self.data.loc[t, 'rrp']
            if rrp < min_export_price:
                # 如果电价低于最低价格，不允许向电网输出
                prob += P_grid_export[t] == 0, f"Min_Export_Price_{t}"
        
        # 7. 电池充电功率约束（光伏+电网 <= 最大充电功率）
        for t in range(self.n_periods):
            pv_power = self.data.loc[t, 'pv_power']
            prob += P_charge[t] <= self.battery_max_charge, f"Max_Charge_Power_{t}"
        
        print(f"  约束条件数量: {len(prob.constraints)}")
        print()
        
        self.prob = prob
        self.P_charge = P_charge
        self.P_discharge = P_discharge
        self.P_grid_import = P_grid_import
        self.P_grid_export = P_grid_export
        self.SOC = SOC
        self.is_charging = is_charging
        self.is_discharging = is_discharging
        
        return prob
    
    def solve(self, solver_name='PULP_CBC_CMD', time_limit=600):
        """求解优化问题"""
        print("="*80)
        print("开始求解优化问题...")
        print(f"求解器: {solver_name}")
        print(f"时间限制: {time_limit}秒")
        print("="*80)
        
        # 选择求解器
        if solver_name == 'PULP_CBC_CMD':
            solver = PULP_CBC_CMD(timeLimit=time_limit, msg=1)
        else:
            solver = None
        
        # 求解
        start_time = datetime.now()
        status = self.prob.solve(solver)
        solve_time = (datetime.now() - start_time).total_seconds()
        
        print(f"\n求解完成!")
        print(f"状态: {LpStatus[status]}")
        print(f"求解时间: {solve_time:.2f}秒")
        
        if status == 1:  # Optimal
            print(f"最优收益: ${value(self.prob.objective):,.2f}")
        
        return status
    
    def extract_results(self):
        """提取优化结果"""
        if self.prob.status != 1:
            print("警告: 优化未找到最优解!")
            return None
        
        results = self.data.copy()
        
        # 提取决策变量的值
        results['P_charge'] = [self.P_charge[t].varValue for t in range(self.n_periods)]
        results['P_discharge'] = [self.P_discharge[t].varValue for t in range(self.n_periods)]
        results['P_grid_import'] = [self.P_grid_import[t].varValue for t in range(self.n_periods)]
        results['P_grid_export'] = [self.P_grid_export[t].varValue for t in range(self.n_periods)]
        results['SOC'] = [self.SOC[t].varValue for t in range(self.n_periods)]
        results['SOC_pct'] = results['SOC'] / self.battery_capacity * 100
        
        # 计算每个时段的收益
        results['export_revenue'] = results['P_grid_export'] * self.time_step_hours * results['rrp']
        results['import_cost'] = results['P_grid_import'] * self.time_step_hours * results['rrp']
        results['lgc_revenue'] = results['pv_power'] * self.time_step_hours * (self.lgc_price / 1000)
        results['net_revenue'] = results['export_revenue'] - results['import_cost'] + results['lgc_revenue']
        
        # 计算能量流
        results['battery_charge_energy'] = results['P_charge'] * self.time_step_hours
        results['battery_discharge_energy'] = results['P_discharge'] * self.time_step_hours
        
        self.results = results
        return results
    
    def print_summary(self):
        """打印结果摘要"""
        if self.results is None:
            return
        
        print("\n" + "="*80)
        print("优化结果摘要")
        print("="*80)
        
        total_revenue = value(self.prob.objective)
        total_export = self.results['P_grid_export'].sum() * self.time_step_hours
        total_import = self.results['P_grid_import'].sum() * self.time_step_hours
        total_pv = self.results['pv_power'].sum() * self.time_step_hours
        
        total_charge = self.results['battery_charge_energy'].sum()
        total_discharge = self.results['battery_discharge_energy'].sum()
        
        total_export_revenue = self.results['export_revenue'].sum()
        total_import_cost = self.results['import_cost'].sum()
        total_lgc = self.results['lgc_revenue'].sum()
        
        print(f"\n总收益: ${total_revenue:,.2f}")
        print(f"  - 售电收益: ${total_export_revenue:,.2f}")
        print(f"  - 购电成本: ${total_import_cost:,.2f}")
        print(f"  - LGC收益: ${total_lgc:,.2f}")
        
        print(f"\n能量统计:")
        print(f"  - 光伏总发电: {total_pv:,.2f} kWh")
        print(f"  - 向电网售电: {total_export:,.2f} kWh")
        print(f"  - 从电网购电: {total_import:,.2f} kWh")
        print(f"  - 电池总充电: {total_charge:,.2f} kWh")
        print(f"  - 电池总放电: {total_discharge:,.2f} kWh")
        print(f"  - 充放电效率: {total_discharge/total_charge*100:.2f}%")
        
        print(f"\n电池使用:")
        print(f"  - 最终SOC: {self.results['SOC_pct'].iloc[-1]:.2f}%")
        print(f"  - SOC范围: {self.results['SOC_pct'].min():.2f}% ~ {self.results['SOC_pct'].max():.2f}%")
        print(f"  - 充电次数: {(self.results['P_charge'] > 0).sum()}")
        print(f"  - 放电次数: {(self.results['P_discharge'] > 0).sum()}")
        
        # 统计负电价时段的套利
        negative_price_periods = self.results[self.results['rrp'] < 0]
        if len(negative_price_periods) > 0:
            neg_import = negative_price_periods['P_grid_import'].sum() * self.time_step_hours
            neg_benefit = -negative_price_periods['import_cost'].sum()
            print(f"\n负电价套利:")
            print(f"  - 负电价时段数: {len(negative_price_periods)}")
            print(f"  - 负电价时购电: {neg_import:,.2f} kWh")
            print(f"  - 负电价套利收益: ${neg_benefit:,.2f}")
        
        print("="*80)
    
    def save_results(self, filename='optimization_results.csv'):
        """保存结果到CSV"""
        if self.results is not None:
            self.results.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"\n结果已保存到: {filename}")
    
    def plot_results(self, days=3):
        """绘制结果图表"""
        if self.results is None:
            return
        
        # 只显示前几天的数据
        periods_per_day = 24 * 60 // 5  # 每天288个时间点
        plot_periods = min(periods_per_day * days, self.n_periods)
        plot_data = self.results.iloc[:plot_periods]
        
        fig, axes = plt.subplots(4, 1, figsize=(16, 12))
        fig.suptitle(f'储能优化结果分析（前{days}天）', fontsize=16, fontweight='bold')
        
        time_index = range(len(plot_data))
        
        # 1. 功率分布
        ax1 = axes[0]
        ax1.plot(time_index, plot_data['pv_power'], label='光伏发电', linewidth=1.5, alpha=0.8)
        ax1.plot(time_index, plot_data['P_charge'], label='电池充电', linewidth=1.5, alpha=0.8)
        ax1.plot(time_index, plot_data['P_discharge'], label='电池放电', linewidth=1.5, alpha=0.8)
        ax1.plot(time_index, plot_data['P_grid_export'], label='电网输出', linewidth=1.5, alpha=0.8)
        ax1.plot(time_index, plot_data['P_grid_import'], label='电网导入', linewidth=1.5, alpha=0.8)
        ax1.set_ylabel('功率 (kW)', fontsize=11)
        ax1.set_title('功率分布', fontsize=12)
        ax1.legend(loc='upper right', ncol=5)
        ax1.grid(True, alpha=0.3)
        
        # 2. SOC变化
        ax2 = axes[1]
        ax2.plot(time_index, plot_data['SOC_pct'], linewidth=2, color='green')
        ax2.fill_between(time_index, 0, plot_data['SOC_pct'], alpha=0.3, color='green')
        ax2.set_ylabel('SOC (%)', fontsize=11)
        ax2.set_title('电池荷电状态', fontsize=12)
        ax2.set_ylim([0, 100])
        ax2.grid(True, alpha=0.3)
        
        # 3. 电价和收益
        ax3 = axes[2]
        ax3_twin = ax3.twinx()
        
        line1 = ax3.plot(time_index, plot_data['rrp'], label='RRP', 
                        linewidth=1.5, color='blue', alpha=0.7)
        line2 = ax3_twin.plot(time_index, plot_data['net_revenue'], label='时段收益', 
                             linewidth=1.5, color='red', alpha=0.7)
        
        ax3.axhline(y=0, color='black', linestyle='--', linewidth=0.8, alpha=0.5)
        ax3.set_ylabel('电价 (AUD/kWh)', fontsize=11, color='blue')
        ax3_twin.set_ylabel('收益 (AUD)', fontsize=11, color='red')
        ax3.set_title('电价与收益', fontsize=12)
        ax3.tick_params(axis='y', labelcolor='blue')
        ax3_twin.tick_params(axis='y', labelcolor='red')
        ax3.grid(True, alpha=0.3)
        
        lines = line1 + line2
        labels = [l.get_label() for l in lines]
        ax3.legend(lines, labels, loc='upper right')
        
        # 4. 累计收益
        ax4 = axes[3]
        cumulative_revenue = plot_data['net_revenue'].cumsum()
        ax4.plot(time_index, cumulative_revenue, linewidth=2, color='darkgreen')
        ax4.fill_between(time_index, 0, cumulative_revenue, alpha=0.3, color='green')
        ax4.set_xlabel('时间索引 (5分钟间隔)', fontsize=11)
        ax4.set_ylabel('累计收益 (AUD)', fontsize=11)
        ax4.set_title('累计收益', fontsize=12)
        ax4.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('optimization_results.png', dpi=300, bbox_inches='tight')
        print("结果图表已保存为: optimization_results.png")
        
        return fig


def main():
    """主函数"""
    print("\n" + "="*80)
    print("储能电站完美收益优化模型")
    print("="*80 + "\n")
    
    # 创建优化器（可调整参数）
    optimizer = EnergyStorageOptimizer(
        lgc_price=10,  # AUD/MWh
        poa_to_power_ratio=3.79,  # W/(W/m²)
        battery_max_charge=250,  # kW
        battery_max_discharge=250,  # kW
        battery_capacity=1000,  # kWh
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        ramp_rate=16.67,  # kW/s
        min_arbitrage_spread=0.05,  # AUD/kWh
        initial_soc=0.5  # 50%
    )
    
    # 加载数据
    data = optimizer.load_data('excel_1117版本.csv')
    
    # 构建优化模型
    prob = optimizer.build_optimization_model()
    
    # 求解
    status = optimizer.solve(time_limit=600)
    
    if status == 1:
        # 提取结果
        results = optimizer.extract_results()
        
        # 打印摘要
        optimizer.print_summary()
        
        # 保存结果
        optimizer.save_results('optimization_results.csv')
        
        # 绘制图表
        optimizer.plot_results(days=3)
        
        print("\n优化完成!")
    else:
        print("\n优化失败，请检查模型设置。")


if __name__ == "__main__":
    main()


