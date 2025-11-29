#!/usr/bin/env python3
"""
AEMO电池储能优化系统 - 增强Web版本 (Streamlit)
支持天、月、季度、半年、年等不同时间周期的分析
"""

import streamlit as st
import pandas as pd
import glob
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, time as dt_time
from typing import List, Dict, Tuple, Optional
import pulp
import calendar

# 页面配置
st.set_page_config(
    page_title="AEMO电池储能优化系统",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

@st.cache_data
def assign_cycle_date(ts_str: str) -> str:
    """分配周期日期"""
    ts = pd.to_datetime(ts_str)
    if ts.time() >= dt_time(23, 0):
        return str(ts.normalize().date())
    elif ts.time() < dt_time(8, 0):
        return str((ts - pd.Timedelta(days=1)).normalize().date())
    else:
        return str(ts.normalize().date())

@st.cache_data
def load_all_data():
    """加载所有数据"""
    try:
        # 查找所有z0Fast文件
        pattern = "AEMO_23to08_with_opt_*_z0Fast.xlsx"
        excel_files = sorted(glob.glob(pattern))
        
        if not excel_files:
            st.error("未找到数据文件！请确保AEMO_23to08_with_opt_*_z0Fast.xlsx文件存在。")
            return None
        
        st.info(f"正在加载 {len(excel_files)} 个数据文件...")
        
        # 加载所有数据
        all_dataframes = []
        progress_bar = st.progress(0)
        
        for i, file in enumerate(excel_files):
            try:
                df = pd.read_excel(file, sheet_name="23to08_opt")
                # 重命名列
                df = df.rename(columns={
                    "时间": "Timestamp",
                    "电价(RRP)": "Price_RRP", 
                    "阶段": "Phase",
                    "z值": "Z_Value",
                    "电量(kWh)": "Energy_kWh",
                    "累计电量(kWh)": "Cumulative_Energy_kWh",
                    "成本/收益": "Cost_Revenue",
                    "周期总收益": "Cycle_Total_Revenue"
                })
                all_dataframes.append(df)
                progress_bar.progress((i + 1) / len(excel_files))
            except Exception as e:
                st.warning(f"加载 {file} 失败: {e}")
        
        if not all_dataframes:
            st.error("无法加载任何数据文件！")
            return None
        
        # 合并数据
        merged_df = pd.concat(all_dataframes, ignore_index=True)
        merged_df["Timestamp"] = pd.to_datetime(merged_df["Timestamp"])
        merged_df = merged_df.sort_values("Timestamp").reset_index(drop=True)
        
        # 添加周期信息
        merged_df["Cycle_Date"] = merged_df["Timestamp"].astype(str).apply(assign_cycle_date)
        merged_df["Cycle_Date"] = pd.to_datetime(merged_df["Cycle_Date"])
        
        # 添加状态列：根据能量值判断工作状态
        def determine_status(row):
            energy = row.get("Energy_kWh", 0)
            phase = row.get("Phase", "")
            if abs(energy) > 1e-6:  # 有能量交换
                if phase == "charge":
                    return "充电"
                elif phase == "discharge":
                    return "放电"
                else:
                    return "工作"  # 未知阶段但有能量
            else:
                return "未工作"  # 没有能量交换
        
        merged_df["Status"] = merged_df.apply(determine_status, axis=1)
        
        st.success(f"数据加载完成！共 {len(merged_df)} 行数据，{merged_df['Cycle_Date'].nunique()} 个日周期")
        return merged_df
        
    except Exception as e:
        st.error(f"数据加载失败: {str(e)}")
        return None

def get_period_boundaries(period_type: str, selected_period: str) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """根据周期类型和选择的周期，返回开始和结束时间"""
    if period_type == "天":
        # 单日：从选定日期的23:00到次日08:00
        date = pd.to_datetime(selected_period)
        start_time = pd.Timestamp(year=date.year, month=date.month, day=date.day, hour=23, minute=0)
        end_time = start_time + pd.Timedelta(hours=9)  # 到次日08:00
        return start_time, end_time
    
    elif period_type == "月":
        # 月度：从上月最后一天23:00到本月最后一天08:00
        year_month = pd.Period(selected_period)
        year, month = year_month.year, year_month.month
        
        # 计算上一个月的最后一天
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1
        
        prev_month_last_day = pd.Timestamp(year=prev_year, month=prev_month, day=1) + pd.offsets.MonthEnd(0)
        start_time = pd.Timestamp(year=prev_month_last_day.year, month=prev_month_last_day.month, 
                                 day=prev_month_last_day.day, hour=23, minute=0)
        
        # 本月最后一天08:00
        month_last_day = pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)
        end_time = pd.Timestamp(year=month_last_day.year, month=month_last_day.month, 
                               day=month_last_day.day, hour=8, minute=0)
        
        return start_time, end_time
    
    elif period_type == "季度":
        # 季度：从上季度最后一天23:00到本季度最后一天08:00
        year_quarter = pd.Period(selected_period)
        year, quarter = year_quarter.year, year_quarter.quarter
        
        # 计算季度的第一个月和最后一个月
        first_month = (quarter - 1) * 3 + 1
        last_month = quarter * 3
        
        # 上季度最后一天23:00
        if quarter == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, (quarter - 2) * 3 + 3
        
        prev_quarter_last_day = pd.Timestamp(year=prev_year, month=prev_month, day=1) + pd.offsets.MonthEnd(0)
        start_time = pd.Timestamp(year=prev_quarter_last_day.year, month=prev_quarter_last_day.month,
                                 day=prev_quarter_last_day.day, hour=23, minute=0)
        
        # 本季度最后一天08:00
        quarter_last_day = pd.Timestamp(year=year, month=last_month, day=1) + pd.offsets.MonthEnd(0)
        end_time = pd.Timestamp(year=quarter_last_day.year, month=quarter_last_day.month,
                               day=quarter_last_day.day, hour=8, minute=0)
        
        return start_time, end_time
    
    elif period_type == "半年":
        # 半年：从上半年最后一天23:00到本半年最后一天08:00
        year = int(selected_period[:4])
        half = int(selected_period[-1])
        
        if half == 1:  # 上半年
            # 从上年12月31日23:00到6月30日08:00
            start_time = pd.Timestamp(year=year-1, month=12, day=31, hour=23, minute=0)
            end_time = pd.Timestamp(year=year, month=6, day=30, hour=8, minute=0)
        else:  # 下半年
            # 从6月30日23:00到12月31日08:00
            start_time = pd.Timestamp(year=year, month=6, day=30, hour=23, minute=0)
            end_time = pd.Timestamp(year=year, month=12, day=31, hour=8, minute=0)
        
        return start_time, end_time
    
    elif period_type == "年":
        # 年度：从上年12月31日23:00到本年12月31日08:00
        year = int(selected_period)
        start_time = pd.Timestamp(year=year-1, month=12, day=31, hour=23, minute=0)
        end_time = pd.Timestamp(year=year, month=12, day=31, hour=8, minute=0)
        return start_time, end_time
    
    # 默认返回
    return pd.Timestamp.now(), pd.Timestamp.now()

