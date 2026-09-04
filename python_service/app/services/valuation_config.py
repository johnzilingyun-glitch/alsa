"""Valuation assumptions — single source of truth for CAPM/WACC/DCF inputs.

Rf / ERP / Kd 默认值与 β、WACC、g 的合理性边界此前散落在三处
（data_providers/a_stock_direct、report_generator_service、
computation_tools），口径各自漂移（provider Kd=4% vs 渲染层 5%）。
本模块收敛为唯一定义点，三方同源 import，两套 WACC 估算不再分裂。

消费者：
- data_providers/a_stock_direct.py   provider 侧 β 护栏与 WACC 估算
- report_generator_service.py        渲染层 DCF（β 钳制 / WACC floor / g 约束）
- computation_tools.py               LLM 确定性 DCF 计算工具的校验边界
- quant/valuation.py                 ValuationEngine 的 DCF 拒绝条件
"""

# ── CAPM 输入默认值 ──
# 股权风险溢价（中国市场口径 5.5%）——provider WACC 与报告 DCF 同源引用。
EQUITY_RISK_PREMIUM = 0.055
# 默认税前债务成本 Kd（provider 与渲染层共用；此前 4%/5% 各执一词）。
DEFAULT_COST_OF_DEBT = 0.04

# ── 无风险利率市场基准（provider 实时值缺失时的回退，标注"市场基准默认"）──
CN_RISK_FREE_FALLBACK = 0.02    # 中债 10Y 兜底（_get_cn_risk_free_rate 网络失败同值）
US_RISK_FREE_DEFAULT = 0.043    # ~4.3% US 10Y mid-2026
HK_RISK_FREE_DEFAULT = 0.035    # ~3.5% HK mid-2026

# ── β 护栏 ──
# Blume (1975) 收缩调整：β_adj = 0.67 × β_regression + 0.33 × 1.0，向市场均值 1 收敛。
BETA_BLOME_REG_WEIGHT = 0.67
# β 合理边界与回归质量阈值：对齐收益观测点不足或相关性塌陷时拒绝回归值。
BETA_FLOOR = 0.2
BETA_CEILING = 3.0
BETA_MIN_ALIGNED_OBS = 60
BETA_MIN_CORR = 0.25

# ── WACC / g 边界 ──
WACC_FLOOR_MARGIN = 0.02   # WACC 下限 = max(Rf + 2%, 5%)
WACC_FLOOR_ABS = 0.05
WACC_CEILING = 0.20        # WACC 上限 20%
MIN_WACC_G_SPREAD = 0.02   # WACC − g 最小利差，不足则拒绝输出 DCF（不 clamp 硬算）
G_NOMINAL_CAP = 0.05       # 永续增长长期名义上限

# ── 行业 β 中位数先验 ──
# |β回归| < 0.2 或 > 3 时回归无统计意义，回退行业先验（而非采信异常值）。
# 数值为 A 股行业杠杆 β 中位数的经验近似（对齐 Damodaran 中国行业 beta 口径），
# 关键词按东财 F10 industry 字段子串匹配；无匹配回退市场先验 1.0。
INDUSTRY_BETA_PRIORS: "dict[str, float]" = {
    "银行": 0.60, "保险": 0.80, "证券": 1.30, "信托": 1.10,
    "房地产": 1.20, "建筑": 1.00, "基建": 0.90,
    "消费电子": 1.20, "电力设备": 1.20,
    "电力": 0.70, "公用": 0.70, "水务": 0.60, "燃气": 0.70,
    "高速": 0.55, "公路": 0.55, "铁路": 0.70, "港口": 0.80, "机场": 0.80, "航运": 1.20,
    "煤炭": 1.00, "石油": 0.90, "石化": 1.00, "钢铁": 1.20, "有色": 1.30, "黄金": 0.90,
    "化工": 1.10, "水泥": 1.00, "玻璃": 1.10,
    "食品": 0.75, "饮料": 0.75, "白酒": 0.80, "乳": 0.75, "啤酒": 0.80,
    "医药": 0.80, "医疗": 0.80, "生物": 0.85, "中药": 0.75,
    "半导体": 1.30, "芯片": 1.30, "电子": 1.20, "元件": 1.15,
    "计算机": 1.20, "软件": 1.10, "互联网": 1.10, "游戏": 1.10, "传媒": 1.10, "影视": 1.15,
    "通信": 1.05, "运营商": 0.65,
    "汽车": 1.10, "新能源": 1.20, "光伏": 1.25, "锂电": 1.25, "电池": 1.25,
    "机械": 1.10, "军工": 1.20, "国防": 1.20, "航空": 1.10,
    "家电": 0.90, "家具": 0.95, "纺织": 0.90, "服装": 0.95, "零售": 1.00, "商贸": 1.00,
    "农业": 0.90, "养殖": 1.05, "种业": 1.05, "化肥": 1.05, "农药": 1.00,
    "旅游": 1.10, "酒店": 1.15, "教育": 1.05, "环保": 1.00, "检测": 0.95,
}


def industry_beta_prior(industry: "str | None") -> float:
    """行业 β 中位数先验：按东财 industry 字段关键词匹配，无匹配回退 1.0。

    返回值保证落在 [BETA_FLOOR, BETA_CEILING] 内（先验表本身已在界内，
    clamp 是防御外部改表）。
    """
    if industry:
        for keyword, prior in INDUSTRY_BETA_PRIORS.items():
            if keyword in str(industry):
                return float(min(max(prior, BETA_FLOOR), BETA_CEILING))
    return 1.0
