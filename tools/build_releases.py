# -*- coding: utf-8 -*-
"""
组装 XiaoLiZiVM_CppSDK 的 Releases 成品区（作者工具包）。

用法：
    python tools/build_releases.py             # 组装
    python tools/build_releases.py --dry-run   # 只看计划，不写盘

产物（Releases/ 为纯生成物，可随时从源码重建）：
    README.md                使用说明（本脚本生成）
    AI编写插件提示词.md       从仓库根复制，并把 Demo_* 引用改写为 template/
    template/                插件工程（复制改名即用）
    include/                 SDK 头文件
    src/                     SDK 实现

为什么 template/ 必须与 include/、src/ 同级：
    工程用 $(ProjectDir)..\\include 与 ..\\src\\xlz_*.cpp 相对引用 SDK，
    层级关系一破坏就编不过 —— 这一点由脚本末尾的引用校验兜底。
"""
import os
import sys
import shutil
import hashlib

SDK_VERSION = "3.1.3"

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
SDK_ROOT = os.path.dirname(TOOLS_DIR)
RELEASES = os.path.join(SDK_ROOT, "Releases")
TMP = os.path.join(SDK_ROOT, "Releases.__tmp__")
OLD = os.path.join(SDK_ROOT, "Releases.__old__")

# ---- 组装来源 ----------------------------------------------------------
TEMPLATE_SUB = "template"
INCLUDE_SUB = "include"
SRC_SUB = "src"

TEMPLATE_SRC_DIR = "Demo_TemplatePlugin"
TEMPLATE_FILES = [
    "TemplatePlugin.sln",
    "TemplatePlugin.vcxproj",
    "TemplatePlugin.vcxproj.filters",
    "exports.def",
    "plugin.cpp",
]
# 不拷贝 *.vcxproj.user（本机调试配置）与 bin/（编译产物）

AI_PROMPT_SRC = os.path.join(SDK_ROOT, "AI编写插件提示词.md")
AI_PROMPT_DST = "AI编写插件提示词.md"

# AI 提示词里需要改写的引用（按顺序应用，先具体后宽泛）
PROMPT_REWRITES = [
    ("Demo_关键词回复\\plugin.cpp", "template\\plugin.cpp"),
    ("`TemplatePlugin` 与 `Demo_关键词回复` 的写法", "`template` 的写法"),
    ("Demo_TemplatePlugin", "template"),
    ("Demo_关键词回复", "template"),
    ("仓库根目录下的 `README.md`", "本工具包根目录的 `README.md`"),
    ("本仓库的 C++ SDK", "本工具包的 C++ SDK"),
    ("本仓库的 SDK", "本工具包的 SDK"),
]
# 改写后会变成重复/误导、需要整行删除的
PROMPT_DROP_CONTAINS = [
    "一个简单的“关键词回复”插件示例",
]

README_TEMPLATE = """# 小栗子虚拟机 C++ SDK 成品区（作者工具包）

> 版本 v{sdk_version} ｜ 与框架 {sdk_version} 对齐

本目录是**免配置的 C++ 插件开发工具包**：不必克隆完整仓库，直接用 Visual Studio
打开这里就能编译出一个可被小栗子虚拟机加载的插件 DLL。

## 目录结构

```
Releases/
├── README.md                本说明
├── AI编写插件提示词.md       丢给 AI 帮你写插件的提示词
├── template/                ● 插件工程（复制改名即用）
│   ├── TemplatePlugin.sln
│   ├── TemplatePlugin.vcxproj
│   ├── TemplatePlugin.vcxproj.filters
│   ├── exports.def          导出表（apprun 与各回调）
│   └── plugin.cpp           插件源码（改这里）
├── include/                 SDK 头文件（{n_include} 个）
└── src/                     SDK 实现（{n_src} 个 .cpp）
```

## 怎么用

### 1. 先编译模板跑通

用 Visual Studio 打开 `template/TemplatePlugin.sln` → 选 **Release | Win32** → 生成。

产物：`template/bin/Release/XiaoLiZiVM_CppSDK_Template.dll`

### 2. 写自己的插件

把 `template/` 整个目录复制成 `MyPlugin/`（含 `.sln`、`.vcxproj`、`exports.def`、`plugin.cpp`），
改工程名与 `plugin.cpp` 内容即可。

> ⚠️ **`template/` 必须与 `include/`、`src/` 保持同级** —— 工程用相对路径
> `..\\include` 和 `..\\src\\xlz_*.cpp` 引用 SDK。
> 也就是：新插件目录要建在 `Releases/` 下、与 `template/` 同级，
> **不要只把 `template/` 单独拷到别的地方**（那样会找不到 SDK 头文件）。

### 3. 部署

把编译出的 DLL 放进框架的插件目录，重载框架即可。

## 编译要求

- **必须 Win32 (x86)**，不能选 x64 —— SDK 的 stdcall 调用器是 x86 汇编实现。
- Visual Studio 2019 / 2022，需安装「使用 C++ 的桌面开发」工作负载。
- 工程默认工具集 `v142`；用更新的 VS 打开时按提示升级工具集即可。

## 编码约定（重点）

- 插件内部统一 **UTF-8**；调用 API 前用 `xlz_encoding.h/.cpp` 转成 usc2/ansi 混合文本，
  取回返回值后再转回 UTF-8。
- 事件类型 / 子类型与回调返回值**不要写魔法数字**，统一用 `xlz_constants.h` 里的
  `enum class`（如 `xlz::GroupEvent::MemberJoined`、`xlz::MessageHandle::Intercept`）。

API 列表、事件常量表、字段命名规范等详见完整仓库的 `README.md`。
"""


