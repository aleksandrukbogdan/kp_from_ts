import streamlit as st
import asyncio
from temporalio.client import Client
from workflows import ProposalWorkflow
import pandas as pd
import base64
import os
import streamlit.components.v1 as components

# --- Конфигурация ---
# Если переменная IS_DEV=true, используем localhost, иначе IP продакшена
IS_DEV = os.getenv('IS_DEV', 'false').lower() == 'true'
SERVER_ADDRESS = 'localhost' if IS_DEV else '10.109.50.250'
PORTAL_PORT = 8085  # Порт портала

# Настройка страницы
st.set_page_config(
    page_title="НИР-центр | Агент КП", 
    layout="wide", 
    page_icon="",
    initial_sidebar_state="collapsed"
)

# --- Проверка авторизации через JavaScript ---
auth_check_script = f'''
<script>
    // Попытка прочитать куки. В Streamlit iframe они могут быть доступны через document.cookie
    function getCookie(name) {{
        var nameEQ = name + "=";
        var ca = document.cookie.split(';');
        for(var i=0;i < ca.length;i++) {{
            var c = ca[i];
            while (c.charAt(0)==' ') c = c.substring(1,c.length);
            if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
        }}
        return null;
    }}

    const authToken = getCookie('portal_auth_token');
    const portalUser = getCookie('portal_user');
    
    // Адрес портала для редиректа
    const redirectUrl = 'http://{SERVER_ADDRESS}:{PORTAL_PORT}/login';

    if (!authToken || !portalUser) {{
        // ВАЖНО: Используем window.top для редиректа ВСЕЙ страницы, а не iframe
        try {{
            window.top.location.href = redirectUrl;
        }} catch (e) {{
            // Fallback если доступ к top блокирован (хотя на одном домене должно работать)
            window.location.href = redirectUrl;
        }}
    }}
</script>
'''

# Вставляем скрипт проверки
components.html(auth_check_script, height=0)

