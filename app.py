# -*- coding: utf-8 -*-
"""
客服反馈 → 产品需求文档（PRD）自动生成器
========================================
适用场景：客服 / 运营同学把日常碎片化的用户反馈，一键结构化为产研可直接阅读的 PRD。
技术栈：Python 3.9+ / Streamlit / OpenAI SDK（兼容 DeepSeek、智谱 GLM、GPT 等）
项目定位：客服运营管培生（储备干部）求职 Demo —— 展示「AI 提效 + 数据敏感度 + 结构化表达」。
"""

# ====================== ① 配置区（兜底默认值） ======================
# 以下三个变量是「兜底默认值」，仅在未通过 secrets / 环境变量 / 边栏提供时使用。
# 优先级：部署平台 secrets / 环境变量  >  页面左侧边栏填写  >  本处硬编码值。
# 部署到 Streamlit Cloud 时，请在 Cloud 控制台的 Secrets 里配置 API_KEY / BASE_URL / MODEL_NAME，
# 切勿把真实 Key 写进代码提交到仓库。
API_KEY    = "sk-xxxxxxxxxxxxxxxxxxxxxxxx"   # TODO: 替换为你的真实 API Key
BASE_URL   = "https://api.deepseek.com/v1"   # DeepSeek 示例；OpenAI 用 https://api.openai.com/v1
MODEL_NAME = "deepseek-chat"                 # DeepSeek 示例；OpenAI 用 gpt-4o / gpt-4o-mini
REQUEST_TIMEOUT = 60                         # 单次请求超时（秒）
TEMPERATURE     = 0.3                        # 生成温度（越低越稳定、越克制）
# ================================================================


# ====================== ② 依赖 & 常量 ======================
import os
import io
import time
import json
import re

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from openai import OpenAI, APIError, APITimeoutError, AuthenticationError, RateLimitError

# 常见“反馈内容”列名，用于 CSV 自动识别（不区分大小写）
COMMON_FEEDBACK_COLS = [
    "反馈", "用户反馈", "feedback", "内容", "content",
    "问题", "problem", "描述", "description", "text", "文本", "留言", "comment",
]

# 演示用示例反馈：刻意混了 4 类问题，方便展示「自动聚类 → 多份 PRD」
EXAMPLE_FEEDBACK = """\
客户说昨天还能正常登录，今天一打开 App 就提示“账号异常已冻结”，但明明没违规，打了 3 次客服电话才有人工接，很生气。
好几个用户反馈在结算页点“立即支付”经常转圈十几秒没反应，最后重复扣了两次款，退款要等 3-5 个工作日，体验很差。
iOS 18 更新后，我的 iPhone 一进“我的订单”页面就闪退，安卓同事的手机没问题，已经反馈半个月了还没修。
推送通知太多了，几乎每天七八条营销推送，用户说已经准备卸载了，希望能像微信那样自己关掉某类通知。
新用户注册完完全不知道下一步干嘛，首屏就一个孤零零的“立即体验”按钮，不知道点进去是啥，流失应该挺严重。
后台工单里看到不少用户吐槽：修改收货地址的入口藏得太深，下单后才发现地址错了，找不到地方改，只能取消重下。
连续两周收到类似反馈：优惠券到期前没有任何提醒，用户过了期才发现，觉得被“套路”了，情绪比较激动。
"""

# System Prompt：让模型扮演资深产品经理，把碎片反馈提炼成标准 PRD
SYSTEM_PROMPT = """\
你是一位拥有 10 年经验的资深互联网产品经理，擅长从海量、碎片化的客服反馈中，\
提炼出真实、可执行、让产研团队一眼看懂的产品需求。

# 处理原则（必须逐条落实）
1. 识别核心痛点，剔除无效情绪：先共情用户的挫败感，但只保留“可被产品解决”的事实性诉求，别把情绪本身当需求。
2. 评估影响面：这个痛点覆盖多少用户？发生频次高不高？用“高 / 中 / 低”定性，并给出判断依据。
3. 评估业务影响：是否增加了客服工作量？是否影响转化率、留存、营收或品牌口碑？量化描述（如能估算）。
4. 给出优先级建议：P0 紧急修复（阻断主流程/资损/大面积投诉）/ P1 近期迭代 / P2 后续优化。
5. 提供初步解决方案方向：给“做什么”的方向性建议，不必写完整技术方案。

# 聚类与输出规则
- 如果所有反馈明显属于同一类问题，输出【一份】PRD。
- 如果反馈涉及多个明显不同的类别，请先【自动聚类】，再分别输出【多份】PRD；\
  每份 PRD 前用二级标题标注归类，例如：## 【需求归类：登录与账号】
- 在正文最开头，先输出一张「需求概览」表，方便管理层一眼掌握全局，格式如下：
  ## 需求概览
  | 需求归类 | 关联反馈条数 | 优先级 | 一句话结论 |
  |---|---|---|---|
  | ... | ... | P0/P1/P2 | ... |

# 每份 PRD 必须包含以下五个板块（用三级标题）
### 【需求背景】
### 【问题描述】
### 【影响面评估】
### 【优先级建议】
### 【建议方案】

# 输出格式
- 仅输出 Markdown，不要输出任何额外的前言、解释或与任务无关的内容。
- 语言简洁、专业、客观，面向产研读者。
"""