def sha8(path):
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:16].upper()


def load_ai_prompt():
    """读取仓库根的 AI 提示词，改写 Demo 引用后返回文本。"""
    with open(AI_PROMPT_SRC, "r", encoding="utf-8") as f:
        text = f.read()

    lines = text.splitlines(keepends=True)
    kept = []
    dropped = 0
    for ln in lines:
        if any(k in ln for k in PROMPT_DROP_CONTAINS):
            dropped += 1
            continue
        kept.append(ln)
    text = "".join(kept)

    for old, new in PROMPT_REWRITES:
        if old in text:
            text = text.replace(old, new)

    return text, dropped


def check_project_refs(root):
    """校验 template/*.vcxproj 里 ..\\ 引用的文件在成品区里真实存在。"""
    vcx = os.path.join(root, TEMPLATE_SUB, "TemplatePlugin.vcxproj")
    if not os.path.exists(vcx):
        return ["缺少 template/TemplatePlugin.vcxproj"]

    with open(vcx, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    import re
    refs = re.findall(r'Include="(\.\.\\[^"]+)"', content)
    missing = []
    for r in sorted(set(refs)):
        rel = r.replace("\\", os.sep)
        full = os.path.normpath(os.path.join(root, TEMPLATE_SUB, rel))
        if not os.path.exists(full):
            missing.append("%s  ->  %s" % (r, os.path.relpath(full, root)))
    return missing


def build(dry_run=False):
    plan = []

    # 1) template/
    tpl_dir = os.path.join(SDK_ROOT, TEMPLATE_SRC_DIR)
    template_items = []
    for name in TEMPLATE_FILES:
        src = os.path.join(tpl_dir, name)
        if not os.path.exists(src):
            print("[错误] 模板文件缺失：%s" % src)
            return 1
        template_items.append((src, TEMPLATE_SUB + "/" + name))
    plan.append(("template", template_items))

    # 2) include/
    inc_dir = os.path.join(SDK_ROOT, INCLUDE_SUB)
    include_items = []
    for name in sorted(os.listdir(inc_dir)):
        if name.lower().endswith(".h"):
            include_items.append((os.path.join(inc_dir, name), INCLUDE_SUB + "/" + name))
    plan.append(("include", include_items))

    # 3) src/
    src_dir = os.path.join(SDK_ROOT, SRC_SUB)
    src_items = []
    for name in sorted(os.listdir(src_dir)):
        if name.lower().endswith(".cpp"):
            src_items.append((os.path.join(src_dir, name), SRC_SUB + "/" + name))
    plan.append(("src", src_items))

    ai_text, dropped = load_ai_prompt()
    readme_text = README_TEMPLATE.format(
        sdk_version=SDK_VERSION,
        n_include=len(include_items),
        n_src=len(src_items),
    )

    print("=" * 68)
    print("XiaoLiZiVM C++ SDK —— 组装 Releases 成品区")
    print("=" * 68)
    print("SDK 根目录 : %s" % SDK_ROOT)
    print("成品区     : %s" % RELEASES)
    print("模式       : %s" % ("干跑（不写盘）" if dry_run else "实际组装"))
    print()

    for section, items in plan:
        print("[%s] %d 个文件" % (section, len(items)))
        for s, arc in items:
            print("       %-56s %9d 字节" % (arc, os.path.getsize(s)))
    print("[AI提示词] 1 个文件（改写 Demo 引用，删除 %d 行重复示例）" % dropped)
    print("[README.md] 本脚本生成")
    print()

    if dry_run:
        print("干跑结束，未写入任何文件。")
        return 0

    # ---- 写盘（原子替换）----
    if os.path.exists(TMP):
        shutil.rmtree(TMP)
    os.makedirs(TMP)

    total = 0
    for section, items in plan:
        for s, arc in items:
            dst = os.path.join(TMP, arc.replace("/", os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(s, dst)
            total += 1

    with open(os.path.join(TMP, AI_PROMPT_DST), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(ai_text)
    with open(os.path.join(TMP, "README.md"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(readme_text)
    total += 2

    # 校验编译引用完整性
    missing = check_project_refs(TMP)
    if missing:
        print("[错误] 工程引用校验失败，成品区未生成：")
        for m in missing:
            print("   -", m)
        shutil.rmtree(TMP, ignore_errors=True)
        return 7
    print("[校验] template/*.vcxproj 的 ..\\include、..\\src 引用全部就位")

    # 原子替换
    if os.path.exists(OLD):
        shutil.rmtree(OLD)
    if os.path.exists(RELEASES):
        os.rename(RELEASES, OLD)
    try:
        os.rename(TMP, RELEASES)
    except Exception:
        if os.path.exists(OLD):
            os.rename(OLD, RELEASES)
        raise
    if os.path.exists(OLD):
        shutil.rmtree(OLD)

    print()
    print("[成品区] %s" % RELEASES)
    print("       共 %d 个文件" % total)
    for root, dirs, files in os.walk(RELEASES):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(root, name)
            arc = os.path.relpath(full, RELEASES).replace(os.sep, "/")
            print("       %-56s %9d 字节  %s" % (arc, os.path.getsize(full), sha8(full)))
    print()
    print("完成。")
    return 0


if __name__ == "__main__":
    sys.exit(build(dry_run="--dry-run" in sys.argv))
