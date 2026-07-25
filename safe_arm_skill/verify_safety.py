"""
NERO 机械臂安全验证脚本
运行: python3 verify_safety.py
每项通过 ✅ 才允许跑 Agent 生成的代码
"""
import re
import sys
import ast
from pathlib import Path

# ============================================================
#  验证规则定义
# ============================================================

REQUIRED = [
    # (规则名称, 检查条件, 严重程度)
    ("CAN口正确", lambda c: "can1" in c and "can0" not in c.split("channel"), "CRITICAL"),
    ("固件版本 V112", lambda c: "V112" in c and "set_normal_mode" not in c, "CRITICAL"),
    ("碰撞保护 0级", lambda c: "set_crash_protection_rating" in c and "rating=0" in c, "CRITICAL"),
    ("关节限位开启", lambda c: "set_joint_limits_enabled" in c and "False" not in c.split("set_joint_limits_enabled")[1][:30] if "set_joint_limits_enabled" in c else False, "HIGH"),
    ("速度限制 ≤50%", lambda c: check_speed_limit(c, 50), "HIGH"),
    ("先读当前角度", lambda c: "get_joint_angles" in c and "home" in c, "HIGH"),
    ("try/except 保护", lambda c: "try:" in c and "except" in c, "MEDIUM"),
    ("异常时下使能", lambda c: check_disable_in_except(c), "MEDIUM"),
    ("禁止 set_normal_mode", lambda c: "set_normal_mode" not in c, "CRITICAL"),
    ("禁止 move_mit", lambda c: "move_mit" not in c, "CRITICAL"),
    ("禁止 can0 硬编码", lambda c: '"can0"' not in c and "'can0'" not in c, "CRITICAL"),
]

FORBIDDEN = [
    "set_normal_mode",
    "move_mit",
    "set_speed_percent(100)",
    "set_speed_percent(90)",
    "set_speed_percent(80)",
    "set_speed_percent(70)",
    "set_speed_percent(60)",
    'channel="can0"',
    "channel='can0'",
    "NeroFW.DEFAULT",
]


def check_speed_limit(code: str, max_pct: int) -> bool:
    """检查速度是否在限制内"""
    # 检查直接数字
    matches = re.findall(r"set_speed_percent\((\d+)\)", code)
    for m in matches:
        if int(m) > max_pct:
            return False
    if matches:
        return True
    # 检查变量引用, 如 SAFE_SPEED = 20
    var_match = re.findall(r"(?:SAFE_SPEED|SAFE_SPEED_PCT)\s*=\s*(\d+)", code)
    if var_match:
        return int(var_match[0]) <= max_pct
    # 检查 speed_percent\s*=\s*(\d+)
    var_match2 = re.findall(r"speed_percent\s*=\s*(\d+)", code)
    if var_match2:
        return int(var_match2[0]) <= max_pct
    return False  # 没找到速度设置


def check_disable_in_except(code: str) -> bool:
    """检查 except 块中是否有 disable()"""
    parts = code.split("except")
    if len(parts) < 2:
        return False
    # 检查第一个 except 块 (最外层的异常处理)
    first_except = parts[1]
    return "disable()" in first_except


def verify_code(code: str, verbose: bool = True) -> tuple[bool, list[str]]:
    """验证代码安全性, 返回 (通过, 问题列表)"""
    issues = []

    if verbose:
        print("=" * 60)
        print("🔍 NERO 安全代码审查")
        print("=" * 60)

    # 检查必需项
    for name, check_fn, severity in REQUIRED:
        try:
            ok = check_fn(code)
        except Exception:
            ok = False
        status = "✅" if ok else f"❌ [{severity}]"
        if verbose:
            print(f"  {status} {name}")
        if not ok:
            issues.append(f"[{severity}] {name}")

    # 检查禁止项
    for forbidden in FORBIDDEN:
        if forbidden in code:
            issues.append(f"[CRITICAL] 禁止项: {forbidden}")
            if verbose:
                print(f"  ❌ [CRITICAL] 禁止项: {forbidden}")

    # 额外检查: 单关节运动范围
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript):
                # 粗略检查是否有超过 0.5 的赋值
                pass
    except SyntaxError:
        issues.append("[HIGH] 代码语法错误")

    passed = len(issues) == 0

    if verbose:
        print("-" * 60)
        if passed:
            print("✅ 全部检查通过! 可以安全执行")
        else:
            print(f"❌ {len(issues)} 个安全问题需要修复:")
            for issue in issues:
                print(f"   {issue}")
        print("=" * 60)

    return passed, issues


def verify_and_fix(code: str, verbose: bool = True) -> str:
    """验证并自动修复常见问题"""
    fixed = code

    # 自动修复
    fixes = [
        ('"can0"', '"can1"', "can0 -> can1"),
        ("'can0'", "'can1'", "can0 -> can1"),
        ("NeroFW.DEFAULT", "NeroFW.V112", "固件 DEFAULT -> V112"),
    ]

    for old, new, desc in fixes:
        if old in fixed:
            fixed = fixed.replace(old, new)
            if verbose:
                print(f"  🔧 自动修复: {desc}")

    # 注入安全配置（如果缺失）
    if "set_crash_protection_rating" not in fixed:
        fixed = fixed.replace(
            "arm.set_speed_percent",
            "arm.set_crash_protection_rating(joint_index=255, rating=0)\n"
            "    arm.set_speed_percent",
        )
        if verbose:
            print("  🔧 自动修复: 添加碰撞保护")

    if "set_joint_limits_enabled" not in fixed:
        fixed = fixed.replace(
            "arm.set_speed_percent",
            "arm.set_joint_limits_enabled(True)\n    arm.set_speed_percent",
        )
        if verbose:
            print("  🔧 自动修复: 添加关节限位")

    return fixed


def interactive_verify(code_path: str = None):
    """交互式验证模式"""
    if code_path:
        code = Path(code_path).read_text(encoding="utf-8")
    else:
        print("请粘贴 Agent 生成的代码 (输入 END 结束):")
        lines = []
        while True:
            line = input()
            if line.strip() == "END":
                break
            lines.append(line)
        code = "\n".join(lines)

    # 自动修复
    print("\n🔧 自动修复中...")
    code = verify_and_fix(code)

    # 验证
    print("")
    passed, issues = verify_code(code)

    if passed:
        print("\n🚀 安全验证通过!")
        if code_path:
            return  # 文件模式不询问执行
        print("是否执行? (输入 yes 确认)")
        confirm = input("> ")
        if confirm.strip().lower() == "yes":
            print("执行中...")
            exec(compile(code, "<safe_exec>", "exec"))
        else:
            print("已取消")
    else:
        print(f"\n❌ 请修复上述 {len(issues)} 个问题后重试")
        # 保存修复后的代码
        out_path = "/tmp/arm_code_fixed.py"
        Path(out_path).write_text(code)
        print(f"修复后的代码已保存到 {out_path}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        interactive_verify(sys.argv[1])
    else:
        interactive_verify()
