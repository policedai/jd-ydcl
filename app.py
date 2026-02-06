# -*- coding: utf-8 -*-
import streamlit as st
import json
from openai import OpenAI
# 导入飞书官方SDK
import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *

# ==========================================
# 1. 核心配置（无需修改）
# ==========================================
FEISHU_APP_ID = st.secrets["FEISHU_APP_ID"]
FEISHU_APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
FEISHU_APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
FEISHU_TABLE_ID = st.secrets["FEISHU_TABLE_ID"]

# AI配置
DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
AI_BASE_URL = "https://api.deepseek.com"

# 全局调试开关
DEBUG = True

# ==========================================
# 初始化飞书官方SDK Client
# ==========================================
def get_feishu_client():
    """创建飞书SDK客户端，全局复用"""
    try:
        client = lark.Client.builder() \
            .app_id(FEISHU_APP_ID) \
            .app_secret(FEISHU_APP_SECRET) \
            .build()  # 直接删掉log_level那一行，用默认配置
        if DEBUG: print("✅ 飞书SDK客户端初始化成功")
        return client
    except Exception as e:
        st.error(f"❌ 飞书SDK客户端初始化失败：{str(e)}")
        if DEBUG: print(f"❌ 飞书SDK初始化异常：{str(e)}")
        return None

feishu_client = get_feishu_client()

# ==========================================
# 2. 飞书API工具函数
# ==========================================
def get_all_tag_options():
    """获取type=4多选「标签」字段的所有选项（基于SDK）"""
    if not feishu_client:
        return []
    try:
        request = ListAppTableFieldRequest.builder() \
            .app_token(FEISHU_APP_TOKEN) \
            .table_id(FEISHU_TABLE_ID) \
            .build()
        response: ListAppTableFieldResponse = feishu_client.bitable.v1.app_table_field.list(request)
        if not response.success():
            if DEBUG: print(f"❌ 获取字段失败：code={response.code}, msg={response.msg}")
            return []
        fields = response.data.items
        tag_list = []
        for field in fields:
            if field.field_name == "标签" and field.type == 4 and field.ui_type == "MultiSelect":
                options = field.property.options
                tag_list = [opt.name for opt in options if opt.name and opt.name.strip()]
                break
        if DEBUG: print(f"✅ 获取标签选项成功，共{len(tag_list)}个：{tag_list[:5]}...")
        return tag_list
    except Exception as e:
        if DEBUG: print(f"❌ 获取标签选项异常：{str(e)}")
        return []

def fetch_records():
    """获取表格所有记录（基于SDK，page_size=100）"""
    if not feishu_client:
        return []
    try:
        request = ListAppTableRecordRequest.builder() \
            .app_token(FEISHU_APP_TOKEN) \
            .table_id(FEISHU_TABLE_ID) \
            .page_size(100) \
            .build()
        response: ListAppTableRecordResponse = feishu_client.bitable.v1.app_table_record.list(request)
        if not response.success():
            st.error(f"❌ 获取飞书记录失败：{response.msg}（代码{response.code}）")
            if DEBUG: print(f"❌ 获取记录失败：code={response.code}, msg={response.msg}")
            return []
        records = []
        for rec in response.data.items:
            records.append({
                "record_id": rec.record_id,
                "fields": rec.fields
            })
        if DEBUG: print(f"✅ 获取飞书记录成功，共{len(records)}条")
        return records
    except Exception as e:
        st.error(f"❌ 获取飞书记录异常：{str(e)}")
        if DEBUG: print(f"❌ 获取记录异常：{str(e)}")
        return []