# ====================== ③ 输入处理 ======================
def parse_uploaded_file(uploaded_file) -> str:
    """解析上传的 CSV / TXT，返回合并后的多行反馈文本。"""
    file_name = uploaded_file.name.lower()
    try:
        if file_name.endswith(".txt"):
            raw = uploaded_file.read().decode("utf-8", errors="ignore")
            return raw

        if file_name.endswith(".csv"):
            # 用 pandas 读取，自动识别编码
            df = pd.read_csv(io.BytesIO(uploaded_file.read()))
            # 优先匹配常见“反馈内容”列名
            target_col = None
            lower_cols = {c.lower().strip(): c for c in df.columns}
            for cand in COMMON_FEEDBACK_COLS:
                if cand.lower() in lower_cols:
                    target_col = lower_cols[cand.lower()]
                    break
            if target_col is None:
                # 没匹配到就用第一列；若只有一列则直接用
                target_col = df.columns[0]
                st.warning(f"未在 CSV 中找到常见“反馈内容”列，已默认使用第一列：{target_col}")
            texts = df[target_col].dropna().astype(str).tolist()
            return "\n".join(t.strip() for t in texts if t.strip())

        st.error("仅支持 CSV 或 TXT 文件。")
        return ""
    except Exception as e:  # noqa: BLE001
        st.error(f"文件解析失败：{e}")
        return ""


def build_feedback_text(area_text: str, uploaded_file) -> str:
    """合并文本框输入与上传文件，得到最终待处理的反馈文本。"""
    parts = []
    if area_text and area_text.strip():
        parts.append(area_text.strip())
    if uploaded_file is not None:
        parsed = parse_uploaded_file(uploaded_file)
        if parsed:
            parts.append(parsed)
    return "\n".join(parts)


def count_feedback(text: str) -> int:
    """统计有效反馈条数（按非空行）。"""
    return len([line for line in text.splitlines() if line.strip()])


# ====================== ④ LLM 调用 ======================
def _get_secret(name: str, fallback: str) -> str:
    """按优先级读取配置：Streamlit secrets → 环境变量 → 代码兜底默认值。"""
    try:
        val = st.secrets.get(name)
        if val:
            return str(val)
    except Exception:
        pass
    val = os.environ.get(name)
    return str(val) if val else fallback


def generate_prd(feedback_text: str, api_key: str, base_url: str, model: str) -> str:
    """调用大模型，把反馈文本结构化为 PRD Markdown。出错时抛出异常由上层捕获。"""
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=REQUEST_TIMEOUT)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": feedback_text},
        ],
        temperature=TEMPERATURE,
    )
    return resp.choices[0].message.content or ""


# ====================== ④-b 输出增强工具 ======================
def parse_overview_table(markdown_text: str):
    """从模型输出中解析「需求概览」Markdown 表格，返回 (DataFrame, 是否解析成功)。"""
    lines = markdown_text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^##\s*需求概览", ln.strip()):
            start = i
            break
    if start is None:
        return None, False
    table_lines = []
    for ln in lines[start + 1:]:
        s = ln.strip()
        if s.startswith("|"):
            table_lines.append(s)
        elif s == "":
            continue
        else:
            # 遇到下一个标题或正文即停止
            break
    rows = [r for r in table_lines if not re.match(r"^[\|\-\s]+$", r)]  # 去掉 --- 分隔行
    if len(rows) < 2:
        return None, False
    data = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    header, body = data[0], data[1:]
    max_col = len(header)
    body = [r + [""] * (max_col - len(r)) if len(r) < max_col else r[:max_col] for r in body]
    return pd.DataFrame(body, columns=header), True


def strip_overview_section(markdown_text: str) -> str:
    """移除「需求概览」段落，避免与下方 dataframe 重复展示。"""
    lines = markdown_text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^##\s*需求概览", ln.strip()):
            start = i
            break
    if start is None:
        return markdown_text
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].strip().startswith("#"):
            end = j
            break
    return "\n".join(lines[:start] + lines[end:]).strip()


