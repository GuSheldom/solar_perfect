"""
白天储能充电+辐照放电优化策略

策略逻辑：
1. 根据POA推算每个时段的光伏发电功率
2. 白天(POA>10)选择最低RRP时段充电直到SOC=100%
3. 充电时：光伏优先，不足则从电网补充(NIL)
4. 光伏多余电量：RRP>-10则并网，否则弃电
5. 晚上高价时段放电
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from typing import Tuple, List

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


class DaytimeStorageOptimizer:
    """白天储能充电优化器"""
    
    def __init__(self,
                 lgc_price=10,  # AUD/MWh
                 poa_to_power_ratio=3.79,  # W/(W/m²)
                 battery_max_charge=250,  # kW
                 battery_max_discharge=250,  # kW
                 battery_capacity=1000,  # kWh
                 charge_efficiency=0.95,
                 discharge_efficiency=0.95,
                 ramp_rate=16.67,  # kW/s
                 min_export_price=-10,  # AUD/MWh 最低发电价格
                 initial_soc=0.0):
        
        self.lgc_price = lgc_price / 1000  # 转换为 AUD/kWh
        self.poa_to_power_ratio = poa_to_power_ratio
        self.P_charge_max = battery_max_charge
        self.P_discharge_max = battery_max_discharge
        self.E_capacity = battery_capacity
        self.eta_c = charge_efficiency
        self.eta_d = discharge_efficiency
        self.ramp_rate = ramp_rate
        self.min_export_price = min_export_price / 1000  # 转换为 AUD/kWh
        self.initial_soc = initial_soc
        
        self.dt = 5 / 60  # 时间步长（小时）
        self.max_ramp = ramp_rate * 300  # 每5分钟最大变化
        
        print("="*80)
        print("白天储能充电+辐照放电优化策略")
        print("="*80)
        print(f"POA转换比: {poa_to_power_ratio}")
        print(f"电池容量: {battery_capacity} kWh")
        print(f"最大充电功率: {battery_max_charge} kW")
        print(f"最大放电功率: {battery_max_discharge} kW")
        print(f"最低发电价格: {min_export_price} AUD/MWh")
        print(f"充放电效率: {charge_efficiency*100}% / {discharge_efficiency*100}%")
        print("="*80 + "\n")
    
    def load_data(self, csv_file, max_periods=None):
        """加载数据"""
        df = pd.read_csv(csv_file, encoding='utf-8')
        
        self.data = pd.DataFrame({
            'datetime': pd.to_datetime(df['日期']),
            'poa': df['POA'],
            'rrp': df['电价RRP'],
        })
        
        # 计算光伏发电功率 (kW)
        self.data['pv_power'] = self.data['poa'] * self.poa_to_power_ratio / 1000
        
        # 添加日期列用于按天分组
        self.data['date'] = self.data['datetime'].dt.date
        
        if max_periods:
            self.data = self.data.iloc[:max_periods].copy()
        
        self.n = len(self.data)
        
        print(f"数据加载: {self.n} 个时间段")
        print(f"时间范围: {self.data['datetime'].min()} 到 {self.data['datetime'].max()}")
        print(f"天数: {self.data['date'].nunique()}")
        print(f"RRP范围: {self.data['rrp'].min():.4f} ~ {self.data['rrp'].max():.4f} AUD/kWh\n")
        
        return self.data
    
    def optimize_daily(self):
        """按天优化策略"""
        print("开始按天优化...")
        start_time = datetime.now()
        
        results = self.data.copy()
        results['P_charge'] = 0.0  # 电池充电功率
        results['P_discharge'] = 0.0  # 电池放电功率
        results['P_grid_import'] = 0.0  # 从电网导入(NIL)
        results['P_grid_export'] = 0.0  # 向电网输出
        results['P_pv_curtail'] = 0.0  # 弃光功率
        results['SOC'] = 0.0
        results['SOC_pct'] = 0.0
        results['action'] = 'idle'  # 动作标记
        
        # 按天循环优化
        unique_dates = results['date'].unique()
        
        for day_idx, date in enumerate(unique_dates):
            day_data = results[results['date'] == date].copy()
            
            # 优化单日
            day_results = self._optimize_single_day(day_data, day_idx)
            
            # 更新结果
            for col in ['P_charge', 'P_discharge', 'P_grid_import', 'P_grid_export', 
                       'P_pv_curtail', 'SOC', 'SOC_pct', 'action']:
                results.loc[day_results.index, col] = day_results[col]
        
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"优化完成，耗时: {elapsed:.2f}秒")
        
        self.results = results
        self._calculate_revenue()
        return results
    
    def _optimize_single_day(self, day_data: pd.DataFrame, day_idx: int) -> pd.DataFrame:
        """优化单日策略"""
        day_results = day_data.copy()
        
        # 初始SOC
        if day_idx == 0:
            soc = self.initial_soc * self.E_capacity
        else:
            # 继承前一天最后的SOC
            if hasattr(self, '_prev_day_soc'):
                soc = self._prev_day_soc
            else:
                soc = self.initial_soc * self.E_capacity
        
        # === 阶段1: 识别白天充电时段 ===
        # 筛选POA>10的时段作为候选充电时段
        daytime_mask = day_results['poa'] > 10
        daytime_periods = day_results[daytime_mask].copy()
        
        if len(daytime_periods) == 0:
            # 没有白天时段，直接返回
            day_results['SOC'] = soc
            day_results['SOC_pct'] = soc / self.E_capacity * 100
            return day_results
        
        # 按RRP排序，选择最低价格的时段进行充电
        daytime_periods_sorted = daytime_periods.sort_values('rrp')
        
        # === 阶段2: 白天充电阶段 ===
        # 选择最低价格时段充电，直到SOC达到100%
        charging_periods = set()
        target_charge_energy = self.E_capacity - soc  # 需要充电的能量
        accumulated_charge = 0.0
        
        for idx, row in daytime_periods_sorted.iterrows():
            if accumulated_charge >= target_charge_energy:
                break
            
            pv_power = row['pv_power']
            rrp = row['rrp']
            
            # 计算本时段可充电量
            max_charge_this_period = min(
                self.P_charge_max * self.dt,  # 功率限制
                target_charge_energy - accumulated_charge  # 剩余需求
            )
            
            # 光伏可提供的充电能量
            pv_energy = pv_power * self.dt
            
            if pv_energy >= max_charge_this_period:
                # 光伏足够充电
                accumulated_charge += max_charge_this_period
            else:
                # 光伏不足，全部用于充电
                accumulated_charge += pv_energy
            
            charging_periods.add(idx)
            
            # 检查是否达到100%
            if accumulated_charge >= target_charge_energy * 0.999:  # 允许0.1%误差
                break
        
        # === 阶段3: 执行策略 ===
        prev_grid_export = 0.0
        
        for idx, row in day_results.iterrows():
            pv_power = row['pv_power']
            rrp = row['rrp']
            poa = row['poa']
            
            P_charge = 0.0
            P_discharge = 0.0
            P_grid_import = 0.0
            P_grid_export = 0.0
            P_pv_curtail = 0.0
            action = 'idle'
            
            if idx in charging_periods:
                # === 充电时段 ===
                action = 'charging'
                
                # 可充电容量
                available_capacity = self.E_capacity - soc
                max_charge_power = min(self.P_charge_max, 
                                      available_capacity / (self.dt * self.eta_c))
                
                if pv_power >= max_charge_power:
                    # 情况1: 光伏功率 >= 电池最大充电功率
                    P_charge = max_charge_power
                    excess_power = pv_power - max_charge_power
                    
                    if rrp > self.min_export_price:
                        # RRP > -10: 多余电量并网
                        P_grid_export = excess_power
                    else:
                        # RRP <= -10: 弃电
                        P_pv_curtail = excess_power
                
                else:
                    # 情况2: 光伏功率 < 电池最大充电功率
                    # 光伏全部用于充电
                    pv_to_battery = pv_power
                    
                    # 从电网补充充电(NIL)
                    nil_power = min(max_charge_power - pv_to_battery,
                                   self.P_charge_max - pv_to_battery)
                    
                    P_charge = pv_to_battery + nil_power
                    P_grid_import = nil_power
            
            elif poa > 5:
                # === 白天非充电时段：光伏发电 ===
                if rrp > self.min_export_price:
                    # RRP > -10: 发电并网
                    P_grid_export = pv_power
                    action = 'pv_export'
                else:
                    # RRP <= -10: 弃电
                    P_pv_curtail = pv_power
                    action = 'curtail'
            
            else:
                # === 夜间时段：考虑放电 ===
                # 高价时段放电
                if rrp > day_results['rrp'].quantile(0.75) and soc > 0.1 * self.E_capacity:
                    max_discharge_power = min(self.P_discharge_max,
                                             soc * self.eta_d / self.dt)
                    P_discharge = max_discharge_power
                    P_grid_export = P_discharge
                    action = 'discharging'
            
            # Ramp rate约束
            if abs(P_grid_export - prev_grid_export) > self.max_ramp:
                if P_grid_export > prev_grid_export:
                    P_grid_export = prev_grid_export + self.max_ramp
                else:
                    P_grid_export = max(0, prev_grid_export - self.max_ramp)
            
            # 更新SOC
            soc += P_charge * self.dt * self.eta_c
            soc -= P_discharge * self.dt / self.eta_d
            soc = np.clip(soc, 0, self.E_capacity)
            
            # 保存结果
            day_results.loc[idx, 'P_charge'] = P_charge
            day_results.loc[idx, 'P_discharge'] = P_discharge
            day_results.loc[idx, 'P_grid_import'] = P_grid_import
            day_results.loc[idx, 'P_grid_export'] = P_grid_export
            day_results.loc[idx, 'P_pv_curtail'] = P_pv_curtail
            day_results.loc[idx, 'SOC'] = soc
            day_results.loc[idx, 'SOC_pct'] = soc / self.E_capacity * 100
            day_results.loc[idx, 'action'] = action
            
            prev_grid_export = P_grid_export
        
        # 保存最后的SOC供下一天使用
        self._prev_day_soc = soc
        
        return day_results
    
    def _calculate_revenue(self):
        """计算收益"""
        r = self.results
        
        # 各项收益/成本
        r['export_revenue'] = r['P_grid_export'] * self.dt * r['rrp']
        r['import_cost'] = r['P_grid_import'] * self.dt * r['rrp']
        r['lgc_revenue'] = (r['P_grid_export'] + r['P_pv_curtail']) * self.dt * self.lgc_price
        r['net_revenue'] = r['export_revenue'] - r['import_cost'] + r['lgc_revenue']
        
        # 能量
        r['battery_charge_energy'] = r['P_charge'] * self.dt
        r['battery_discharge_energy'] = r['P_discharge'] * self.dt
        r['pv_curtail_energy'] = r['P_pv_curtail'] * self.dt
    
    def print_summary(self):
        """打印结果摘要"""
        if not hasattr(self, 'results'):
            return
        
        r = self.results
        
        print("\n" + "="*80)
        print("优化结果摘要")
        print("="*80)
        
        total_revenue = r['net_revenue'].sum()
        total_export_rev = r['export_revenue'].sum()
        total_import_cost = r['import_cost'].sum()
        total_lgc = r['lgc_revenue'].sum()
        
        total_pv_energy = r['pv_power'].sum() * self.dt
        total_export = r['P_grid_export'].sum() * self.dt
        total_import = r['P_grid_import'].sum() * self.dt
        total_charge = r['battery_charge_energy'].sum()
        total_discharge = r['battery_discharge_energy'].sum()
        total_curtail = r['pv_curtail_energy'].sum()
        
        print(f"\n💰 总收益: ${total_revenue:,.2f}")
        print(f"   ├─ 售电收益: ${total_export_rev:,.2f}")
        print(f"   ├─ 购电成本: ${total_import_cost:,.2f}")
        print(f"   └─ LGC收益: ${total_lgc:,.2f}")
        
        print(f"\n⚡ 能量统计:")
        print(f"   ├─ 光伏总发电: {total_pv_energy:,.2f} kWh")
        print(f"   ├─ 弃光总量: {total_curtail:,.2f} kWh ({total_curtail/total_pv_energy*100:.1f}%)")
        print(f"   ├─ 向电网售电: {total_export:,.2f} kWh")
        print(f"   ├─ 从电网购电(NIL): {total_import:,.2f} kWh")
        print(f"   ├─ 电池总充电: {total_charge:,.2f} kWh")
        print(f"   ├─ 电池总放电: {total_discharge:,.2f} kWh")
        if total_charge > 0:
            print(f"   └─ 往返效率: {total_discharge/total_charge*100:.2f}%")
        
        print(f"\n🔋 电池使用:")
        print(f"   ├─ 最终SOC: {r['SOC_pct'].iloc[-1]:.2f}%")
        print(f"   ├─ SOC范围: {r['SOC_pct'].min():.2f}% ~ {r['SOC_pct'].max():.2f}%")
        print(f"   ├─ 达到100%次数: {(r['SOC_pct'] >= 99.9).sum()} 次")
        print(f"   ├─ 充电周期: {(r['P_charge'] > 1).sum()} 次")
        print(f"   └─ 放电周期: {(r['P_discharge'] > 1).sum()} 次")
        
        # 动作统计
        print(f"\n📊 策略执行:")
        action_counts = r['action'].value_counts()
        for action, count in action_counts.items():
            print(f"   ├─ {action}: {count} 次")
        
        # 负电价统计
        neg_periods = r[r['rrp'] < 0]
        if len(neg_periods) > 0:
            neg_import = neg_periods['P_grid_import'].sum() * self.dt
            neg_benefit = -neg_periods['import_cost'].sum()
            print(f"\n📉 负电价套利:")
            print(f"   ├─ 负电价时段: {len(neg_periods)} 个")
            print(f"   ├─ 购电量(NIL): {neg_import:,.2f} kWh")
            print(f"   └─ 套利收益: ${neg_benefit:,.2f}")
        
        print("="*80)
    
    def save_results(self, filename='daytime_storage_results.csv'):
        """保存结果"""
        if hasattr(self, 'results'):
            self.results.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"\n结果已保存到: {filename}")
    
    def plot_results(self, days=3):
        """绘制结果图表"""
        if not hasattr(self, 'results'):
            return
        
        periods_per_day = 288
        plot_periods = min(periods_per_day * days, self.n)
        plot_data = self.results.iloc[:plot_periods]
        
        fig, axes = plt.subplots(5, 1, figsize=(16, 14))
        fig.suptitle(f'白天储能充电策略结果（前{days}天）', fontsize=16, fontweight='bold')
        
        time_idx = range(len(plot_data))
        
        # 1. 光伏功率和电网交互
        ax1 = axes[0]
        ax1.plot(time_idx, plot_data['pv_power'], label='光伏发电', linewidth=1.5, alpha=0.8)
        ax1.plot(time_idx, plot_data['P_grid_export'], label='电网输出', linewidth=1.5, alpha=0.8)
        ax1.plot(time_idx, plot_data['P_grid_import'], label='电网导入(NIL)', linewidth=1.5, alpha=0.8)
        ax1.plot(time_idx, plot_data['P_pv_curtail'], label='弃光', linewidth=1.5, alpha=0.8, linestyle='--')
        ax1.set_ylabel('功率 (kW)', fontsize=11)
        ax1.set_title('光伏与电网交互', fontsize=12)
        ax1.legend(loc='upper right', ncol=4, fontsize=9)
        ax1.grid(True, alpha=0.3)
        
        # 2. 电池充放电
        ax2 = axes[1]
        ax2.plot(time_idx, plot_data['P_charge'], label='电池充电', linewidth=1.5, alpha=0.8, color='green')
        ax2.plot(time_idx, plot_data['P_discharge'], label='电池放电', linewidth=1.5, alpha=0.8, color='red')
        ax2.set_ylabel('功率 (kW)', fontsize=11)
        ax2.set_title('电池充放电', fontsize=12)
        ax2.legend(loc='upper right', fontsize=9)
        ax2.grid(True, alpha=0.3)
        
        # 3. SOC
        ax3 = axes[2]
        ax3.plot(time_idx, plot_data['SOC_pct'], linewidth=2, color='purple')
        ax3.fill_between(time_idx, 0, plot_data['SOC_pct'], alpha=0.3, color='purple')
        ax3.axhline(y=100, color='red', linestyle='--', linewidth=1, alpha=0.5, label='100% SOC')
        ax3.set_ylabel('SOC (%)', fontsize=11)
        ax3.set_title('电池荷电状态', fontsize=12)
        ax3.set_ylim([0, 105])
        ax3.legend(fontsize=9)
        ax3.grid(True, alpha=0.3)
        
        # 4. 电价和收益
        ax4 = axes[3]
        ax4_twin = ax4.twinx()
        
        line1 = ax4.plot(time_idx, plot_data['rrp'], label='RRP', 
                        linewidth=1.5, color='blue', alpha=0.7)
        line2 = ax4_twin.plot(time_idx, plot_data['net_revenue'], label='时段收益', 
                             linewidth=1.5, color='red', alpha=0.7)
        
        ax4.axhline(y=self.min_export_price*1000, color='orange', linestyle='--', 
                   linewidth=1, alpha=0.5, label=f'最低发电价({self.min_export_price*1000} AUD/MWh)')
        ax4.set_ylabel('电价 (AUD/kWh)', fontsize=11, color='blue')
        ax4_twin.set_ylabel('收益 (AUD)', fontsize=11, color='red')
        ax4.set_title('电价与收益', fontsize=12)
        ax4.tick_params(axis='y', labelcolor='blue')
        ax4_twin.tick_params(axis='y', labelcolor='red')
        ax4.grid(True, alpha=0.3)
        
        lines = line1 + line2
        labels = [l.get_label() for l in lines]
        ax4.legend(lines, labels, loc='upper right', fontsize=9)
        
        # 5. 累计收益
        ax5 = axes[4]
        cumulative = plot_data['net_revenue'].cumsum()
        ax5.plot(time_idx, cumulative, linewidth=2, color='darkgreen')
        ax5.fill_between(time_idx, 0, cumulative, alpha=0.3, color='green')
        ax5.set_xlabel('时间索引 (5分钟间隔)', fontsize=11)
        ax5.set_ylabel('累计收益 (AUD)', fontsize=11)
        ax5.set_title('累计收益', fontsize=12)
        ax5.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('daytime_storage_results.png', dpi=300, bbox_inches='tight')
        print("图表已保存为: daytime_storage_results.png")
        
        return fig


def main():
    """主函数"""
    print("\n" + "="*80)
    print("白天储能充电+辐照放电优化策略")
    print("="*80 + "\n")
    
    optimizer = DaytimeStorageOptimizer(
        lgc_price=10,  # AUD/MWh
        poa_to_power_ratio=3.79,
        battery_max_charge=250,  # kW
        battery_max_discharge=250,  # kW
        battery_capacity=1000,  # kWh
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        ramp_rate=16.67,  # kW/s
        min_export_price=-10,  # AUD/MWh
        initial_soc=0.0
    )
    
    # 加载全部30天数据
    data = optimizer.load_data('excel_1117版本.csv', max_periods=None)
    
    # 优化
    results = optimizer.optimize_daily()
    
    # 打印摘要
    optimizer.print_summary()
    
    # 保存结果
    optimizer.save_results('daytime_storage_results.csv')
    
    # 绘制图表
    optimizer.plot_results(days=3)
    
    print("\n✅ 优化完成!")


if __name__ == "__main__":
    main()