def get_available_periods(df: pd.DataFrame, period_type: str) -> List[str]:
    """获取数据中实际可用的周期"""
    min_time = df["Timestamp"].min()
    max_time = df["Timestamp"].max()
    
    periods = []
    
    if period_type == "天":
        # 获取所有日周期
        unique_cycles = sorted(df["Cycle_Date"].dt.date.unique())
        return [str(date) for date in unique_cycles]
    
    elif period_type == "月":
        # 从2023-12开始到数据最后一个月
        start_year, start_month = 2023, 12
        end_year, end_month = max_time.year, max_time.month
        
        current_year, current_month = start_year, start_month
        while (current_year, current_month) <= (end_year, end_month):
            periods.append(f"{current_year}-{current_month:02d}")
            if current_month == 12:
                current_year += 1
                current_month = 1
            else:
                current_month += 1
        
        return periods
    
    elif period_type == "季度":
        # 从2024Q1开始，根据实际数据范围确定可用季度
        periods = ["2024Q1", "2024Q2", "2024Q3", "2024Q4"]
        
        # 2025年的季度：数据到8月，所以Q1、Q2、Q3可用
        if max_time.year >= 2025:
            if max_time.month >= 3:  # Q1完整
                periods.append("2025Q1")
            if max_time.month >= 6:  # Q2完整
                periods.append("2025Q2")
            if max_time.month >= 8:  # Q3部分可用（到8月）
                periods.append("2025Q3")
        
        return periods
    
    elif period_type == "半年":
        # 从2024H1开始，2025年数据到8月，所以2025H1可用但2025H2不可用
        periods = ["2024H1", "2024H2"]
        if max_time.year >= 2025 and max_time.month >= 6:
            periods.append("2025H1")
        return periods
    
    elif period_type == "年":
        # 从2024年开始，2025年数据不完整（只到8月）
        periods = ["2024"]
        # 2025年数据不完整，不包含在年度分析中
        return periods
    
    return []