def update_record(record_id, fields_data):
    """更新飞书记录（基于SDK，核心适配type=4多选字段）"""
    if not feishu_client or not record_id or not isinstance(fields_data, dict) or not fields_data:
        return None
    if DEBUG:
        print(f"\n===== 【更新记录】开始 - ID: {record_id} =====")
        print(f"【更新记录】待更新字段：{fields_data}")
    try:
        request = UpdateAppTableRecordRequest.builder() \
            .app_token(FEISHU_APP_TOKEN) \
            .table_id(FEISHU_TABLE_ID) \
            .record_id(record_id) \
            .request_body(AppTableRecord.builder().fields(fields_data).build()) \
            .build()
        response: UpdateAppTableRecordResponse = feishu_client.bitable.v1.app_table_record.update(request)
        if not response.success():
            err_msg = f"❌ 标签更新失败：{response.msg}（代码{response.code}）"
            st.error(err_msg)
            if DEBUG: print(f"❌ 更新记录失败：code={response.code}, msg={response.msg}")
            return None
        st.toast("🏷️ 标签同步到飞书成功！", icon="✅")
        if DEBUG: print(f"✅ 记录更新成功 - ID: {record_id}")
        return response.data
    except Exception as e:
        err_msg = f"❌ 标签更新异常：{str(e)}"
        st.error(err_msg)
        if DEBUG: print(err_msg)
        return None

def save_record(fields):
    """新增飞书记录（基于SDK，适配type=4多选字段，修复record_id嵌套问题）"""
    if not feishu_client or not isinstance(fields, dict) or not fields:
        return None
    try:
        request = CreateAppTableRecordRequest.builder() \
            .app_token(FEISHU_APP_TOKEN) \
            .table_id(FEISHU_TABLE_ID) \
            .request_body(AppTableRecord.builder().fields(fields).build()) \
            .build()
        response: CreateAppTableRecordResponse = feishu_client.bitable.v1.app_table_record.create(request)
        if not response.success():
            err_msg = f"❌ 新增文章失败：{response.msg}（代码{response.code}）"
            st.error(err_msg)
            if DEBUG: print(f"❌ 新增记录失败：code={response.code}, msg={response.msg}")
            return None
        # 修复：新增记录的record_id在response.data.record里
        record_id = response.data.record.record_id
        st.success("✅ 新增文章并同步到飞书成功！")
        if DEBUG: print(f"✅ 新增记录成功 - ID: {record_id}")
        return response.data.record
    except Exception as e:
        err_msg = f"❌ 新增文章异常：{str(e)}"
        st.error(err_msg)
        if DEBUG: print(err_msg)
        return None

# ==========================================
# 3. AI 分析逻辑（核心修改：考生视角+量化要求+纯中文解析）
# ==========================================
def analyze_content(text):
    """AI分析英语阅读（北京中学生视角，纯中文解析，满足量化要求）"""
    if not text or len(text.strip()) < 10:
        st.error("❌ 原文过短，无法解析")
        return json.dumps({})
    try:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=AI_BASE_URL)
        # 丰富提示词：高考考生视角+纯中文+强制量化要求（单词≥8/短语≥5/长难句≥3）
        prompt = f"""
        请以北京中学生英语中高考考生的视角，对以下英语阅读文本进行全面解析，所有解析内容均使用中文，且严格满足以下量化要求：
        1. 重点难点单词：提取至少8个，包含【英文单词、国际音标、中文释义（结合阅读语境）】；
        2. 核心高频短语：提取至少5个，包含【英文短语、中文释义（结合阅读语境）】；
        3. 经典长难句：提取至少3个，对每个长难句分别做【原句、语法结构分析（标注从句/非谓语/倒装等考点）、中文精准翻译】；
        4. 文章核心主旨：用简洁的中文总结文章中心思想和写作目的；
        5. 全文对照翻译：给出原文的完整中文翻译，贴合语境，语句通顺。

        请严格按照以下JSON格式返回结果，不要添加任何额外内容，不要用代码块包裹：
        {{
            "theme": "文章核心主旨（中文）",
            "difficult_words": [{{"word": "英文单词", "phonetic": "国际音标", "meaning": "中文释义"}}],
            "phrases": ["英文短语 中文释义", "英文短语 中文释义"],
            "sentences": [{{"original": "长难句原句", "analysis": "语法结构分析（中文，考点标注）", "translation": "中文翻译"}}],
            "full_translation": "全文完整中文翻译（中文）"
        }}

        英语阅读文本：
        {text}
        """
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            response_format={'type': 'json_object'},
            temperature=0.1
        )
        raw = response.choices[0].message.content
        clean_json = raw.replace("```json", "").replace("```", "").strip()
        json.loads(clean_json)  # 校验JSON格式
        return clean_json
    except json.JSONDecodeError:
        st.error("❌ AI返回非合法JSON格式，请重新录入原文")
        return json.dumps({})
    except Exception as e:
        st.error(f"❌ AI分析异常: {str(e)}")
        if DEBUG: print(f"AI分析异常详情: {str(e)}")
        return json.dumps({})