def to_wecom_plain(markdown_text: str) -> str:
    """把 Markdown 转成企微聊天友好的纯文本（去标题/加粗符号，表格转缩进）。"""
    out = []
    for ln in markdown_text.splitlines():
        s = ln.rstrip()
        st_ = s.strip()
        if st_.startswith("## "):
            out.append("【" + st_[3:].strip() + "】")
        elif st_.startswith("### "):
            out.append("· " + st_[4:].strip())
        elif st_.startswith("# "):
            out.append(st_[2:].strip())
        elif st_.startswith("|"):
            cells = [c.strip() for c in st_.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):  # 跳过分隔行
                continue
            out.append("  " + " | ".join(cells))
        else:
            out.append(s.replace("**", ""))
    return "\n".join(out)


def copy_button(label: str, text: str, key: str, height: int = 44):
    """渲染一个“复制到剪贴板”按钮（localhost 属安全上下文，clipboard API 可用）。"""
    safe = json.dumps(text)
    esc = label.replace("'", "\\'")
    html = f"""
    <div>
      <button id="cp_{key}" onclick="(function(){{
        navigator.clipboard.writeText({safe}).then(function(){{
          var b=document.getElementById('cp_{key}');
          b.innerText='✅ 已复制';
          b.style.background='#0a8a3c';
          setTimeout(function(){{b.innerText='{esc}';b.style.background='';}},1800);
        }}).catch(function(e){{alert('复制失败，请手动选择文本复制');}});
      }})()" style="width:100%;padding:9px 12px;border:none;border-radius:6px;
        background:#3370ff;color:#fff;font-size:14px;cursor:pointer;">{label}</button>
    </div>
    """
    components.html(html, height=height)


# ====================== ④-c 优先级筛选工具 ======================
def extract_priority_map(overview_df):
    """从概览表构建 {需求归类: 优先级} 映射。"""
    pri_map = {}
    if overview_df is None or overview_df.empty:
        return pri_map
    cols = list(overview_df.columns)
    cat_col = next((c for c in cols if ("归类" in c or "需求" in c)), cols[0])
    pri_col = next((c for c in cols if "优先级" in c), cols[-1])
    for _, row in overview_df.iterrows():
        pri_map[str(row[cat_col]).strip()] = str(row[pri_col]).strip().upper()
    return pri_map


def filter_overview_df(overview_df, selected):
    """按选中的优先级过滤概览表。"""
    sel = set(s.upper() for s in selected)
    if overview_df is None or overview_df.empty:
        return overview_df
    pri_col = next((c for c in overview_df.columns if "优先级" in c), overview_df.columns[-1])
    mask = overview_df[pri_col].astype(str).str.upper().isin(sel)
    return overview_df[mask].reset_index(drop=True)


def filter_prd_markdown(detail_md, overview_df, selected):
    """按优先级筛选详细 PRD；返回 (筛选后文本, 是否命中)。"""
    sel = set(s.upper() for s in selected)
    if not sel or overview_df is None or overview_df.empty:
        return detail_md, True
    pri_map = extract_priority_map(overview_df)
    if "## 【需求归类" not in detail_md:
        first_pri = next(iter(pri_map.values()), "")
        shown = first_pri in sel
        return (detail_md if shown else ""), shown
    segments = re.split(r"(?m)^(##\s*【需求归类.*)$", detail_md)
    head = segments[0]
    kept = []
    for i in range(1, len(segments), 2):
        heading = segments[i]
        body = segments[i + 1] if i + 1 < len(segments) else ""
        cat = re.search(r"【需求归类[:：]\s*(.*?)】", heading)
        cat_name = cat.group(1).strip() if cat else ""
        if pri_map.get(cat_name, "") in sel:
            kept.append(heading + body)
    return head + "\n".join(kept), bool(kept)


