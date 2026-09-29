"""业务模块口径注册表。

同一份口径同时被三处使用，保证「概览」和「运单/业务明细」对得上：

1. services 里的明细筛选、创建、状态流转；
2. services/overview 里的概览重算与对账；
3. seed 初始化写入时的模块与字段清单。

任何一处都不允许再私藏一份状态/字段定义。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModuleSpec:
    name: str                # 模块标识，也是 records.module 的取值
    label: str               # 中文模块名（概览页展示）
    entity: str              # 业务实体称谓（提示文案用）
    keyword_field: str       # 明细列表关键字检索字段
    required_fields: tuple[str, ...]   # 创建时必填字段
    list_fields: tuple[str, ...]       # 明细列字段顺序（文档/导出口径）
    statuses: tuple[str, ...]          # 允许的状态序列（首个为初始状态，末个为终态）
    action_rules: dict[str, str]       # 动作 -> 目标状态
    negative_actions: tuple[str, ...] = ()  # 触发后置 abnormal=True 的动作

    @property
    def initial_status(self) -> str:
        return self.statuses[0]

    @property
    def terminal_status(self) -> str:
        return self.statuses[-1]


MODULES: tuple[ModuleSpec, ...] = (
    ModuleSpec(
        name="shipment", label="发运单管理", entity="发运单",
        keyword_field="运单编号",
        required_fields=("运单编号", "发货方", "收货方"),
        list_fields=("运单编号", "发货方", "收货方", "货物名称", "温层要求", "发运日期", "预计到达", "运单状态"),
        statuses=("待发运", "在途", "已到达", "已签收", "已退回"),
        action_rules={"确认发运": "在途", "确认到达": "已到达", "退回货物": "已退回"},
    ),
    ModuleSpec(
        name="temp_monitor", label="温控监测", entity="温度记录",
        keyword_field="记录编号",
        required_fields=("记录编号", "运单编号", "当前温度"),
        list_fields=("记录编号", "运单编号", "当前温度", "温度上限", "温度下限", "记录时间", "设备编号", "记录状态"),
        statuses=("正常", "接近临界", "超温", "数据缺失"),
        action_rules={"标记预警": "接近临界", "确认超温": "超温", "数据补录": "正常"},
    ),
    ModuleSpec(
        name="vehicle", label="车辆调度", entity="冷藏车辆",
        keyword_field="车辆编号",
        required_fields=("车辆编号", "车牌号", "车型类别"),
        list_fields=("车辆编号", "车牌号", "车型类别", "温层能力", "制冷机组型号", "上次维保日", "当前位置", "车辆状态"),
        statuses=("空闲", "已派单", "执行中", "维修中", "停运"),
        action_rules={"派发出车": "已派单", "收车归队": "空闲", "报修车辆": "维修中"},
    ),
    ModuleSpec(
        name="driver", label="司机管理", entity="驾驶人员",
        keyword_field="司机编号",
        required_fields=("司机编号", "姓名", "驾驶证号"),
        list_fields=("司机编号", "姓名", "驾驶证号", "从业资格证", "健康证有效期", "联系手机", "所属车队", "司机状态"),
        statuses=("在岗", "出车中", "休息", "停岗"),
        action_rules={"安排出车": "出车中", "办理停岗": "停岗", "恢复在岗": "在岗"},
    ),
    ModuleSpec(
        name="cold_storage", label="冷库运营", entity="冷库库区",
        keyword_field="库区编号",
        required_fields=("库区编号", "库区名称", "设定温度"),
        list_fields=("库区编号", "库区名称", "设定温度", "当前温度", "库容利用率", "作业班组", "巡检时间", "库区状态"),
        statuses=("正常运行", "温度偏高", "除霜中", "检修中"),
        action_rules={"开始除霜": "除霜中", "安排检修": "检修中", "恢复运行": "正常运行"},
    ),
    ModuleSpec(
        name="loading", label="装卸作业", entity="装卸记录",
        keyword_field="记录编号",
        required_fields=("记录编号", "运单编号", "装卸类型"),
        list_fields=("记录编号", "运单编号", "装卸类型", "月台编号", "开门时长", "装卸人员", "开始时间", "装卸状态"),
        statuses=("待装卸", "装卸中", "已完成", "已超时"),
        action_rules={"开始装卸": "装卸中", "确认完成": "已完成", "标记超时": "已超时"},
    ),
    ModuleSpec(
        name="alert", label="报警管理", entity="报警记录",
        keyword_field="报警编号",
        required_fields=("报警编号", "报警类型", "关联设备"),
        list_fields=("报警编号", "报警类型", "关联设备", "报警阈值", "触发值", "触发时间", "处置措施", "报警状态"),
        statuses=("未处理", "已确认", "处理中", "已消除"),
        action_rules={"确认报警": "已确认", "开始处理": "处理中", "消除报警": "已消除"},
    ),
    ModuleSpec(
        name="route", label="线路规划", entity="运输线路",
        keyword_field="线路编号",
        required_fields=("线路编号", "始发地", "到达地"),
        list_fields=("线路编号", "始发地", "到达地", "标准里程", "预估耗时", "途经节点", "路况等级", "线路状态"),
        statuses=("启用", "临时管制", "已废弃", "备用"),
        action_rules={"启用线路": "启用", "临时封闭": "临时管制", "废弃线路": "已废弃"},
    ),
    ModuleSpec(
        name="reefer_unit", label="制冷机组", entity="制冷设备",
        keyword_field="机组编号",
        required_fields=("机组编号", "所属车辆", "机组型号"),
        list_fields=("机组编号", "所属车辆", "机组型号", "设定温度", "回风温度", "运转时长", "上次保养日", "机组状态"),
        statuses=("运行", "怠速", "故障", "保养中"),
        action_rules={"停机检查": "故障", "安排保养": "保养中", "复位故障": "运行"},
    ),
    ModuleSpec(
        name="fuel", label="油料管理", entity="加油记录",
        keyword_field="记录编号",
        required_fields=("记录编号", "车辆编号", "油料类型"),
        list_fields=("记录编号", "车辆编号", "油料类型", "加油量", "加油金额", "油站名称", "加油日期", "记录状态"),
        statuses=("待录入", "已录入", "已审核", "已驳回"),
        action_rules={"录入记录": "已录入", "审核通过": "已审核", "驳回记录": "已驳回"},
        negative_actions=("驳回记录",),
    ),
    ModuleSpec(
        name="delivery", label="签收回单", entity="签收记录",
        keyword_field="签收编号",
        required_fields=("签收编号", "运单编号", "签收人"),
        list_fields=("签收编号", "运单编号", "签收人", "签收时间", "货物状况", "温度记录", "签收照片", "签收状态"),
        statuses=("待签收", "已签收", "异常签收", "已拒收"),
        action_rules={"正常签收": "已签收", "标记异常": "异常签收", "登记拒收": "已拒收"},
    ),
    ModuleSpec(
        name="break_chain", label="断链追溯", entity="断链事件",
        keyword_field="事件编号",
        required_fields=("事件编号", "运单编号", "断链环节"),
        list_fields=("事件编号", "运单编号", "断链环节", "超温时长", "超温幅度", "责任判定", "处理结论", "事件状态"),
        statuses=("待调查", "调查中", "已定责", "已关闭"),
        action_rules={"发起调查": "调查中", "判定责任": "已定责", "关闭事件": "已关闭"},
    ),
    ModuleSpec(
        name="dock", label="月台管理", entity="装卸月台",
        keyword_field="月台编号",
        required_fields=("月台编号", "月台类型", "温层分区"),
        list_fields=("月台编号", "月台类型", "温层分区", "占用状态", "滑升门状态", "高度调节板", "月台照明", "月台状态"),
        statuses=("空闲", "作业中", "待清洁", "故障维修"),
        action_rules={"分配作业": "作业中", "安排清洁": "待清洁", "报修故障": "故障维修"},
    ),
    ModuleSpec(
        name="package", label="包装管理", entity="保温包装",
        keyword_field="包装编号",
        required_fields=("包装编号", "包装类型", "保温材料"),
        list_fields=("包装编号", "包装类型", "保温材料", "适用温层", "使用次数", "上次消毒日", "破损情况", "包装状态"),
        statuses=("在库", "使用中", "待消毒", "已报废"),
        action_rules={"出库使用": "使用中", "安排消毒": "待消毒", "确认报废": "已报废"},
    ),
    ModuleSpec(
        name="toll", label="通行费用", entity="过路记录",
        keyword_field="记录编号",
        required_fields=("记录编号", "车辆编号", "收费站名称"),
        list_fields=("记录编号", "车辆编号", "收费站名称", "收费金额", "通行方向", "通行日期", "凭证编号", "记录状态"),
        statuses=("待确认", "已确认", "待冲销"),
        action_rules={"确认费用": "已确认", "冲销费用": "待冲销"},
    ),
    ModuleSpec(
        name="sanitation", label="车辆消杀", entity="消杀记录",
        keyword_field="消杀编号",
        required_fields=("消杀编号", "车辆编号", "消杀方式"),
        list_fields=("消杀编号", "车辆编号", "消杀方式", "消毒剂名称", "消杀区域", "操作人员", "消杀日期", "消杀状态"),
        statuses=("待消杀", "已消杀", "复消中"),
        action_rules={"执行消杀": "已消杀", "安排复消": "复消中"},
    ),
    ModuleSpec(
        name="contract", label="承运合同", entity="运输合同",
        keyword_field="合同编号",
        required_fields=("合同编号", "托运方", "承运方"),
        list_fields=("合同编号", "托运方", "承运方", "合同期限", "温层要求", "违约条款", "结算方式", "合同状态"),
        statuses=("草稿", "已签约", "履行中", "已到期", "已终止"),
        action_rules={"签订合同": "已签约", "到期提醒": "已到期", "终止合同": "已终止"},
    ),
    ModuleSpec(
        name="insurance", label="货运保险", entity="保险单",
        keyword_field="保单编号",
        required_fields=("保单编号", "运单编号", "投保险种"),
        list_fields=("保单编号", "运单编号", "投保险种", "保额金额", "保险费率", "起保日期", "止保日期", "保单状态"),
        statuses=("待投保", "已投保", "已出险", "已结案"),
        action_rules={"确认投保": "已投保", "申请出险": "已出险", "结案归档": "已结案"},
    ),
)

MODULE_BY_NAME: dict[str, ModuleSpec] = {spec.name: spec for spec in MODULES}
MODULE_NAMES: tuple[str, ...] = tuple(spec.name for spec in MODULES)