# ==========================================
# 4. UI 界面（核心修改：删除重新分析按钮）
# ==========================================
st.set_page_config(page_title="高考英语阅读智能解析", layout="wide")

# CSS 优化
st.markdown("""
    <style>
    .stRadio [role=radiogroup] { spacing: 0px; }
    .stRadio label { padding: 5px 10px; border-radius: 4px; margin-bottom: 2px; }
    .phrase-tag { background: #e3f2fd; padding: 2px 8px; border-radius: 4px; margin: 3px; display: inline-block; color: #1565c0; font-size: 13px; font-weight: 500; }
    .article-box { border: 1px solid #eee; padding: 15px; background: white; border-radius: 8px; height: 500px; overflow-y: auto; font-family: 'Times New Roman', serif; font-size: 16px; line-height: 1.6; }
    .word-card { background: #f9f9f9; border-left: 3px solid #1565c0; padding: 8px; margin-bottom: 5px; border-radius: 4px; font-size: 14px; }
    .streamlit-expanderHeader { white-space: normal !important; width: 100% !important; }
    .stButton > button { margin-bottom: 5px; }
    </style>
""", unsafe_allow_html=True)

# 初始化session_state
if 'db' not in st.session_state:
    st.session_state.db = fetch_records()
if 'tag_options' not in st.session_state:
    st.session_state.tag_options = get_all_tag_options()
if 'btn_loading' not in st.session_state:
    st.session_state.btn_loading = False

# --- 侧边栏筛选 ---
with st.sidebar:
    st.title("⚙️ 筛选管理")
    if st.button("🔄 刷新云端数据", use_container_width=True, type="secondary"):
        with st.spinner("刷新中..."):
            st.session_state.db = fetch_records()
            st.session_state.tag_options = get_all_tag_options()
        st.rerun()
    st.divider()
    selected_filters = st.multiselect("按标签筛选", st.session_state.tag_options, placeholder="选择标签筛选...")
    search_key = st.text_input("搜索文章标题", placeholder="输入标题关键词...")

# --- 主界面 ---
tab_read, tab_add = st.tabs(["📖 阅读解析", "➕ 录入文章"])

