"""
使用完整参数运行优化：包含电网接入功率限制
"""

from daytime_storage_optimization import DaytimeStorageOptimizer

# 需要修改DaytimeStorageOptimizer类以支持NEL和NIL限制
class GridLimitedOptimizer(DaytimeStorageOptimizer):
    """包含电网功率限制的优化器"""
    
    def __init__(self, nel=4440, nil=670, **kwargs):
        super().__init__(**kwargs)
        self.nel = nel  # Network Export Level (kW)
        self.nil = nil  # Network Import Level (kW)
        
        print(f"电网接入限制:")
        print(f"  - NEL (向电网输出): {nel} kW")
        print(f"  - NIL (从电网导入): {nil} kW")
        print("="*80 + "\n")
    
    def _optimize_single_day(self, day_data, day_idx):
        """优化单日策略（考虑电网功率限制）"""
        day_results = day_data.copy()
        
        # 初始SOC
        if day_idx == 0:
            soc = self.initial_soc * self.E_capacity
        else:
            if hasattr(self, '_prev_day_soc'):
                soc = self._prev_day_soc
            else:
                soc = self.initial_soc * self.E_capacity
        
        # === 阶段1: 识别白天充电时段 ===
        daytime_mask = day_results['poa'] > 10
        daytime_periods = day_results[daytime_mask].copy()
        
        if len(daytime_periods) == 0:
            day_results['SOC'] = soc
            day_results['SOC_pct'] = soc / self.E_capacity * 100
            return day_results
        
        # 按RRP排序
        daytime_periods_sorted = daytime_periods.sort_values('rrp')
        
        # === 阶段2: 选择充电时段 ===
        charging_periods = set()
        target_charge_energy = self.E_capacity - soc
        accumulated_charge = 0.0
        
        for idx, row in daytime_periods_sorted.iterrows():
            if accumulated_charge >= target_charge_energy:
                break
            
            pv_power = row['pv_power']
            
            # 考虑电网导入限制(NIL)和电池充电功率限制
            # 充电功率受限于：min(电池最大充电, 光伏+NIL)
            max_charge_this_period = min(
                self.P_charge_max * self.dt,
                target_charge_energy - accumulated_charge
            )
            
            pv_energy = pv_power * self.dt
            
            if pv_energy >= max_charge_this_period:
                accumulated_charge += max_charge_this_period
            else:
                accumulated_charge += pv_energy
            
            charging_periods.add(idx)
            
            if accumulated_charge >= target_charge_energy * 0.999:
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
                
                available_capacity = self.E_capacity - soc
                max_charge_power = min(self.P_charge_max, 
                                      available_capacity / (self.dt * self.eta_c))
                
                if pv_power >= max_charge_power:
                    # 光伏足够充满电池
                    P_charge = max_charge_power
                    excess_power = pv_power - max_charge_power
                    
                    # 多余电量：考虑NEL限制
                    if rrp > self.min_export_price:
                        P_grid_export = min(excess_power, self.nel)  # 受NEL限制
                        if excess_power > self.nel:
                            P_pv_curtail = excess_power - self.nel
                    else:
                        P_pv_curtail = excess_power
                
                else:
                    # 光伏不足，需要电网补充
                    pv_to_battery = pv_power
                    
                    # 从电网补充：受NIL限制
                    nil_needed = max_charge_power - pv_to_battery
                    nil_power = min(nil_needed, self.nil)  # 受NIL限制
                    
                    P_charge = pv_to_battery + nil_power
                    P_grid_import = nil_power
            
            elif poa > 5:
                # === 白天非充电时段：光伏发电 ===
                if rrp > self.min_export_price:
                    # 受NEL限制
                    P_grid_export = min(pv_power, self.nel)
                    if pv_power > self.nel:
                        P_pv_curtail = pv_power - self.nel
                    action = 'pv_export'
                else:
                    P_pv_curtail = pv_power
                    action = 'curtail'
            
            else:
                # === 夜间时段：考虑放电 ===
                if rrp > day_results['rrp'].quantile(0.75) and soc > 0.1 * self.E_capacity:
                    max_discharge_power = min(self.P_discharge_max,
                                             soc * self.eta_d / self.dt)
                    P_discharge = max_discharge_power
                    
                    # 放电输出：受NEL限制
                    P_grid_export = min(P_discharge, self.nel)
                    
                    # 如果NEL限制了输出，调整实际放电量
                    if P_grid_export < P_discharge:
                        P_discharge = P_grid_export
                    
                    action = 'discharging'
            
            # Ramp rate约束（仅针对电网输出）
            if abs(P_grid_export - prev_grid_export) > self.max_ramp:
                if P_grid_export > prev_grid_export:
                    P_grid_export = prev_grid_export + self.max_ramp
                else:
                    P_grid_export = max(0, prev_grid_export - self.max_ramp)
            
            # 更新SOC
            soc += P_charge * self.dt * self.eta_c
            soc -= P_discharge * self.dt / self.eta_d
            soc = max(0, min(soc, self.E_capacity))
            
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
        
        # 保存最后的SOC
        self._prev_day_soc = soc
        
        return day_results