def filter_data_by_period_boundaries(df: pd.DataFrame, period_type: str, selected_period: str) -> pd.DataFrame:
    """根据时间边界筛选数据"""
    start_time, end_time = get_period_boundaries(period_type, selected_period)
    
    # 筛选在时间范围内的数据
    filtered_df = df[(df["Timestamp"] >= start_time) & (df["Timestamp"] <= end_time)].copy()
    
    return filtered_df

def solve_cycle_with_z(charge_prices: List[float], discharge_prices: List[float], 
                      z: float, charge_rate: float = 55.83, discharge_rate: float = 200.0, 
                      max_capacity: float = 5000.0) -> Tuple[List[float], List[float], float]:
    """使用线性规划求解给定Z值下的最优分配"""
    try:
        # 创建线性规划问题
        prob = pulp.LpProblem("Battery_Optimization", pulp.LpMaximize)
        
        n_charge = len(charge_prices)
        n_discharge = len(discharge_prices)
        
        # 决策变量：充电时段i到放电时段j的能量分配
        x = {}
        for i in range(n_charge):
            for j in range(n_discharge):
                if discharge_prices[j] > charge_prices[i] + z:  # 只有满足阈值条件才创建变量
                    x[i, j] = pulp.LpVariable(f"x_{i}_{j}", 0, None)
        
        if not x:  # 没有可行的分配
            return [0.0] * n_charge, [0.0] * n_discharge, 0.0
        
        # 目标函数：最大化总利润
        # 单位换算：RRP是AUD/MWh，变量单位是kWh，需要除以1000转换为MWh
        profit_terms = []
        for (i, j), var in x.items():
            profit_per_mwh = discharge_prices[j] - charge_prices[i]  # AUD/MWh
            profit_terms.append(profit_per_mwh * var / 1000.0)  # AUD/MWh × kWh/1000 = AUD
        
        if profit_terms:
            prob += pulp.lpSum(profit_terms)
        
        # 约束条件
        # 1. 充电时段容量约束
        for i in range(n_charge):
            charge_vars = [x[i, j] for j in range(n_discharge) if (i, j) in x]
            if charge_vars:
                prob += pulp.lpSum(charge_vars) <= charge_rate
        
        # 2. 放电时段容量约束
        for j in range(n_discharge):
            discharge_vars = [x[i, j] for i in range(n_charge) if (i, j) in x]
            if discharge_vars:
                prob += pulp.lpSum(discharge_vars) <= discharge_rate
        
        # 3. 储能容量约束 - 确保任何时刻的累计储能不超过最大容量
        # 总充电量不能超过最大储能容量
        all_charge_vars = [x[i, j] for i in range(n_charge) for j in range(n_discharge) if (i, j) in x]
        if all_charge_vars:
            prob += pulp.lpSum(all_charge_vars) <= max_capacity
        
        # 求解
        prob.solve(pulp.PULP_CBC_CMD(msg=0))
        
        if prob.status != pulp.LpStatusOptimal:
            return [0.0] * n_charge, [0.0] * n_discharge, 0.0
        
        # 提取结果
        charge_energy = [0.0] * n_charge
        discharge_energy = [0.0] * n_discharge
        total_profit = 0.0
        
        for (i, j), var in x.items():
            if var.varValue and var.varValue > 1e-6:
                energy = var.varValue
                charge_energy[i] += energy
                discharge_energy[j] += energy
                profit_per_mwh = discharge_prices[j] - charge_prices[i]  # AUD/MWh
                energy_mwh = energy / 1000.0  # 转换为MWh
                total_profit += profit_per_mwh * energy_mwh  # AUD
        
        return charge_energy, discharge_energy, total_profit
        
    except Exception as e:
        st.error(f"求解过程出错: {e}")
        return [0.0] * len(charge_prices), [0.0] * len(discharge_prices), 0.0

