"""
简化的储能优化模型 - 更快的求解速度
去掉二进制约束，通过惩罚项避免同时充放电
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

class SimplifiedOptimizer:
    def __init__(self,
                 lgc_price=10,  # AUD/MWh
                 poa_to_power_ratio=3.79,
                 battery_max_charge=250,  # kW
                 battery_max_discharge=250,  # kW
                 battery_capacity=1000,  # kWh
                 charge_efficiency=0.95,
                 discharge_efficiency=0.95,
                 ramp_rate=16.67,  # kW/s
                 initial_soc=0.5):
        
        self.lgc_price = lgc_price / 1000  # 转换为 AUD/kWh
        self.poa_to_power_ratio = poa_to_power_ratio
        self.P_charge_max = battery_max_charge
        self.P_discharge_max = battery_max_discharge
        self.E_capacity = battery_capacity
        self.eta_c = charge_efficiency
        self.eta_d = discharge_efficiency
        self.ramp_rate = ramp_rate
        self.initial_soc = initial_soc
        
        self.dt = 5 / 60  # 时间步长（小时）
        self.max_ramp = ramp_rate * 300  # 每5分钟最大变化(kW)
        
        print("="*80)
        print("简化储能优化模型参数")
        print("="*80)
        print(f"LGC价格: {lgc_price} AUD/MWh")
        print(f"POA转换比: {poa_to_power_ratio}")
        print(f"电池最大充电功率: {battery_max_charge} kW")
        print(f"电池最大放电功率: {battery_max_discharge} kW")
        print(f"电池容量: {battery_capacity} kWh")
        print(f"充电效率: {charge_efficiency*100}%")
        print(f"放电效率: {discharge_efficiency*100}%")
        print(f"Ramp Rate: {ramp_rate} kW/s")
        print(f"初始SOC: {initial_soc*100}%")
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
        
        # 限制数据量
        if max_periods:
            self.data = self.data.iloc[:max_periods].copy()
        
        self.n = len(self.data)
        
        print(f"数据加载完成: {self.n} 个时间段")
        print(f"时间范围: {self.data['datetime'].min()} 到 {self.data['datetime'].max()}")
        print(f"RRP范围: {self.data['rrp'].min():.4f} ~ {self.data['rrp'].max():.4f} AUD/kWh\n")
        
        return self.data
    
    def optimize_greedy(self):
        """
        使用贪心策略进行优化
        简单但有效的策略：
        1. 低电价（特别是负电价）时充电
        2. 高电价时放电
        3. 考虑SOC和功率约束
        4. 考虑ramp rate
        """
        print("使用贪心策略进行优化...")
        
        # 初始化结果
        results = self.data.copy()
        results['P_charge'] = 0.0
        results['P_discharge'] = 0.0
        results['P_grid_import'] = 0.0
        results['P_grid_export'] = 0.0
        results['SOC'] = 0.0
        results['SOC_pct'] = 0.0
        
        # 初始SOC
        soc = self.initial_soc * self.E_capacity
        prev_grid_export = 0.0  # 上一时刻的电网输出功率
        
        # 计算电价的统计信息用于决策
        rrp_25 = self.data['rrp'].quantile(0.25)  # 低价阈值
        rrp_75 = self.data['rrp'].quantile(0.75)  # 高价阈值
        min_export_price = -self.lgc_price  # 最低放电价格
        
        print(f"电价分位数: 25%={rrp_25:.4f}, 75%={rrp_75:.4f}")
        print(f"最低放电价格: {min_export_price:.4f} AUD/kWh\n")
        
        for t in range(self.n):
            pv = results.loc[t, 'pv_power']
            rrp = results.loc[t, 'rrp']
            
            P_charge = 0.0
            P_discharge = 0.0
            P_grid_import = 0.0
            P_grid_export = 0.0
            
            # 决策逻辑
            if rrp < 0:  # 负电价：最大化充电和电网导入
                # 电网充电（获得收益）
                P_grid_import = min(self.P_charge_max, 
                                   (self.E_capacity - soc) / (self.dt * self.eta_c))
                P_charge = P_grid_import
                
                # 光伏也优先充电，如果还有空间
                if P_charge < self.P_charge_max:
                    pv_to_battery = min(pv, self.P_charge_max - P_charge,
                                       (self.E_capacity - soc) / (self.dt * self.eta_c) - P_charge)
                    P_charge += pv_to_battery
                    pv_remaining = pv - pv_to_battery
                else:
                    pv_remaining = pv
                
                # 剩余光伏发电输出到电网（负电价也能获利）
                if pv_remaining > 0:
                    P_grid_export = pv_remaining
            
            elif rrp < rrp_25:  # 低电价：充电（如果SOC不高）
                if soc < 0.8 * self.E_capacity:
                    # 光伏充电
                    pv_to_battery = min(pv, self.P_charge_max,
                                       (self.E_capacity - soc) / (self.dt * self.eta_c))
                    P_charge = pv_to_battery
                    pv_remaining = pv - pv_to_battery
                    
                    # 如果价格非常低且SOC很低，考虑电网充电
                    if rrp < rrp_25 * 0.5 and soc < 0.3 * self.E_capacity:
                        grid_charge = min(self.P_charge_max - P_charge,
                                         (self.E_capacity - soc) / (self.dt * self.eta_c) - P_charge)
                        P_grid_import = grid_charge
                        P_charge += grid_charge
                    
                    # 剩余光伏输出到电网
                    P_grid_export = pv_remaining
                else:
                    # SOC已高，光伏直接输出
                    P_grid_export = pv
            
            elif rrp > rrp_75:  # 高电价：放电
                # 光伏全部输出
                P_grid_export = pv
                
                # 电池放电（如果SOC足够且价格高于最低价格）
                if soc > 0.1 * self.E_capacity and rrp > min_export_price:
                    P_discharge = min(self.P_discharge_max,
                                     soc * self.eta_d / self.dt)
                    P_grid_export += P_discharge
            
            else:  # 中等电价：光伏输出，电池保持
                if rrp > min_export_price:
                    P_grid_export = pv
            
            # 考虑ramp rate约束
            if abs(P_grid_export - prev_grid_export) > self.max_ramp:
                if P_grid_export > prev_grid_export:
                    P_grid_export = prev_grid_export + self.max_ramp
                else:
                    P_grid_export = max(0, prev_grid_export - self.max_ramp)
                
                # 调整其他功率以保持平衡
                available = pv + P_discharge
                if P_grid_export > available:
                    P_grid_export = available
            
            # 更新SOC
            soc += P_charge * self.dt * self.eta_c
            soc -= P_discharge * self.dt / self.eta_d
            soc = np.clip(soc, 0, self.E_capacity)
            
            # 保存结果
            results.loc[t, 'P_charge'] = P_charge
            results.loc[t, 'P_discharge'] = P_discharge
            results.loc[t, 'P_grid_import'] = P_grid_import
            results.loc[t, 'P_grid_export'] = P_grid_export
            results.loc[t, 'SOC'] = soc
            results.loc[t, 'SOC_pct'] = soc / self.E_capacity * 100
            
            prev_grid_export = P_grid_export
        
        self.results = results
        self._calculate_revenue()
        return results
    
    def _calculate_revenue(self):
        """计算收益"""
        r = self.results
        
        # 各项收益/成本
        r['export_revenue'] = r['P_grid_export'] * self.dt * r['rrp']
        r['import_cost'] = r['P_grid_import'] * self.dt * r['rrp']
        r['lgc_revenue'] = r['pv_power'] * self.dt * self.lgc_price
        r['net_revenue'] = r['export_revenue'] - r['import_cost'] + r['lgc_revenue']
        
        # 能量
        r['battery_charge_energy'] = r['P_charge'] * self.dt
        r['battery_discharge_energy'] = r['P_discharge'] * self.dt
        
        self.results = r
    
    def print_summary(self):
        """打印结果摘要"""
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
        
        print(f"\n💰 总收益: ${total_revenue:,.2f}")
        print(f"   ├─ 售电收益: ${total_export_rev:,.2f}")
        print(f"   ├─ 购电成本: ${total_import_cost:,.2f}")
        print(f"   └─ LGC收益: ${total_lgc:,.2f}")
        
        print(f"\n⚡ 能量统计:")
        print(f"   ├─ 光伏总发电: {total_pv_energy:,.2f} kWh")
        print(f"   ├─ 向电网售电: {total_export:,.2f} kWh")
        print(f"   ├─ 从电网购电: {total_import:,.2f} kWh")
        print(f"   ├─ 电池总充电: {total_charge:,.2f} kWh")
        print(f"   ├─ 电池总放电: {total_discharge:,.2f} kWh")
        if total_charge > 0:
            print(f"   └─ 往返效率: {total_discharge/total_charge*100:.2f}%")
        
        print(f"\n🔋 电池使用:")
        print(f"   ├─ 最终SOC: {r['SOC_pct'].iloc[-1]:.2f}%")
        print(f"   ├─ SOC范围: {r['SOC_pct'].min():.2f}% ~ {r['SOC_pct'].max():.2f}%")
        print(f"   ├─ 充电周期: {(r['P_charge'] > 1).sum()} 次")
        print(f"   └─ 放电周期: {(r['P_discharge'] > 1).sum()} 次")
        
        # 负电价套利统计
        neg_periods = r[r['rrp'] < 0]
        if len(neg_periods) > 0:
            neg_import = neg_periods['P_grid_import'].sum() * self.dt
            neg_benefit = -neg_periods['import_cost'].sum()
            print(f"\n📉 负电价套利:")
            print(f"   ├─ 负电价时段: {len(neg_periods)} 个")
            print(f"   ├─ 购电量: {neg_import:,.2f} kWh")
            print(f"   └─ 套利收益: ${neg_benefit:,.2f}")
        
        print("="*80)
    
    def save_results(self, filename='optimization_results.csv'):
        """保存结果"""
        self.results.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"\n结果已保存到: {filename}")
    
    def plot_results(self, days=3):
        """绘制结果图表"""
        periods_per_day = 288
        plot_periods = min(periods_per_day * days, self.n)
        plot_data = self.results.iloc[:plot_periods]
        
        fig, axes = plt.subplots(4, 1, figsize=(16, 12))
        fig.suptitle(f'储能优化结果（前{days}天）', fontsize=16, fontweight='bold')
        
        time_idx = range(len(plot_data))
        
        # 1. 功率分布
        ax1 = axes[0]
        ax1.plot(time_idx, plot_data['pv_power'], label='光伏发电', linewidth=1.5, alpha=0.8)
        ax1.plot(time_idx, plot_data['P_charge'], label='电池充电', linewidth=1.5, alpha=0.8)
        ax1.plot(time_idx, plot_data['P_discharge'], label='电池放电', linewidth=1.5, alpha=0.8)
        ax1.plot(time_idx, plot_data['P_grid_export'], label='电网输出', linewidth=1.5, alpha=0.8)
        ax1.plot(time_idx, plot_data['P_grid_import'], label='电网导入', linewidth=1.5, alpha=0.8)
        ax1.set_ylabel('功率 (kW)', fontsize=11)
        ax1.set_title('功率分布', fontsize=12)
        ax1.legend(loc='upper right', ncol=5, fontsize=9)
        ax1.grid(True, alpha=0.3)
        
        # 2. SOC
        ax2 = axes[1]
        ax2.plot(time_idx, plot_data['SOC_pct'], linewidth=2, color='green')
        ax2.fill_between(time_idx, 0, plot_data['SOC_pct'], alpha=0.3, color='green')
        ax2.set_ylabel('SOC (%)', fontsize=11)
        ax2.set_title('电池荷电状态', fontsize=12)
        ax2.set_ylim([0, 100])
        ax2.grid(True, alpha=0.3)
        
        # 3. 电价和收益
        ax3 = axes[2]
        ax3_twin = ax3.twinx()
        
        line1 = ax3.plot(time_idx, plot_data['rrp'], label='RRP', 
                        linewidth=1.5, color='blue', alpha=0.7)
        line2 = ax3_twin.plot(time_idx, plot_data['net_revenue'], label='时段收益', 
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
        ax3.legend(lines, labels, loc='upper right', fontsize=9)
        
        # 4. 累计收益
        ax4 = axes[3]
        cumulative = plot_data['net_revenue'].cumsum()
        ax4.plot(time_idx, cumulative, linewidth=2, color='darkgreen')
        ax4.fill_between(time_idx, 0, cumulative, alpha=0.3, color='green')
        ax4.set_xlabel('时间索引 (5分钟间隔)', fontsize=11)
        ax4.set_ylabel('累计收益 (AUD)', fontsize=11)
        ax4.set_title('累计收益', fontsize=12)
        ax4.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('optimization_results.png', dpi=300, bbox_inches='tight')
        print("图表已保存为: optimization_results.png")
        
        return fig


def main():
    """主函数"""
    print("\n" + "="*80)
    print("储能电站完美收益优化 - 贪心算法")
    print("="*80 + "\n")
    
    # 创建优化器（所有参数都可以调整）
    optimizer = SimplifiedOptimizer(
        lgc_price=10,  # AUD/MWh
        poa_to_power_ratio=3.79,
        battery_max_charge=250,  # kW
        battery_max_discharge=250,  # kW
        battery_capacity=1000,  # kWh
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        ramp_rate=16.67,  # kW/s
        initial_soc=0.5
    )
    
    # 加载数据（使用全部数据）
    data = optimizer.load_data('excel_1117版本.csv', max_periods=None)
    
    # 优化
    start = datetime.now()
    results = optimizer.optimize_greedy()
    elapsed = (datetime.now() - start).total_seconds()
    
    print(f"优化完成，耗时: {elapsed:.2f}秒")
    
    # 打印摘要
    optimizer.print_summary()
    
    # 保存结果
    optimizer.save_results('optimization_results.csv')
    
    # 绘制图表
    optimizer.plot_results(days=3)
    
    print("\n✅ 所有任务完成!")


if __name__ == "__main__":
    main()