# ====================== ④-d 高级感 UI 样式 ======================
PREMIUM_CSS = """
<style>
:root{
  --brand:#3370ff; --brand2:#7b5cff; --ink:#1f2733; --sub:#6b7480;
  --line:#e7eaf1; --card:#ffffff;
}
.stApp{
  background:linear-gradient(180deg,#eaf0fb 0%, #f6f8fc 200px, #f6f8fc 100%);
}
.block-container{padding-top:.75rem;}
.title-card{
  width:100%;padding:18px 22px;border-radius:14px;
  background:linear-gradient(92deg,#3b5bff 0%, #7b5cff 100%);
  box-shadow:0 10px 30px rgba(80,90,200,.25);margin-bottom:.4rem;
}
.title-text{font-size:26px;font-weight:800;color:#ffffff;letter-spacing:.3px;}
.subtitle{color:#eef0ff;font-size:14px;margin-top:8px;margin-left:2px;opacity:.95;}
[data-testid="stMetric"]{
  background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:14px 18px;box-shadow:0 8px 24px rgba(31,39,51,.06);
}
[data-testid="stMetric"] label{color:var(--sub);font-size:13px;font-weight:500;}
[data-testid="stMetric"] [data-testid="stMetricValue"]{color:var(--ink);font-weight:800;font-size:26px;}
[data-testid="stSidebar"]{
  background:#ffffff;border-right:1px solid var(--line);
  box-shadow:2px 0 16px rgba(31,39,51,.04);
}
[data-testid="stSubheader"]{
  border-left:4px solid var(--brand);padding-left:10px;border-radius:4px;
  color:var(--ink);font-weight:700;
}
.stButton>button[data-baseweb="button"]{border-radius:10px;font-weight:600;transition:.15s;}
.stButton>button[data-baseweb="button"]:hover{transform:translateY(-1px);
  box-shadow:0 6px 16px rgba(51,112,255,.25);}
.stDownloadButton>button[data-baseweb="button"]{border-radius:10px;}
div[data-testid="stToolbar"]{display:none;}
section[data-testid="stFileUploader"]>div{border-radius:12px;}
</style>
"""