def update_period_data_with_z(period_data: pd.DataFrame, z_value: float, period_type: str,
                             charge_rate: float = 55.83, discharge_rate: float = 200.0, 
                             max_capacity: float = 5000.0) -> pd.DataFrame:
    """根据新的Z值更新周期数据（支持多天数据）"""
    updated_data = period_data.copy()
    
    if period_type == "天":
        # 单天处理（原逻辑）
        return update_single_cycle_with_z(updated_data, z_value, charge_rate, discharge_rate, max_capacity)
    else:
        # 多天处理：按日周期分组处理
        unique_cycles = updated_data["Cycle_Date"].unique()
        all_updated_data = []
        
        for cycle_date in unique_cycles:
            cycle_data = updated_data[updated_data["Cycle_Date"] == cycle_date].copy()
            updated_cycle = update_single_cycle_with_z(cycle_data, z_value, charge_rate, discharge_rate, max_capacity)
            all_updated_data.append(updated_cycle)
        
        return pd.concat(all_updated_data, ignore_index=True)

def update_single_cycle_with_z(cycle_data: pd.DataFrame, z_value: float, 
                               charge_rate: float = 55.83, discharge_rate: float = 200.0, 
                               max_capacity: float = 5000.0) -> pd.DataFrame:
    """更新单个日周期的数据"""
    updated_data = cycle_data.copy()
    
    # 提取充电和放电数据
    charge_data = updated_data[updated_data["Phase"] == "charge"]
    discharge_data = updated_data[updated_data["Phase"] == "discharge"]
    
    if len(charge_data) == 0 or len(discharge_data) == 0:
        return updated_data
    
    # 获取价格数据
    charge_prices = charge_data["Price_RRP"].tolist()
    discharge_prices = discharge_data["Price_RRP"].tolist()
    
    # 求解优化问题
    charge_energy, discharge_energy, total_profit = solve_cycle_with_z(
        charge_prices, discharge_prices, z_value, charge_rate, discharge_rate, max_capacity)
    
    # 重置所有能量值和状态
    updated_data["Z_Value"] = z_value
    updated_data["Energy_kWh"] = 0.0
    updated_data["Cost_Revenue"] = 0.0
    updated_data["Status"] = "未工作"  # 初始化所有时段为未工作
    
    # 更新充电数据
    charge_indices = charge_data.index
    for i, idx in enumerate(charge_indices):
        if i < len(charge_energy):
            energy = charge_energy[i]
            price = updated_data.at[idx, "Price_RRP"]
            updated_data.at[idx, "Energy_kWh"] = energy
            updated_data.at[idx, "Cost_Revenue"] = -price * energy / 1000
            # 更新状态：如果有充电能量则显示"充电"，否则保持"未工作"
            if energy > 1e-6:  # 大于极小值才算有效充电
                updated_data.at[idx, "Status"] = "充电"
    
    # 更新放电数据
    discharge_indices = discharge_data.index
    for i, idx in enumerate(discharge_indices):
        if i < len(discharge_energy):
            energy = -discharge_energy[i]  # 放电为负值
            price = updated_data.at[idx, "Price_RRP"]
            updated_data.at[idx, "Energy_kWh"] = energy
            updated_data.at[idx, "Cost_Revenue"] = -price * energy / 1000
            # 更新状态：如果有放电能量则显示"放电"，否则保持"未工作"
            if discharge_energy[i] > 1e-6:  # 大于极小值才算有效放电
                updated_data.at[idx, "Status"] = "放电"
    
    # 计算累计电量
    cumulative_energy = 0
    for idx in updated_data.index:
        energy = updated_data.at[idx, "Energy_kWh"]
        cumulative_energy = max(0, min(max_capacity, cumulative_energy + energy))
        updated_data.at[idx, "Cumulative_Energy_kWh"] = cumulative_energy
    
    # 设置周期总收益
    updated_data["Cycle_Total_Revenue"] = total_profit
    
    return updated_data