with tab_read:
    data = st.session_state.db.copy()
    # 筛选逻辑
    if selected_filters and data:
        filtered_data = []
        for r in data:
            record_tags = r['fields'].get('标签', [])
            if isinstance(record_tags, list) and set(selected_filters) & set(record_tags):
                filtered_data.append(r)
        data = filtered_data
    if search_key and data:
        data = [r for r in data if search_key.lower() in r['fields'].get('标题', '').lower()]

    # 列布局
    col_l, col_r = st.columns([0.6, 3]) 
    
    with col_l:
        st.caption("文章选择")
        if data:
            titles = [r['fields'].get('标题', '无题') for r in data]
            sel_title = st.radio("文章列表", titles, label_visibility="collapsed")
            cur_rec = next(r for r in data if r['fields'].get('标题') == sel_title)
        else: 
            st.info("📭 暂无匹配的文章记录")
            cur_rec = None

    with col_r:
        if cur_rec:
            rid, f = cur_rec['record_id'], cur_rec['fields']
            
            # 顶部标题栏（删除重新分析按钮）
            st.subheader(f.get('标题', '无题'))

            # 标签管理区
            st.markdown("### 🏷️ 标签管理")
            default_tags = f.get('标签', [])
            default_tags = default_tags if isinstance(default_tags, list) else []
            updated_tags = st.multiselect(
                "选择标签（可多选）", 
                st.session_state.tag_options, 
                default=default_tags, 
                key=f"edit_tag_{rid}",
                placeholder="请选择文章标签..."
            )
            if updated_tags != default_tags:
                if st.button("💾 保存标签", key=f"save_tag_{rid}", use_container_width=True, type="primary"):
                    with st.spinner("同步标签到飞书..."):
                        update_record(rid, {"标签": updated_tags})
                        st.session_state.db = fetch_records()
                        st.rerun()

            st.divider()
            
            # 解析区布局
            c_left, c_right = st.columns([1, 1.2])
            with c_left:
                st.markdown("**📝 原文**")
                content = f.get('正文', '暂无原文内容')
                st.markdown(f"<div class='article-box'>{content}</div>", unsafe_allow_html=True)
                with st.expander("📖 查看全文对照翻译", expanded=False):
                    try:
                        ans = json.loads(f.get('分析结果', '{}'))
                        full_trans = ans.get('full_translation', '暂无全文翻译')
                        st.write(full_trans)
                    except: 
                        st.warning("⚠️ 解析格式错误，建议重新录入原文")

            with c_right:
                st.markdown("**🧠 高考视角深度解析**")
                try:
                    ai_result = f.get('分析结果', '{}')
                    ans = json.loads(ai_result) if ai_result.strip() else {}
                    # 主题核心
                    theme = ans.get('theme', '暂无文章主旨分析')
                    st.success(f"**📌 文章核心主旨：** {theme}")
                    
                    # 重点单词
                    st.markdown("### 📑 重点难点单词")
                    words = ans.get('difficult_words', [])
                    if words and isinstance(words, list):
                        for w in words:
                            if isinstance(w, dict):
                                word = w.get('word', '未知')
                                phonetic = w.get('phonetic', '无音标')
                                meaning = w.get('meaning', '无释义')
                                st.markdown(f"<div class='word-card'><b>{word}</b> [{phonetic}] <br/>{meaning}</div>", unsafe_allow_html=True)
                    else:
                        st.info("暂无重点单词解析")

                    # 核心短语
                    st.markdown("### 🔗 核心高频短语")
                    ps = ans.get('phrases', [])
                    if ps and isinstance(ps, list) and len(ps) > 0:
                        ps_html = "".join([f"<span class='phrase-tag'>{p}</span>" for p in ps if p])
                        st.markdown(ps_html, unsafe_allow_html=True)
                    else:
                        st.info("暂无核心短语解析")

                    # 长难句拆解（完整显示，无截断）
                    st.markdown("### 🚀 经典长难句解析")
                    sentences = ans.get('sentences', [])
                    if sentences and isinstance(sentences, list):
                        for i, s in enumerate(sentences, 1):
                            if isinstance(s, dict):
                                original = s.get('original', '无原句')
                                analysis = s.get('analysis', '无语法分析')
                                translation = s.get('translation', '无翻译')
                                # 完整显示原句，自动换行
                                exp_title = f"📌 长难句 {i}：{original}"
                                with st.expander(exp_title, expanded=False):
                                    st.markdown("**【语法考点分析】**")
                                    st.write(analysis)
                                    st.markdown("**【精准中文翻译】**")
                                    st.info(translation)
                    else:
                        st.info("暂无长难句解析")
                except Exception as e:
                    st.warning(f"⚠️ 解析加载失败：{str(e)}，建议重新录入原文")

# --- 录入文章页 ---
with tab_add:
    st.header("✍️ 录入英语阅读材料")
    with st.form("add_form", clear_on_submit=True):
        t = st.text_input("文章标题*", placeholder="如：2025海淀高三一模阅读A篇、2024全国甲卷完形填空...")
        c = st.text_area("英文原文*", height=300, placeholder="请粘贴纯文本英文原文，无需格式，支持阅读/完形/七选五...")
        sel_t = st.multiselect("添加标签", st.session_state.tag_options, placeholder="如：高三、一模、记叙文、科普文...")
        submit_btn = st.form_submit_button("🚀 录入并生成解析", use_container_width=True, type="primary")
        if submit_btn:
            if not t or not t.strip():
                st.error("❌ 文章标题不能为空！")
            elif not c or not c.strip():
                st.error("❌ 英文原文不能为空！")
            else:
                with st.spinner("📝 正在录入并生成解析..."):
                    save_res = save_record({
                        "标题": t.strip(), 
                        "正文": c.strip(), 
                        "标签": sel_t, 
                        "分析结果": analyze_content(c.strip())
                    })
                    if save_res:
                        st.session_state.db = fetch_records()
                        st.session_state.tag_options = get_all_tag_options()
                        st.rerun()

# 重置按钮加载状态

st.session_state.btn_loading = False