# ====================== ⑤ Streamlit UI ======================
def main():
    st.set_page_config(
        page_title="客服反馈 → PRD 生成器",
        page_icon="📝",
        layout="wide",
    )
    st.markdown(PREMIUM_CSS, unsafe_allow_html=True)

    # ---------- 侧边栏：配置 & 说明 ----------
    with st.sidebar:
        st.title("⚙️ 配置")
        st.caption("优先级：部署 secrets/环境变量 > 此处临时填写 > 代码默认值。")
        ui_key = st.text_input("API Key（可选，留空用代码默认值）",
                               type="password", value="")
        ui_url = st.text_input("Base URL（可选）", value="")
        ui_model = st.text_input("模型名称（可选）", value="")
        st.divider()
        st.markdown("### 关于本项目")
        st.markdown("把碎片化客服反馈，一键结构化为产研可阅读的 PRD。")
        st.markdown("---")
        st.caption("兼容 DeepSeek / 智谱 GLM / OpenAI 等 OpenAI 格式接口。")

    # 决定最终使用的配置：平台 secrets/环境变量 > 侧边栏临时填写 > 代码硬编码默认值
    api_key = ui_key.strip() or _get_secret("API_KEY", API_KEY)
    base_url = ui_url.strip() or _get_secret("BASE_URL", BASE_URL)
    model = ui_model.strip() or _get_secret("MODEL_NAME", MODEL_NAME)

    # ---------- 主区域 ----------
    st.markdown(
        '<div class="title-card">'
        '<div class="title-text">📝 客服反馈 → 产品需求文档（PRD）生成器</div>'
        '<div class="subtitle">把日常碎片化的用户反馈，自动提炼为标准 PRD，直接发给产研团队。</div>'
        '</div>', unsafe_allow_html=True)

    # 初始化 session_state
    if "feedback_text" not in st.session_state:
        st.session_state.feedback_text = ""
    if "prd_result" not in st.session_state:
        st.session_state.prd_result = ""
    if "last_cost" not in st.session_state:
        st.session_state.last_cost = 0.0
    if "last_count" not in st.session_state:
        st.session_state.last_count = 0

    # Step 1：输入区
    st.subheader("① 输入客服反馈")
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("✨ 填充示例数据", use_container_width=True):
            st.session_state.feedback_text = EXAMPLE_FEEDBACK
        uploaded_file = st.file_uploader("上传 CSV / TXT（可选）",
                                          type=["csv", "txt"],
                                          help="CSV 会自动识别“反馈内容”列；TXT 按行读取。")
        if uploaded_file is not None:
            parsed = parse_uploaded_file(uploaded_file)
            if parsed:
                st.session_state.feedback_text = parsed
                st.info(f"已从文件读取 {count_feedback(parsed)} 条反馈，已填入下方文本框。")

    with col1:
        fb_text = st.text_area(
            "粘贴客服反馈（每行一条；可多类混合，AI 会自动聚类）",
            height=240,
            key="feedback_text",
            placeholder="例如：\n用户说登录就提示账号异常已冻结……\n结算页点支付经常转圈还重复扣款……",
        )

    # 合并输入
    final_text = build_feedback_text(fb_text, uploaded_file if uploaded_file else None)
    fb_count = count_feedback(final_text)

    # Step 2：生成
    st.subheader("② 生成 PRD")
    c1, c2 = st.columns([1, 3])
    with c1:
        generate = st.button("🚀 一键生成 PRD", type="primary", use_container_width=True)

    if generate:
        # 错误前置校验
        if not api_key or api_key.startswith("sk-xxxxxxxx"):
            st.error("❌ 尚未配置有效的 API Key：请在 app.py 顶部填入，或在左侧边栏临时填写。")
        elif fb_count == 0:
            st.warning("⚠️ 输入为空：请粘贴反馈，或点击「填充示例数据」，或上传文件。")
        else:
            with st.spinner("🤖 AI 正在把反馈结构化为 PRD，请稍候……"):
                start = time.time()
                try:
                    prd = generate_prd(final_text, api_key, base_url, model)
                    cost = time.time() - start
                    if not prd.strip():
                        st.error("❌ 模型返回为空，请重试或检查模型配置。")
                    else:
                        st.session_state.prd_result = prd
                        st.session_state.last_cost = cost
                        st.session_state.last_count = fb_count
                        st.success(f"✅ 生成完成：{fb_count} 条反馈 → PRD，耗时 {cost:.1f}s")
                except AuthenticationError:
                    st.error("❌ 鉴权失败：API Key 无效或已过期，请检查配置。")
                except APITimeoutError:
                    st.error(f"❌ 请求超时（>{REQUEST_TIMEOUT}s）：请检查网络或调大 REQUEST_TIMEOUT。")
                except RateLimitError:
                    st.error("❌ 触发限流：请稍后重试，或检查账号额度 / 降低调用频率。")
                except APIError as e:
                    st.error(f"❌ 模型接口报错：{e}")
                except Exception as e:  # noqa: BLE001
                    st.error(f"❌ 未知错误：{e}")

    # Step 3：输出区
    if st.session_state.prd_result:
        st.subheader("③ 生成结果")
        # 数据指标条：体现“数据敏感度”
        m1, m2, m3 = st.columns(3)
        m1.metric("输入反馈条数", st.session_state.last_count)
        m2.metric("处理耗时", f"{st.session_state.last_cost:.1f}s")
        # 粗略统计聚类出的需求份数（按二级“需求归类”标题计数）
        n_prd = st.session_state.prd_result.count("## 【需求归类")
        m3.metric("聚类需求份数", max(n_prd, 1))

        # 概览表单独用 dataframe 渲染（强化“数据敏感度”展示，且可排序/筛选）
        overview_df, has_overview = parse_overview_table(st.session_state.prd_result)
        if has_overview:
            detail_md = strip_overview_section(st.session_state.prd_result)
            # 优先级筛选器
            selected = st.multiselect(
                "🔎 按优先级筛选（可多选）", ["P0", "P1", "P2"], default=["P0", "P1", "P2"],
                help="只展示选中优先级的聚类需求，下方概览表与详细 PRD 同步过滤。",
            )
            filtered_df = filter_overview_df(overview_df, selected)
            st.markdown("#### 📊 需求概览")
            if filtered_df.empty:
                st.info("当前筛选条件下没有匹配的聚类需求。")
            else:
                st.dataframe(filtered_df, use_container_width=True, hide_index=True)
                csv_bytes = filtered_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "⬇️ 导出需求清单（CSV）", csv_bytes,
                    file_name="需求清单.csv", mime="text/csv", use_container_width=True,
                )
            # 详细 PRD 同步按优先级过滤
            filtered_detail, any_shown = filter_prd_markdown(detail_md, overview_df, selected)
            if not any_shown:
                st.info("当前筛选条件下没有可展示的详细 PRD。")
            else:
                st.markdown(filtered_detail)
        else:
            st.markdown(st.session_state.prd_result)

        # 复制 / 下载区
        st.divider()
        c_a, c_b, c_c = st.columns(3)
        with c_a:
            copy_button("📋 复制（飞书/文档 Markdown）",
                        st.session_state.prd_result, "feishu")
        with c_b:
            copy_button("📋 复制（企微纯文本）",
                        to_wecom_plain(st.session_state.prd_result), "wecom")
        with c_c:
            st.download_button(
                label="⬇️ 下载 PRD（.md）",
                data=st.session_state.prd_result,
                file_name="PRD_生成结果.md",
                mime="text/markdown",
                use_container_width=True,
            )


if __name__ == "__main__":
    main()
