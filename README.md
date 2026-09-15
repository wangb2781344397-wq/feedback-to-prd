# 客服反馈 → PRD 自动生成器

把碎片化的客服 / 用户反馈，一键结构化为产研可直接阅读的标准《产品需求文档（PRD）》。
基于 **Streamlit + 大模型（OpenAI SDK 格式，兼容 DeepSeek / 智谱 GLM / GPT）** 构建。

> 项目定位：客服运营管培生（储备干部）求职 Demo —— 展示「AI 工具提效 · 数据敏感度 · 结构化表达」。

## 项目简介

日常客服 / 运营同学会收到大量碎片化的用户反馈（吐槽、投诉、建议），但这些 raw 文本很难直接传递给产研团队。
本项目用一个轻量 Web 应用，把这类文本自动整理成结构清晰、可直接排期的 PRD，降低沟通损耗。

## 核心功能

- **多源输入**：文本框多行粘贴（每行一条）+ 上传 CSV / TXT 批量导入 + 一键填充示例数据。
- **结构化提炼**：内置「资深产品经理」视角的 System Prompt，输出 `【需求背景】【问题描述】【影响面评估】【优先级建议】【建议方案】` 五段式标准 PRD。
- **多类别自动聚类**：混合反馈自动归类，输出多份 PRD，并附「需求概览」表（归类 / 条数 / 优先级 / 一句话结论）。
- **数据敏感度展示**：概览表可排序 / 筛选、支持 CSV 导出；优先级筛选器同步过滤详版 PRD。
- **多端复制**：一键复制为飞书 / 文档 Markdown，或企微纯文本，方便直接转发。

## 展示的能力（求职角度）

| 能力 | 在项目中如何体现 |
|---|---|
| AI 工具提效 | 把原本需人工阅读的碎片反馈，自动生成标准 PRD，单条处理秒级完成 |
| 数据敏感度 | 自动聚类、量化影响面与优先级，并输出可筛选 / 可导出的概览表 |
| 结构化表达 | 固定五段式 PRD 模板，确保产研一眼看懂、可直接排期 |

## 技术栈

Python 3.9+ · Streamlit · OpenAI SDK（兼容 DeepSeek / 智谱 GLM / GPT）· pandas

## 本地运行

```bash
# 1. 进入项目目录
cd <项目目录>

# 2. 创建并激活虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置 API Key（三选一）
#    a. 运行时在页面左侧边栏填写（推荐，Key 不落库）
#    b. 设置环境变量 API_KEY / BASE_URL / MODEL_NAME
#    c. 直接改 app.py 顶部 API_KEY / BASE_URL / MODEL_NAME（不推荐，勿提交真实 Key）

# 5. 启动
streamlit run app.py
# 浏览器打开 http://localhost:8501
```

## 部署建议（对外公开 Demo）

- **Hugging Face Spaces（推荐，默认公开、免登录）**
  1. 在 https://huggingface.co 新建 Space，SDK 选 **Streamlit**。
  2. 上传本仓库的 `app.py` / `requirements.txt` / `README.md`（`README.md` 需含 Space 配置 frontmatter，见 `hf-space/README.md`）。
  3. 在 Space 的 `Settings → Repository secrets` 填入 `API_KEY` / `BASE_URL` / `MODEL_NAME` 三条，Restart 即可。
- **Streamlit Community Cloud**：可正常部署运行，但免费版对所有访问者强制要求登录，不适合作为对外公开链接（如简历）。
- **本地 / 源码**：直接把本仓库链接放入简历，审阅者可见完整源码与说明。

> 密钥优先级：`平台 Secrets / 环境变量` > 页面边栏填写 > 代码默认值。生产部署请务必走 Secrets，勿硬编码 Key。

## 目录结构

```
.
├── app.py            # 主程序（Streamlit 应用）
├── requirements.txt  # 依赖
└── README.md         # 项目说明
```

## 说明

本项目为求职 Demo，示例反馈与 PRD 均为演示数据；调用大模型需自备 API Key，费用由调用方承担。