# --- Функция для загрузки шрифта ---
def get_font_base64(font_path):
    try:
        with open(font_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except:
        return None

# Пути к шрифтам
font_regular = get_font_base64("/app/fonts/Onest-Regular.ttf")
font_medium = get_font_base64("/app/fonts/Onest-Medium.ttf")

# --- Material 3 CSS с брендом НИР-центр ---
material3_css = f"""
<style>
    /* ========== Font Face ========== */
    @font-face {{
        font-family: 'Onest';
        src: url(data:font/truetype;base64,{font_regular or ''}) format('truetype');
        font-weight: 400;
        font-style: normal;
    }}
    @font-face {{
        font-family: 'Onest';
        src: url(data:font/truetype;base64,{font_medium or ''}) format('truetype');
        font-weight: 500;
        font-style: normal;
    }}

    /* ========== CSS Variables ========== */
    :root {{
        --md-sys-color-primary: #FF6B35;
        --md-sys-color-on-primary: #FFFFFF;
        --md-sys-color-primary-container: #FFDBCF;
        --md-sys-color-secondary: #1E3A5F;
        --md-sys-color-surface: #FFFFFF;
        --md-sys-color-surface-variant: #F5F5F5;
        --md-sys-color-background: #FDF8F6;
        --md-sys-color-on-surface: #1C1B1F;
        --md-sys-color-on-surface-variant: #49454F;
        --md-sys-color-outline: #E0E0E0;
        --md-sys-color-success: #4CAF50;
    }}

    /* ========== Global Styles ========== */
    html, body, [class*="css"] {{
        font-family: 'Onest', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }}

    /* Hide Streamlit defaults */
    #MainMenu {{visibility: hidden;}}
    header {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    
    /* Background */
    .stApp {{
        background: var(--md-sys-color-background);
    }}

    /* ========== Custom Header ========== */
    .custom-header {{
        background: var(--md-sys-color-surface);
        padding: 12px 24px;
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 1000;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        display: flex;
        align-items: center;
        justify-content: space-between;
    }}

    .header-left {{
        display: flex;
        align-items: center;
        gap: 16px;
    }}

    .brand-logo-svg {{
        height: 24px;
        width: auto;
    }}

    .header-divider {{
        color: var(--md-sys-color-outline);
        font-size: 20px;
    }}

    .app-name {{
        font-size: 14px;
        font-weight: 500;
        color: var(--md-sys-color-on-surface-variant);
    }}

    .back-button {{
        display: inline-flex !important;
        align-items: center !important;
        gap: 6px !important;
        padding: 8px 16px !important;
        background: transparent !important;
        color: var(--md-sys-color-primary) !important;
        border: 1px solid var(--md-sys-color-primary) !important;
        border-radius: 100px !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        text-decoration: none !important;
        transition: all 0.2s ease !important;
    }}

    .back-button:hover {{
        background: var(--md-sys-color-primary-container) !important;
        color: var(--md-sys-color-primary) !important;
        text-decoration: none !important;
    }}

    .back-button:visited {{
        color: var(--md-sys-color-primary) !important;
        text-decoration: none !important;
    }}

    /* Add padding to main content for fixed header */
    .block-container {{
        padding-top: 80px !important;
    }}

    /* ========== Loading Overlay ========== */
    .loading-overlay {{
        background: var(--md-sys-color-surface);
        border-radius: 24px;
        padding: 48px;
        text-align: center;
        box-shadow: 0 4px 24px rgba(0,0,0,0.08);
        max-width: 480px;
        margin: 80px auto 0;
    }}

    .loading-spinner {{
        width: 64px;
        height: 64px;
        border: 4px solid var(--md-sys-color-outline);
        border-top-color: var(--md-sys-color-primary);
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 24px;
    }}

    @keyframes spin {{
        to {{ transform: rotate(360deg); }}
    }}

    .loading-text {{
        font-size: 20px;
        font-weight: 500;
        color: var(--md-sys-color-secondary);
        margin-bottom: 8px;
    }}

    .loading-subtext {{
        font-size: 14px;
        color: var(--md-sys-color-on-surface-variant);
    }}

    /* ========== Data Editor Improvements ========== */
    .cost-matrix-hint {{
        font-size: 13px;
        color: var(--md-sys-color-on-surface-variant);
        margin-bottom: 12px;
    }}

    /* ========== Titles ========== */
    h1 {{
        color: var(--md-sys-color-secondary) !important;
        font-weight: 600 !important;
        font-size: 1.75rem !important;
        margin-bottom: 8px !important;
    }}

    h2, h3 {{
        color: var(--md-sys-color-secondary) !important;
        font-weight: 500 !important;
    }}

    /* ========== Cards ========== */
    .card {{
        background: var(--md-sys-color-surface);
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        margin-bottom: 16px;
    }}

    .card-header {{
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 16px;
    }}

    .card-icon {{
        width: 48px;
        height: 48px;
        background: var(--md-sys-color-primary-container);
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
    }}

    .card-title {{
        font-size: 18px;
        font-weight: 500;
        color: var(--md-sys-color-secondary);
        margin: 0;
    }}

    /* ========== Buttons ========== */
    .stButton > button {{
        background: var(--md-sys-color-primary) !important;
        color: var(--md-sys-color-on-primary) !important;
        border: none !important;
        border-radius: 100px !important;
        padding: 12px 24px !important;
        font-weight: 500 !important;
        font-family: 'Onest', sans-serif !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 1px 3px rgba(255, 107, 53, 0.3) !important;
    }}

    .stButton > button:hover {{
        background: #E55A28 !important;
        box-shadow: 0 4px 12px rgba(255, 107, 53, 0.4) !important;
        transform: translateY(-1px);
    }}

    .stButton > button:active {{
        transform: translateY(0);
    }}

    /* Secondary button style */
    .stButton > button[kind="secondary"] {{
        background: transparent !important;
        color: var(--md-sys-color-primary) !important;
        border: 1px solid var(--md-sys-color-primary) !important;
        box-shadow: none !important;
    }}

    /* ========== Inputs ========== */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {{
        border-radius: 12px !important;
        border: 1px solid var(--md-sys-color-outline) !important;
        font-family: 'Onest', sans-serif !important;
        padding: 12px 16px !important;
        transition: border-color 0.2s ease !important;
    }}

    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {{
        border-color: var(--md-sys-color-primary) !important;
        box-shadow: 0 0 0 2px rgba(255, 107, 53, 0.1) !important;
    }}

    /* ========== File Uploader ========== */
    .stFileUploader > div {{
        border-radius: 16px !important;
        border: 2px dashed var(--md-sys-color-outline) !important;
        background: var(--md-sys-color-surface) !important;
        transition: all 0.2s ease !important;
    }}

    .stFileUploader > div:hover {{
        border-color: var(--md-sys-color-primary) !important;
        background: var(--md-sys-color-primary-container) !important;
    }}

    /* ========== Metrics ========== */
    [data-testid="stMetricValue"] {{
        color: var(--md-sys-color-primary) !important;
        font-weight: 600 !important;
        font-size: 2rem !important;
    }}

    [data-testid="stMetricLabel"] {{
        color: var(--md-sys-color-on-surface-variant) !important;
    }}

    /* ========== Data Editor ========== */
    .stDataFrame {{
        border-radius: 12px !important;
        overflow: hidden;
    }}

    /* ========== Expander ========== */
    .streamlit-expanderHeader {{
        background: var(--md-sys-color-surface-variant) !important;
        border-radius: 12px !important;
        font-weight: 500 !important;
    }}

    /* ========== Sidebar ========== */
    [data-testid="stSidebar"] {{
        background: var(--md-sys-color-surface) !important;
    }}

    [data-testid="stSidebar"] .stButton > button {{
        background: transparent !important;
        color: #F44336 !important;
        border: 1px solid #F44336 !important;
        box-shadow: none !important;
    }}

    /* ========== Alerts ========== */
    .stSuccess {{
        background: #E8F5E9 !important;
        border-left: 4px solid var(--md-sys-color-success) !important;
        border-radius: 8px !important;
    }}

    .stInfo {{
        background: var(--md-sys-color-primary-container) !important;
        border-left: 4px solid var(--md-sys-color-primary) !important;
        border-radius: 8px !important;
    }}

    .stWarning {{
        background: #FFF3E0 !important;
        border-left: 4px solid #FF9800 !important;
        border-radius: 8px !important;
    }}

    /* ========== Step Indicator ========== */
    .step-indicator {{
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 24px;
    }}

    .step-badge {{
        width: 32px;
        height: 32px;
        background: var(--md-sys-color-primary);
        color: white;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 600;
        font-size: 14px;
    }}

    .step-badge.inactive {{
        background: var(--md-sys-color-outline);
    }}

    .step-badge.done {{
        background: var(--md-sys-color-success);
    }}

    .step-line {{
        flex: 1;
        height: 2px;
        background: var(--md-sys-color-outline);
    }}

    .step-line.active {{
        background: var(--md-sys-color-primary);
    }}
</style>
"""

st.markdown(material3_css, unsafe_allow_html=True)

# --- Custom Header ---
header_html = f"""
<div class="custom-header">
    <div class="header-left">
        <svg class="brand-logo-svg" width="160" height="22" viewBox="0 0 609 79" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M319.017 53.2139H345.819V0H359.178V53.2139H366.82V78.3311H353.446V64.958H305.714V0H319.017V53.2139ZM13.3096 26.9736H40.125V0H53.4941V64.958H40.125V38.8096H13.1826L13.3096 64.958H0V0H13.3096V26.9736ZM81.8975 41.9287L111.534 0H122.273V64.958H108.964V23.3955L79.3271 64.958H68.5879V0H81.8975V41.9287ZM162.524 0C166.44 2.8971e-05 169.99 0.42794 173.172 1.28418C176.354 2.0793 179.046 3.39469 181.249 5.22949C183.513 7.00323 185.227 9.35814 186.39 12.2939C187.613 15.1687 188.194 18.7171 188.133 22.9375C188.072 26.6071 187.43 29.8793 186.206 32.7539C184.982 35.5675 183.268 37.9529 181.065 39.9102C178.924 41.8062 176.323 43.2747 173.264 44.3145C170.265 45.293 166.991 45.7822 163.442 45.7822H150.867V64.958H137.558V0H162.524ZM420.888 11.8359H387.77V26.9736H416.668V38.8096H387.77V53.2139H420.888V64.958H374.468V0H420.888V11.8359ZM446.997 26.9736H473.812V0H487.183V64.958H473.812V38.8096H446.871L446.997 64.958H433.688V0H446.997V26.9736ZM548.319 11.8359H529.214V64.958H515.841V11.8359H496.735V0H548.319V11.8359ZM582.825 0C586.739 1.85201e-05 590.287 0.427941 593.467 1.28418C596.647 2.0793 599.338 3.39462 601.54 5.22949C603.803 7.00321 605.516 9.35819 606.678 12.2939C607.901 15.1687 608.481 18.7171 608.42 22.9375C608.359 26.6071 607.717 29.8793 606.494 32.7539C605.271 35.5674 603.558 37.9529 601.356 39.9102C599.216 41.8062 596.617 43.2747 593.559 44.3145C590.562 45.2931 587.289 45.7822 583.742 45.7822H571.174V64.958H557.872V0H582.825ZM278.936 19.1104C285.266 19.1105 290.398 24.2426 290.398 30.5732C290.398 36.9041 285.266 42.036 278.936 42.0361C273.944 42.0359 269.699 38.8447 268.126 34.3916H224.787C223.214 38.8449 218.969 42.0361 213.978 42.0361C207.647 42.0357 202.515 36.9039 202.515 30.5732C202.515 24.2428 207.647 19.1108 213.978 19.1104C218.967 19.1104 223.21 22.2997 224.785 26.75H268.128C269.702 22.2996 273.946 19.1106 278.936 19.1104ZM571.174 34.0391H583.009C584.66 34.039 586.22 33.8246 587.688 33.3965C589.155 32.9683 590.439 32.2953 591.54 31.3779C592.641 30.4605 593.527 29.3289 594.2 27.9834C594.873 26.6378 595.241 25.0469 595.302 23.2119C595.424 19.053 594.323 16.1168 591.999 14.4043C589.675 12.6918 586.647 11.836 582.917 11.8359H571.174V34.0391ZM150.867 34.0381H162.708C164.36 34.0381 165.92 33.8245 167.389 33.3965C168.857 32.9683 170.143 32.2954 171.244 31.3779C172.346 30.4605 173.233 29.329 173.906 27.9834C174.579 26.6378 174.947 25.0469 175.008 23.2119C175.13 19.053 174.028 16.1169 171.703 14.4043C169.378 12.6918 166.349 11.836 162.616 11.8359H150.867V34.0381Z" fill="#453C69"/>
        </svg>
        <span class="header-divider">|</span>
        <span class="app-name">Агент КП</span>
    </div>
    <a href="http://{SERVER_ADDRESS}:8085" class="back-button">
        ← На главную
    </a>
</div>
"""
st.markdown(header_html, unsafe_allow_html=True)

# --- Main Title ---
st.title("Генератор коммерческих предложений")

if IS_DEV:
    st.sidebar.warning(f"🔧 DEV MODE ACTIVE\nServer: {SERVER_ADDRESS}")

# Функция для подключения к Temporal
async def get_client():
    return await Client.connect("temporal-server:7233")

# 1. Загрузка
@st.dialog("Добавить роль в расчет")
def add_role_dialog():
    role_name = st.text_input("Название должность (например, ML-инженер)")
    hourly_rate = st.number_input("Стоимость часа (р.)", min_value=0, value=1000, step=500)
    
    #Расчет "итого" 
    st.write(f"Предварительная стоимость за 8-часовой день: {hourly_rate * 8} р.")
    
    if st.button("Добавить в таблицу"):
        if not role_name:
            st.error("Введите название роли")
        elif role_name in st.session_state['roles_config']:
            st.error(f"Роль '{role_name}' уже существует")
        else:
            st.session_state['roles_config'][role_name] = hourly_rate
            st.rerun()

@st.dialog("Добавить этап проекта")
def add_stage_dialog():
    stage_name = st.text_input("Название этапа (строка таблицы)")
    
    if st.button("Добавить в таблицу"):
        if not stage_name:
            st.error("Введите название этапа")
        elif stage_name in st.session_state['stages_list']:
            st.error(f"Этап '{stage_name}' уже существует")
        else:
            st.session_state['stages_list'].append(stage_name)
            st.rerun()

# 1. Загрузка (Показываем только если нет активного процесса)
if 'workflow_id' not in st.session_state:
    st.markdown("""
    <div class="card">
        <div class="card-header">
            <div class="card-icon">📄</div>
            <h3 class="card-title">Загрузка технического задания</h3>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Загрузите документ ТЗ для анализа", type=["pdf", "docx", "txt"])
    
    if uploaded_file and st.button("Запустить анализ"):
        client = asyncio.run(get_client())
        
        # Запускаем Workflow или подключаемся к существующему
        try:
            handle = asyncio.run(client.start_workflow(
                ProposalWorkflow.run,
                args=[uploaded_file.getvalue(), uploaded_file.name],
                id=f"cp-{uploaded_file.name}-{uploaded_file.size}", # Уникальный ID
                task_queue="proposal-queue",
            ))
            st.success("Процесс успешно запущен! Ожидание результатов...")
        except Exception as e:
            # Проверяем, что ошибка "Workflow execution already started"
            if "Workflow execution already started" in str(e):
                 st.warning("Этот файл уже анализируется. Подключаюсь к процессу...")
                 handle = client.get_workflow_handle(f"cp-{uploaded_file.name}-{uploaded_file.size}")
            else:
                st.error(f"Ошибка запуска: {e}")
                st.stop()
        
        st.session_state['workflow_id'] = handle.id
        st.rerun()

    if 'roles_config' not in st.session_state:
        #Настройки ролей
        st.session_state['roles_config'] = {
            "Менеджер": 2500
        }

    if 'stages_list' not in st.session_state:
        #Список этапов
        st.session_state['stages_list'] = ["Сбор датасета", "Проектирование"]

else:
    # Если есть активный workflow
    client = asyncio.run(get_client())
    handle = client.get_workflow_handle(st.session_state['workflow_id'])
    
    # Кнопка сброса (в сайдбаре или сверху)
    if st.sidebar.button("Сброс / Начать заново"):
        del st.session_state['workflow_id']
        st.rerun()
    
    # Запрашиваем текущее состояние (Query)
    try:
        state = asyncio.run(handle.query(ProposalWorkflow.get_data))
    except Exception as e:
        st.error(f"Не удалось получить статус: {e}")
        st.stop()

    status = state['status']
    data = state['extracted_data']

    # Если еще обрабатывается - показываем loading overlay
    if status == "PROCESSING" or status == "GENERATING":
        loading_text = "Формирование предложения..." if status == "GENERATING" else "Анализ документа..."
        loading_subtext = "ИИ обрабатывает ваше ТЗ" if status == "PROCESSING" else "ИИ генерирует коммерческое предложение"
        st.markdown(f"""
        <div class="loading-overlay">
            <div class="loading-spinner"></div>
            <div class="loading-text">{loading_text}</div>
            <div class="loading-subtext">{loading_subtext}</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Обновить"):
            st.rerun()

    # 2. Проверка (Human-in-Loop)
    elif status == "WAITING_FOR_HUMAN" and data:
        st.markdown("""
        <div class="card">
            <div class="card-header">
                <div class="card-icon">✅</div>
                <h3 class="card-title">Анализ завершён — проверьте и утвердите</h3>
            </div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("Редактировать данные проекта", expanded=True):
            client_name = st.text_input("Клиент", data.get('client_name'))
            project_essence = st.text_area("Суть проекта", data.get('project_essence'))
            features = st.text_area("Функционал (через запятую)", ",".join(data.get('key_features', [])))
            # Стек и технологии - извлекается из ТЗ, если есть
            tech_stack_default = data.get('tech_stack', '')
            if isinstance(tech_stack_default, list):
                tech_stack_default = ", ".join(tech_stack_default)
            tech_stack = st.text_area("Стек и технологии", tech_stack_default, help="Технологии и инструменты для реализации проекта")

        # Блок Калькулятора
        st.subheader("Матрица трудозатрат")
        st.markdown('<p class="cost-matrix-hint">Укажите количество часов для каждой роли на каждом этапе проекта:</p>', unsafe_allow_html=True)
        
        roles = list(st.session_state['roles_config'].keys())
        stages = st.session_state['stages_list']

        col_btns1, col_btns2 = st.columns(2)
        with col_btns1:
            if st.button("➕ Добавить роль"): add_role_dialog()
        with col_btns2:
            if st.button("➕ Добавить этап"): add_stage_dialog()
            
        # Удаление этапов
        if len(stages) > 0:
            with st.expander("Управление этапами (удаление)"):
                stages_to_delete = st.multiselect("Выберите этапы для удаления", stages)
                if st.button("Удалить выбранные этапы"):
                    for s in stages_to_delete:
                        if s in st.session_state['stages_list']:
                            st.session_state['stages_list'].remove(s)
                    st.rerun()
        
        # Создаем таблицу для ввода часов
        df_hours = pd.DataFrame(0, index=stages, columns=roles)
        edited_hours_df = st.data_editor(
            df_hours, 
            use_container_width=True,
            column_config={role: st.column_config.NumberColumn(role, min_value=0, step=1, help=f"Часы для роли {role}") for role in roles}
        )

        # Расчет итогов
        summary_data = []
        total_project_cost = 0

        for role in roles:
            total_hours = edited_hours_df[role].sum()
            rate = st.session_state['roles_config'][role]
            cost = total_hours * rate
            total_project_cost += cost
            summary_data.append({
                "Роль": role,
                "Всего часов": total_hours,
                "Ставка": rate,
                "Стоимость": cost
            })
        
        # Вывод таблицы итогов (ВНЕ цикла)
        # st.table(pd.DataFrame(summary_data))
        
        st.write("### Итоговая таблица (редактирование ставок и ролей)")
        summary_df = pd.DataFrame(summary_data)
        
        column_config = {
            "Роль": st.column_config.TextColumn("Роль", disabled=True),
            "Всего часов": st.column_config.NumberColumn("Всего часов", disabled=True),
            "Ставка": st.column_config.NumberColumn("Ставка (р./час)", min_value=0, step=100, required=True),
            "Стоимость": st.column_config.NumberColumn("Стоимость", disabled=True, format="%d р.")
        }
        
        edited_summary_df = st.data_editor(
            summary_df,
            column_config=column_config,
            use_container_width=True,
            num_rows="dynamic", # Разрешаем удаление строк
            key="summary_editor"
        )
        
        # Синхронизация изменений (Ставки и Удаление ролей)
        current_roles_in_editor = set()
        new_roles_config = {}
        has_changes = False

        for index, row in edited_summary_df.iterrows():
            r_name = row["Роль"]
            if r_name: # Пропускаем пустые строки если они вдруг появятся
                current_roles_in_editor.add(r_name)
                # Проверяем изменение ставки
                new_rate = int(row["Ставка"])
                new_roles_config[r_name] = new_rate
                
                if r_name in st.session_state['roles_config']:
                    if st.session_state['roles_config'][r_name] != new_rate:
                        has_changes = True
        
        # Проверяем удаление ролей
        original_roles = set(st.session_state['roles_config'].keys())
        if current_roles_in_editor != original_roles:
            has_changes = True
            
        if has_changes:
            st.session_state['roles_config'] = new_roles_config
            st.rerun()

        st.metric("Общая стоимость проекта", f"{total_project_cost:,.0f}".replace(",", " ") + " р.")

        if st.button("Утвердить и сгенерировать КП"):
            # Обработка tech_stack - может быть строкой или списком
            tech_stack_list = [t.strip() for t in tech_stack.split(",") if t.strip()] if tech_stack else []
            updated_data = {
                "client_name": client_name,
                "project_essence": project_essence,
                "key_features": features.split(","),
                "business_goals": data.get('business_goals'),
                "tech_stack": tech_stack_list
            }
            # Отправляем сигнал: 1. Данные ТЗ, 2. Матрица часов (dict), 3. Ставки
            asyncio.run(handle.signal(
                ProposalWorkflow.user_approve_signal, 
                {
                    "updated_data": updated_data, 
                    "budget": edited_hours_df.to_dict('index'), # Матрица {Stage: {Role: hours}}
                    "rates": st.session_state['roles_config'] # Ставки
                }
            ))
            st.rerun()

    elif status == "COMPLETED":
        st.markdown("""
        <div class="card">
            <div class="card-header">
                <div class="card-icon">🎉</div>
                <h3 class="card-title">Готовое коммерческое предложение</h3>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if state.get('final_proposal'):
            st.markdown(state['final_proposal'])
        else:
            st.warning("Результат пуст. Проверьте логи worker'а.")
            
        if st.button("Начать заново"):
            del st.session_state['workflow_id']
            st.rerun()