def main():
    """使用完整参数运行"""
    print("\n" + "="*80)
    print("白天储能充电优化 - 完整参数（含电网限制）")
    print("="*80 + "\n")
    
    # 完整参数
    optimizer = GridLimitedOptimizer(
        # 电网接入限制
        nel=4440,  # kW - Network Export Level
        nil=670,   # kW - Network Import Level
        
        # 其他参数
        lgc_price=10,  # AUD/MWh
        poa_to_power_ratio=3.79,
        battery_max_charge=2752,  # kW
        battery_max_discharge=2752,  # kW
        battery_capacity=5504,  # kWh
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        ramp_rate=16.67,  # kW/s
        min_export_price=-10,  # AUD/MWh
        initial_soc=0.0
    )
    
    # 加载数据
    print("正在加载数据...")
    data = optimizer.load_data('excel_1117版本.csv', max_periods=None)
    
    # 优化
    print("开始优化...")
    results = optimizer.optimize_daily()
    
    # 打印摘要
    optimizer.print_summary()
    
    # 额外统计：电网限制影响
    r = optimizer.results
    print("\n" + "="*80)
    print("电网限制影响分析")
    print("="*80)
    
    # NIL限制影响
    charging_periods = r[r['P_charge'] > 0]
    nil_limited = charging_periods[charging_periods['P_grid_import'] >= optimizer.nil * 0.99]
    print(f"\n📥 NIL限制 ({optimizer.nil} kW):")
    print(f"   ├─ 受限时段: {len(nil_limited)} 个")
    print(f"   ├─ 实际最大导入: {r['P_grid_import'].max():.2f} kW")
    print(f"   └─ 平均导入: {r[r['P_grid_import'] > 0]['P_grid_import'].mean():.2f} kW")
    
    # NEL限制影响
    export_periods = r[r['P_grid_export'] > 0]
    nel_limited = export_periods[export_periods['P_grid_export'] >= optimizer.nel * 0.99]
    print(f"\n📤 NEL限制 ({optimizer.nel} kW):")
    print(f"   ├─ 受限时段: {len(nel_limited)} 个")
    print(f"   ├─ 实际最大输出: {r['P_grid_export'].max():.2f} kW")
    print(f"   └─ 平均输出: {r[r['P_grid_export'] > 0]['P_grid_export'].mean():.2f} kW")
    
    # 光伏受NEL限制的弃光
    nel_curtail = r[(r['pv_power'] > optimizer.nel) & (r['poa'] > 5)]
    if len(nel_curtail) > 0:
        print(f"\n⚠️  因NEL限制的弃光:")
        print(f"   └─ 时段数: {len(nel_curtail)} 个")
    
    print("="*80)
    
    # 保存结果
    optimizer.save_results('grid_limited_results.csv')
    
    # 绘制图表
    optimizer.plot_results(days=3)
    
    print("\n✅ 优化完成!")
    print(f"\n📊 参数汇总:")
    print(f"   电池容量:      5,504 kWh")
    print(f"   电池充电功率:  2,752 kW")
    print(f"   电池放电功率:  2,752 kW")
    print(f"   电网导入(NIL): 670 kW  ⚠️ (限制充电速度)")
    print(f"   电网输出(NEL): 4,440 kW")
    print(f"   最低发电价格:  -10 AUD/MWh")


if __name__ == "__main__":
    main()


