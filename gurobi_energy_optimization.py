"""
使用Gurobi求解储能优化问题
比PuLP+CBC快10-100倍
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

try:
    import gurobipy as gp
    from gurobipy import GRB
    GUROBI_AVAILABLE = True
except ImportError:
    GUROBI_AVAILABLE = False
    print("警告: Gurobi未安装。请运行: pip install gurobipy")

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


class GurobiEnergyOptimizer:
    """使用Gurobi的储能优化器"""
    
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
        
        if not GUROBI_AVAILABLE:
            raise ImportError("Gurobi未安装，请先安装: pip install gurobipy")
        
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
        self.max_ramp = ramp_rate * 300  # 每5分钟最大变化
        
        print("="*80)
        print("Gurobi 储能优化模型")
        print("="*80)
        print(f"LGC价格: {lgc_price} AUD/MWh")
        print(f"电池容量: {battery_capacity} kWh")
        print(f"最大充电功率: {battery_max_charge} kW")
        print(f"最大放电功率: {battery_max_discharge} kW")
        print(f"充放电效率: {charge_efficiency*100}% / {discharge_efficiency*100}%")
        print(f"Ramp Rate: {ramp_rate} kW/s")
        print("="*80 + "\n")
    
    def load_data(self, csv_file, max_periods=None):
        """加载数据"""
        df = pd.read_csv(csv_file, encoding='utf-8')
        
        self.data = pd.DataFrame({
            'datetime': pd.to_datetime(df['日期']),
            'poa': df['POA'],
            'rrp': df['电价RRP'],
        })
        
        self.data['pv_power'] = self.data['poa'] * self.poa_to_power_ratio / 1000
        
        if max_periods:
            self.data = self.data.iloc[:max_periods].copy()
        
        self.n = len(self.data)
        
        print(f"数据加载完成: {self.n} 个时间段")
        print(f"时间范围: {self.data['datetime'].min()} 到 {self.data['datetime'].max()}")
        print(f"RRP范围: {self.data['rrp'].min():.4f} ~ {self.data['rrp'].max():.4f} AUD/kWh\n")
        
        return self.data
    
    def build_and_solve(self, time_limit=600, mip_gap=0.01, threads=None):
        """
        构建并求解优化模型
        
        参数:
        - time_limit: 时间限制（秒）
        - mip_gap: MIP优化间隙（0.01 = 1%）
        - threads: 使用的线程数（None=自动）
        """
        print("构建Gurobi优化模型...")
        start_time = datetime.now()
        
        # 创建模型
        model = gp.Model("energy_storage_optimization")
        
        # 关闭输出（可选）
        # model.setParam('OutputFlag', 0)
        
        # 设置参数
        model.setParam('TimeLimit', time_limit)
        model.setParam('MIPGap', mip_gap)
        if threads:
            model.setParam('Threads', threads)
        
        # === 决策变量 ===
        
        # 连续变量
        P_charge = model.addVars(self.n, lb=0, ub=self.P_charge_max, 
                                 name="P_charge")
        P_discharge = model.addVars(self.n, lb=0, ub=self.P_discharge_max, 
                                    name="P_discharge")
        P_grid_import = model.addVars(self.n, lb=0, name="P_grid_import")
        P_grid_export = model.addVars(self.n, lb=0, name="P_grid_export")
        SOC = model.addVars(self.n + 1, lb=0, ub=self.E_capacity, name="SOC")
        
        # 二进制变量（避免同时充放电）
        is_charging = model.addVars(self.n, vtype=GRB.BINARY, name="is_charging")
        is_discharging = model.addVars(self.n, vtype=GRB.BINARY, name="is_discharging")
        
        print(f"  变量数: {model.NumVars}")
        
        # === 目标函数 ===
        
        obj_expr = gp.LinExpr()
        
        for t in range(self.n):
            rrp = self.data.loc[t, 'rrp']
            pv = self.data.loc[t, 'pv_power']
            
            # 售电收益
            obj_expr += P_grid_export[t] * self.dt * rrp
            
            # 购电成本（负收益）
            obj_expr -= P_grid_import[t] * self.dt * rrp
            
            # LGC收益
            obj_expr += pv * self.dt * self.lgc_price
        
        model.setObjective(obj_expr, GRB.MAXIMIZE)
        
        # === 约束条件 ===
        
        # 1. 初始SOC
        model.addConstr(SOC[0] == self.initial_soc * self.E_capacity, "initial_soc")
        
        # 2. SOC动态平衡
        for t in range(self.n):
            model.addConstr(
                SOC[t+1] == SOC[t] 
                + P_charge[t] * self.dt * self.eta_c
                - P_discharge[t] * self.dt / self.eta_d,
                f"soc_balance_{t}"
            )
        
        # 3. 功率平衡
        for t in range(self.n):
            pv = self.data.loc[t, 'pv_power']
            model.addConstr(
                pv + P_discharge[t] + P_grid_import[t] 
                == P_charge[t] + P_grid_export[t],
                f"power_balance_{t}"
            )
        
        # 4. 不能同时充放电
        M = max(self.P_charge_max, self.P_discharge_max)
        
        for t in range(self.n):
            model.addConstr(
                is_charging[t] + is_discharging[t] <= 1,
                f"no_simul_charge_discharge_{t}"
            )
            model.addConstr(
                P_charge[t] <= M * is_charging[t],
                f"charge_logic_{t}"
            )
            model.addConstr(
                P_discharge[t] <= M * is_discharging[t],
                f"discharge_logic_{t}"
            )
        
        # 5. Ramp Rate约束
        for t in range(1, self.n):
            model.addConstr(
                P_grid_export[t] - P_grid_export[t-1] <= self.max_ramp,
                f"ramp_up_{t}"
            )
            model.addConstr(
                P_grid_export[t-1] - P_grid_export[t] <= self.max_ramp,
                f"ramp_down_{t}"
            )
        
        # 6. 最低放电价格约束（不低于-LGC）
        min_export_price = -self.lgc_price
        for t in range(self.n):
            rrp = self.data.loc[t, 'rrp']
            if rrp < min_export_price:
                model.addConstr(P_grid_export[t] == 0, f"min_price_{t}")
        
        print(f"  约束数: {model.NumConstrs}")
        print(f"  二进制变量数: {model.NumBinVars}")
        
        # === 求解 ===
        
        print("\n开始求解...")
        print(f"时间限制: {time_limit}秒")
        print(f"MIP间隙: {mip_gap*100}%")
        print("-"*80)
        
        model.optimize()
        
        solve_time = (datetime.now() - start_time).total_seconds()
        
        # === 结果 ===
        
        print("\n" + "="*80)
        
        if model.status == GRB.OPTIMAL:
            print("✅ 找到最优解!")
        elif model.status == GRB.TIME_LIMIT:
            print("⚠️  达到时间限制，返回当前最优解")
        elif model.status == GRB.INTERRUPTED:
            print("⚠️  求解被中断")
        else:
            print(f"❌ 求解失败，状态码: {model.status}")
            return None
        
        print(f"求解时间: {solve_time:.2f}秒")
        print(f"最优目标值: ${model.ObjVal:,.2f}")
        
        if model.status == GRB.TIME_LIMIT:
            print(f"MIP间隙: {model.MIPGap*100:.2f}%")
        
        print("="*80)
        
        # 保存模型和变量
        self.model = model
        self.P_charge = P_charge
        self.P_discharge = P_discharge
        self.P_grid_import = P_grid_import
        self.P_grid_export = P_grid_export
        self.SOC = SOC
        
        return model
    
    def extract_results(self):
        """提取优化结果"""
        if not hasattr(self, 'model'):
            print("错误: 请先运行 build_and_solve()")
            return None
        
        results = self.data.copy()
        
        # 提取变量值
        results['P_charge'] = [self.P_charge[t].X for t in range(self.n)]
        results['P_discharge'] = [self.P_discharge[t].X for t in range(self.n)]
        results['P_grid_import'] = [self.P_grid_import[t].X for t in range(self.n)]
        results['P_grid_export'] = [self.P_grid_export[t].X for t in range(self.n)]
        results['SOC'] = [self.SOC[t].X for t in range(self.n)]
        results['SOC_pct'] = results['SOC'] / self.E_capacity * 100
        
        # 计算收益
        results['export_revenue'] = results['P_grid_export'] * self.dt * results['rrp']
        results['import_cost'] = results['P_grid_import'] * self.dt * results['rrp']
        results['lgc_revenue'] = results['pv_power'] * self.dt * self.lgc_price
        results['net_revenue'] = results['export_revenue'] - results['import_cost'] + results['lgc_revenue']
        
        # 能量
        results['battery_charge_energy'] = results['P_charge'] * self.dt
        results['battery_discharge_energy'] = results['P_discharge'] * self.dt
        
        self.results = results
        return results
    
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
        
        total_pv = r['pv_power'].sum() * self.dt
        total_export = r['P_grid_export'].sum() * self.dt
        total_import = r['P_grid_import'].sum() * self.dt
        total_charge = r['battery_charge_energy'].sum()
        total_discharge = r['battery_discharge_energy'].sum()
        
        print(f"\n💰 总收益: ${total_revenue:,.2f}")
        print(f"   ├─ 售电收益: ${total_export_rev:,.2f}")
        print(f"   ├─ 购电成本: ${total_import_cost:,.2f}")
        print(f"   └─ LGC收益: ${total_lgc:,.2f}")
        
        print(f"\n⚡ 能量统计:")
        print(f"   ├─ 光伏总发电: {total_pv:,.2f} kWh")
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
        
        neg_periods = r[r['rrp'] < 0]
        if len(neg_periods) > 0:
            neg_import = neg_periods['P_grid_import'].sum() * self.dt
            neg_benefit = -neg_periods['import_cost'].sum()
            print(f"\n📉 负电价套利:")
            print(f"   ├─ 负电价时段: {len(neg_periods)} 个")
            print(f"   ├─ 购电量: {neg_import:,.2f} kWh")
            print(f"   └─ 套利收益: ${neg_benefit:,.2f}")
        
        print("="*80)
    
    def save_results(self, filename='gurobi_optimization_results.csv'):
        """保存结果"""
        if hasattr(self, 'results'):
            self.results.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"\n结果已保存到: {filename}")
    
    def plot_results(self, days=3):
        """绘制结果图表"""
        if not hasattr(self, 'results'):
            return
        
        from simplified_optimization import SimplifiedOptimizer
        
        # 复用绘图代码
        temp_opt = SimplifiedOptimizer()
        temp_opt.results = self.results
        temp_opt.n = len(self.results)
        temp_opt.dt = self.dt
        temp_opt.plot_results(days=days)


def main():
    """主函数"""
    
    # 检查Gurobi是否可用
    if not GUROBI_AVAILABLE:
        print("\n❌ Gurobi未安装!")
        print("\n请安装Gurobi:")
        print("  pip install gurobipy")
        print("\n如果没有许可证，Gurobi会使用受限免费版本（最多2000个变量）")
        print("对于学术用户，可以申请免费学术许可: https://www.gurobi.com/academia/")
        return
    
    print("\n" + "="*80)
    print("使用Gurobi进行储能优化")
    print("="*80 + "\n")
    
    # 创建优化器
    optimizer = GurobiEnergyOptimizer(
        lgc_price=10,
        poa_to_power_ratio=3.79,
        battery_max_charge=250,
        battery_max_discharge=250,
        battery_capacity=1000,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        ramp_rate=16.67,
        initial_soc=0.5
    )
    
    # 加载数据
    # 建议：先用较小数据集测试（如7天）
    data = optimizer.load_data('excel_1117版本.csv', max_periods=288*7)  # 7天数据
    
    # 构建并求解
    model = optimizer.build_and_solve(
        time_limit=600,  # 10分钟时间限制
        mip_gap=0.01,    # 1% MIP间隙
        threads=None     # 自动选择线程数
    )
    
    if model:
        # 提取结果
        results = optimizer.extract_results()
        
        # 打印摘要
        optimizer.print_summary()
        
        # 保存结果
        optimizer.save_results('gurobi_optimization_results.csv')
        
        # 绘制图表
        optimizer.plot_results(days=3)
        
        print("\n✅ 优化完成!")
    else:
        print("\n❌ 优化失败")


if __name__ == "__main__":
    main()


