import streamlit as st
import asyncio
from temporalio.client import Client
from workflows import ProposalWorkflow

# Настройка страницы
st.set_page_config(page_title="Коммерческое предложение (Temporal)", layout="wide")
st.title("Коммерческое предложение AI")

# Функция для подключения к Temporal
async def get_client():
    return await Client.connect("localhost:7233")

# 1. Загрузка
st.header("1. Загрузка ТЗ")
uploaded_file = st.file_uploader("Загрузите ТЗ", type=["pdf", "docx", "txt"])

if uploaded_file and st.button("Запустить анализ"):
    client = asyncio.run(get_client())
    
    # Запускаем Workflow и получаем его ID
    handle = asyncio.run(client.start_workflow(
        ProposalWorkflow.run,
        args=[uploaded_file.getvalue(), uploaded_file.name],
        id=f"cp-{uploaded_file.name}-{uploaded_file.size}", # Уникальный ID
        task_queue="proposal-queue",
    ))
    
    st.session_state['workflow_id'] = handle.id
    st.success("Процесс запущен на сервере! Ожидание результатов...")

# Логика опроса состояния Workflow
if 'workflow_id' in st.session_state:
    client = asyncio.run(get_client())
    handle = client.get_workflow_handle(st.session_state['workflow_id'])
    
    # Запрашиваем текущее состояние (Query)
    try:
        state = asyncio.run(handle.query(ProposalWorkflow.get_data))
    except Exception as e:
        st.error(f"Не удалось получить статус: {e}")
        st.stop()

    status = state['status']
    data = state['extracted_data']

    # Если еще обрабатывается
    if status == "PROCESSING":
        st.spinner("ИИ анализирует документ...")
        if st.button("Обновить статус"):
            st.rerun()

    # 2. Проверка (Human-in-Loop)
    elif status == "WAITING_FOR_HUMAN" and data:
        st.divider()
        st.header("2. Проверка и утверждение")
        st.info("ИИ закончил анализ. Workflow ждет вашего решения.")

        with st.form("approval_form"):
            col1, col2 = st.columns(2)
            with col1:
                client_name = st.text_input("Клиент", data.get('client_name'))
                deadline = st.text_input("Срок", data.get('deadline'))
                price = st.number_input("Бюджет (Заглушка)", value=1000000, step=100000)
            with col2:
                # Обработка списка фич для textarea
                features_list = data.get('key_features', [])
                if isinstance(features_list, list):
                    features_str = "\n".join(features_list)
                else:
                    features_str = str(features_list)
                    
                features_edited = st.text_area("Ключевые особенности", features_str)

            submitted = st.form_submit_button("Утвердить и сгенерировать КП")
            
            if submitted:
                # Формируем обновленные данные
                updated_data = data.copy()
                updated_data['client_name'] = client_name
                updated_data['deadline'] = deadline
                updated_data['key_features'] = features_edited.split("\n")
                # tech_stack берем старый или добавляем поле ввода, если нужно
                
                # ОТПРАВЛЯЕМ СИГНАЛ (Разблокируем Workflow)
                asyncio.run(handle.signal(ProposalWorkflow.user_approve_signal, updated_data, price))
                st.success("Сигнал отправлен! Генерация КП...")
                st.rerun()

    # 3. Результат
    elif status == "COMPLETED":
        st.divider()
        st.header("3. Готовое КП")
        st.markdown(state['final_proposal'])
        
        if st.button("Начать заново"):
            del st.session_state['workflow_id']
            st.rerun()