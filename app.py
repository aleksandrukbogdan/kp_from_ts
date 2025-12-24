import streamlit as st
from logic import extract_requirements_from_ts, generate_proposal

st.set_page_config(page_title="Коммерческое предложение", layout="wide")

st.title("Коммерческое предложение AI")
st.markdown("Загрузите ТЗ, проверьте саммари от ИИ")

# 1. Загрузка  тз

st.header("1. Загрузка ТЗ")
uploaded_file = st.file_uploader("Загрузите ТЗ (PDF/DOCX/TXT)", type=["pdf", "docx", "txt"])

#парсер текста

tz_text = "Заказчик: УГМК\nТип проекта: Веб-платформа\nСрок проекта: 10.03.2026\nФункционал: Личный кабинет, Интеграция с ЦУР, Чат-бот поддержки\nТехнологии: Python, React"

if st.button("Получить анализ!!!"):
    with st.spinner("Подождите, ИИ обрабатывает ТЗ"):
        extracted_data = extract_requirements_from_ts(tz_text)

        st.session_state['extracted_data'] = extracted_data

        st.success("Анализ завершен")

# 2. Проверка 
if 'extracted_data' in st.session_state:
    st.divider()
    st.header("2. Проверка понимания задачи")
    st.info("Агент выделил следующие параментры, вы можете скорректировать их")
    col1, col2 = st.columns(2)
    with col1:
        client_name = st.text_input("Клиент", st.session_state['extracted_data']['client_name'])
        deadline = st.text_input("Срок", st.session_state['extracted_data']['deadline'])
        price = st.number_input("Оценка бюджета(руб)", value=10000000, step=100000)
    with col2:
        features_str = "\n".join(st.session_state['extracted_data']['key_features'])
        features = st.text_area("Ключевые особенности", features_str)
    
    update_requirements = st.session_state['extracted_data'].copy()
    update_requirements['client_name'] = client_name
    update_requirements['deadline'] = deadline
    update_requirements['features'] = features    

    #3. Результат
    st.divider()
    st.header("3. Генерация коммерческого предложения")

    if st.button("Сгенерировать предложение"):
        with st.spinner("Подождите, ИИ генерирует предложение"):
            final_doc = generate_proposal(update_requirements, price)
            st.session_state['final_doc'] = final_doc

    if 'final_doc' in st.session_state:
        st.markdown("Предварительный просмотр")
        st.markdown(st.session_state['final_doc'])