def get_period_display_name(period_type: str, selected_period: str) -> str:
    """获取周期的显示名称"""
    if period_type == "天":
        return f"日周期: {selected_period}"
    elif period_type == "月":
        return f"月周期: {selected_period}"
    elif period_type == "季度":
        return f"季度周期: {selected_period}"
    elif period_type == "半年":
        return f"半年周期: {selected_period}"
    elif period_type == "年":
        return f"年度周期: {selected_period}"
    return selected_period





def main():
    """主函数"""
    st.title("⚡ AEMO电池储能优化系统 - 增强版")
    
    # 添加自定义CSS来调整整体页面字体大小
    st.markdown("""
    <style>
    /* 调整metric数字字体大小 */
    [data-testid="metric-container"] [data-testid="metric-value"] {
        font-size: 1.0rem !important;
    }
    
    /* 全局字体缩小 */
    .main .block-container {
        font-size: 0.85rem;
    }
    
    /* 调整表格字体 */
    .dataframe {
        font-size: 0.8rem !important;
    }
    
    /* 调整侧边栏字体 */
    .css-1d391kg {
        font-size: 0.85rem;
    }
    
    /* 调整selectbox和其他控件字体 */
    .stSelectbox > div > div {
        font-size: 0.85rem;
    }
    
    /* 调整metric标签字体 */
    [data-testid="metric-container"] [data-testid="metric-label"] {
        font-size: 1.2rem !important;
    }
    
    /* 调整subheader字体 */
    .css-10trblm {
        font-size: 1.1rem !important;
    }
    
    /* 调整普通文本 */
    p, div, span {
        font-size: 0.85rem;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 周期类型选择（顶部）
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        period_type = st.selectbox(
            "🕐 选择分析周期类型",
            ["天", "月", "季度", "半年", "年"],
            index=0,
            help="选择不同的时间周期进行分析"
        )
    
    st.markdown("---")
    
    # 加载数据
    if 'all_data' not in st.session_state:
        with st.spinner("正在加载数据..."):
            st.session_state.all_data = load_all_data()
    
    all_data = st.session_state.all_data
    if all_data is None:
        st.stop()
    
    # 侧边栏控制
    st.sidebar.header("🎛️ 控制面板")
    # 刷新数据按钮：清空缓存并重新加载Excel文件
    if st.sidebar.button("🔁 刷新数据", help="清空缓存并重新加载所有Excel数据文件"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.session_state.pop('all_data', None)
        st.session_state.pop('current_period_data', None)
        st.success("数据缓存已清空，将重新加载数据……")
    
    # 获取周期选项
    period_options = get_available_periods(all_data, period_type)
    
    if not period_options:
        st.error("没有找到可用的周期数据")
        st.stop()
    
    # 周期选择
    selected_period = st.sidebar.selectbox(
        f"📅 选择{period_type}",
        period_options,
        index=0
    )
    
    # 计算最优Z值（仅对季度、半年、年进行计算）
    optimal_z = None
    optimal_profit = None
    

    
    # Z值输入
    z_value = st.sidebar.number_input(
        "⚡ Z值",
        min_value=0.0,
        value=st.session_state.get('z_value', 0.0),
        step=0.5,
        format="%.1f"
    )
    
    # 电池参数设置
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔋 电池参数设置")
    
    # 充电功率
    charge_power = st.sidebar.number_input(
        "⬆️ 充电功率 (kW)",
        min_value=1.0,
        value=st.session_state.get('charge_power', 670.0),
        step=10.0,
        format="%.1f",
        help="最大充电功率"
    )
    
    # 放电功率  
    discharge_power = st.sidebar.number_input(
        "⬇️ 放电功率 (kW)",
        min_value=1.0,
        value=st.session_state.get('discharge_power', 2400.0),
        step=50.0,
        format="%.1f",
        help="最大放电功率"
    )
    
    # 将功率转换为每5分钟时段的能量 (kW * 5min / 60min = kWh)
    charge_rate = charge_power * 5 / 60  # kW * (5/60) = kWh per 5-minute period
    discharge_rate = discharge_power * 5 / 60
    
    # 最大累计电量
    max_capacity = st.sidebar.number_input(
        "📦 最大储能容量 (kWh)",
        min_value=1.0,
        value=st.session_state.get('max_capacity', 5000.0),
        step=10.0,
        format="%.1f",
        help="电池最大储能容量"
    )
    
    # 保存参数到session state
    st.session_state['z_value'] = z_value
    st.session_state['charge_power'] = charge_power
    st.session_state['discharge_power'] = discharge_power
    st.session_state['max_capacity'] = max_capacity
    
    # 获取选定周期的数据
    period_data = filter_data_by_period_boundaries(all_data, period_type, selected_period)
    
    if len(period_data) == 0:
        st.error("选定周期没有数据")
        st.stop()
    
    # 根据Z值更新数据
    if st.sidebar.button("🔄 重新计算", type="primary"):
        with st.spinner("正在计算最优策略..."):
            period_data = update_period_data_with_z(period_data, z_value, period_type, 
                                                  charge_rate, discharge_rate, max_capacity)
            st.session_state.current_period_data = period_data
    
    # 使用缓存的数据或原始数据
    if 'current_period_data' in st.session_state:
        display_data = st.session_state.current_period_data
    else:
        display_data = update_period_data_with_z(period_data, z_value, period_type,
                                               charge_rate, discharge_rate, max_capacity)
        st.session_state.current_period_data = display_data
    
    # 计算统计信息
    if period_type == "天":
        # 单日统计
        total_profit = display_data["Cycle_Total_Revenue"].iloc[0] if len(display_data) > 0 else 0
        total_charge = display_data[display_data["Phase"] == "charge"]["Energy_kWh"].sum()
        total_discharge = -display_data[display_data["Phase"] == "discharge"]["Energy_kWh"].sum()
        max_cumulative = display_data["Cumulative_Energy_kWh"].max()
        cycle_count = 1
    else:
        # 多日统计
        daily_profits = display_data.groupby("Cycle_Date")["Cycle_Total_Revenue"].first()
        total_profit = daily_profits.sum()
        total_charge = display_data[display_data["Phase"] == "charge"]["Energy_kWh"].sum()
        total_discharge = -display_data[display_data["Phase"] == "discharge"]["Energy_kWh"].sum()
        max_cumulative = display_data["Cumulative_Energy_kWh"].max()
        cycle_count = len(daily_profits)
    
    # 显示统计信息
    if period_type in ["季度", "半年", "年"]:
        # 对于长周期，显示6列包括最优Z值信息
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        
        with col1:
            st.metric("📊 总收益", f"{total_profit:.2f} AUD", delta=None)
        
        with col2:
            st.metric("🔋 总充电量", f"{total_charge:.1f} kWh", delta=None)
        
        with col3:
            st.metric("⚡ 总放电量", f"{total_discharge:.1f} kWh", delta=None)
        
        with col4:
            st.metric("📈 最大储能", f"{max_cumulative:.1f} kWh", delta=None)
        
        with col5:
            st.metric("📅 包含天数", f"{cycle_count} 天", delta=None)
        
        with col6:
            cache_key_z = f'optimal_z_{period_type}_{selected_period}'
            if cache_key_z in st.session_state:
                optimal_z_display = st.session_state[cache_key_z]
                delta_z = f"+{optimal_z_display - z_value:.1f}" if optimal_z_display != z_value else None
                st.metric("🎯 最优Z值", f"{optimal_z_display:.1f}", delta=delta_z)
            else:
                st.metric("🎯 最优Z值", "未计算", delta=None)
    else:
        # 对于日周期，显示5列
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("📊 总收益", f"{total_profit:.2f} AUD", delta=None)
        
        with col2:
            st.metric("🔋 总充电量", f"{total_charge:.1f} kWh", delta=None)
        
        with col3:
            st.metric("⚡ 总放电量", f"{total_discharge:.1f} kWh", delta=None)
        
        with col4:
            st.metric("📈 最大储能", f"{max_cumulative:.1f} kWh", delta=None)
        
        with col5:
            st.metric("📅 包含天数", f"{cycle_count} 天", delta=None)
    
    # 创建两列布局
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        st.subheader(f"📋 {get_period_display_name(period_type, selected_period)} 详细数据")
        
        # 为展示计算新增列：充电成本(按周期内电量净累计) 与 周期内累加收益
        # 确保按时间排序后在各自日周期内做累计
        display_data = display_data.sort_values(["Cycle_Date", "Timestamp"]).copy()
        display_data["Charge_Cost"] = display_data.groupby("Cycle_Date")["Energy_kWh"].cumsum()
        display_data["Cycle_Cum_Revenue"] = display_data.groupby("Cycle_Date")["Cost_Revenue"].cumsum()

        # 准备显示用的数据
        display_df = display_data.copy()
        display_df["时间"] = display_df["Timestamp"].dt.strftime("%Y-%m-%d %H:%M")
        display_df["日期"] = display_df["Cycle_Date"].dt.strftime("%Y-%m-%d")
        display_df["电价(RRP)"] = display_df["Price_RRP"].round(2)
        display_df["阶段"] = display_df["Phase"].map({"charge": "充电", "discharge": "放电"})
        display_df["状态"] = display_df["Status"]  # 添加状态列
        # 将原“Z值”列替换为“充电成本”（按周期内电量净累计）
        display_df["充电成本"] = display_df["Charge_Cost"].round(2)
        display_df["电量(kWh)"] = display_df["Energy_kWh"].round(2)
        display_df["累计电量(kWh)"] = display_df["Cumulative_Energy_kWh"].round(2)
        display_df["成本/收益"] = display_df["Cost_Revenue"].round(2)
        # 将原“周期总收益”列替换为“周期内累加收益”（按周期内累计到当前行），并追加展示“周期总收益”
        display_df["周期内累加收益"] = display_df["Cycle_Cum_Revenue"].round(2)
        display_df["周期总收益"] = display_df["Cycle_Total_Revenue"].round(2)
        
        # 选择显示列
        if period_type == "天":
            display_cols = ["时间", "电价(RRP)", "阶段", "状态", "充电成本", "电量(kWh)", 
                           "累计电量(kWh)", "成本/收益", "周期内累加收益", "周期总收益"]
        else:
            display_cols = ["日期", "时间", "电价(RRP)", "阶段", "状态", "充电成本", "电量(kWh)", 
                           "累计电量(kWh)", "成本/收益", "周期内累加收益", "周期总收益"]
        
        # 显示表格
        st.dataframe(
            display_df[display_cols],
            use_container_width=True,
            height=400
        )
    
    with col_right:
        st.subheader("📊 可视化分析")
        
        # 电价趋势图
        if period_type == "天":
            x_axis = "Timestamp"
            title_suffix = "（单日）"
        else:
            x_axis = "Timestamp"
            title_suffix = f"（{period_type}）"
        
        fig_price = px.line(
            display_data, 
            x=x_axis, 
            y="Price_RRP",
            color="Phase",
            title=f"电价趋势{title_suffix}",
            color_discrete_map={"charge": "blue", "discharge": "red"}
        )
        fig_price.update_layout(height=200, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_price, use_container_width=True)
        
        # 能量分布图
        energy_data = display_data[display_data["Energy_kWh"] != 0]
        if len(energy_data) > 0:
            fig_energy = px.bar(
                energy_data, 
                x=x_axis, 
                y="Energy_kWh",
                color="Phase",
                title=f"充放电能量分布{title_suffix}",
                color_discrete_map={"charge": "green", "discharge": "orange"}
            )
            fig_energy.update_layout(height=200, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_energy, use_container_width=True)
        
        # 累计电量图（仅单日显示）
        if period_type == "天":
            fig_cumulative = px.line(
                display_data, 
                x="Timestamp", 
                y="Cumulative_Energy_kWh",
                title="累计储能量",
                color_discrete_sequence=["purple"]
            )
            fig_cumulative.update_layout(height=200, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_cumulative, use_container_width=True)
    
    # 显示周期概览
    st.subheader("🔍 周期概览")
    
    if period_type == "天":
        # 单日分析
        phase_stats = display_data.groupby("Phase").agg({
            "Energy_kWh": ["sum", "count"],
            "Cost_Revenue": "sum",
            "Price_RRP": ["mean", "min", "max"]
        }).round(2)
        
        phase_stats.columns = ["总能量", "时段数", "总成本收益", "平均电价", "最低电价", "最高电价"]
        phase_stats.index = phase_stats.index.map({"charge": "充电阶段", "discharge": "放电阶段"})
        
        st.dataframe(phase_stats, use_container_width=True)
    else:
        # 多日分析
        daily_summary = display_data.groupby("Cycle_Date").agg({
            "Cycle_Total_Revenue": "first",
            "Energy_kWh": lambda x: x[display_data.loc[x.index, "Phase"] == "charge"].sum(),
            "Price_RRP": ["mean", "min", "max"]
        }).round(2)
        
        daily_summary.columns = ["日收益", "日充电量", "平均电价", "最低电价", "最高电价"]
        daily_summary.index = daily_summary.index.strftime("%Y-%m-%d")
        
        st.dataframe(daily_summary, use_container_width=True)
    
    # 侧边栏显示系统信息
    st.sidebar.markdown("---")
    st.sidebar.subheader("ℹ️ 系统信息")
    
    # 构建系统信息
    info_text = f"""
    **分析周期**: {period_type}  
    **当前选择**: {selected_period}  
    **当前Z值**: {z_value}  
    **数据点**: {len(display_data)} 行  
    **包含天数**: {cycle_count} 天
    """
    
    # 如果有最优Z值，添加到信息中
    if period_type in ["季度", "半年", "年"]:
        cache_key_z = f'optimal_z_{period_type}_{selected_period}'
        cache_key_profit = f'optimal_profit_{period_type}_{selected_period}'
        if cache_key_z in st.session_state:
            optimal_z_info = st.session_state[cache_key_z]
            optimal_profit_info = st.session_state[cache_key_profit]
            info_text += f"""  
    **最优Z值**: {optimal_z_info:.1f}  
    **最优收益**: {optimal_profit_info:.2f}
    """
    
    st.sidebar.info(info_text)
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("💡 **使用说明**:")
    st.sidebar.markdown(f"""
    1. 选择分析周期类型（{period_type}）
    2. 选择具体的{period_type}
    3. 调整Z值（最低利润阈值）
    4. 点击"重新计算"更新结果
    5. 查看表格和图表了解详情
    """)

if __name__ == "__main__":
    main() 