import streamlit as st
import asyncio
from temporalio.client import Client
from workflows import ProposalWorkflow
import pandas as pd

# Настройка страницы
st.set_page_config(page_title="Коммерческое предложение (Temporal)", layout="wide")
st.title("Коммерческое предложение AI")

# Функция для подключения к Temporal
async def get_client():
    return await Client.connect("localhost:7233")

# 1. Загрузка
@st.dialog("Добавить роль в расчет")
def add_role_dialog():
    role_name = st.text_input("Название должность (например, ML-инженер)")
    hourly_rate = st.number_input("Стоимость часа (р.)", min_value=0, value=1000, step=500)
    
    #Расчет "итого" 
    st.write(f"Предварительная стоимость за 8-часовой день: {hourly_rate * 8} р.")
    
    if st.button("Добавить в таблицу"):
        st.session_state['roles_config'][role_name] = hourly_rate
        st.rerun()

@st.dialog("Добавить этап проекта")
def add_stage_dialog():
    stage_name = st.text_input("Название этапа (строка таблицы)")
    
    if st.button("Добавить в таблицу"):
        st.session_state['stages_list'].append(stage_name)
        st.rerun()

# 1. Загрузка (Показываем только если нет активного процесса)
if 'workflow_id' not in st.session_state:
    st.header("1. Загрузка ТЗ")
    uploaded_file = st.file_uploader("Загрузите ТЗ", type=["pdf", "docx", "txt"])
    
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
            st.success("Процесс запущен на сервере! Ожидание результатов...")
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
    if st.sidebar.button("⚠️ Сброс / Начать заново"):
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
    st.info(f"Текущий статус: {status}") # Debug info

    # Если еще обрабатывается
    if status == "PROCESSING" or status == "GENERATING":
        st.spinner("ИИ формирует документ..." if status == "GENERATING" else "ИИ анализирует документ...")
        if st.button("Обновить статус"):
            st.rerun()

    # 2. Проверка (Human-in-Loop)
    elif status == "WAITING_FOR_HUMAN" and data:
        st.header("2. Проверка и утверждение")
        st.info("ИИ закончил анализ. Workflow ждет вашего решения.")

        with st.expander("Редактировать ТЗ и цели"):
            client_name = st.text_input("Клиент", data.get('client_name'))
            project_essence = st.text_area("Суть проекта", data.get('project_essence'))
            features = st.text_area("Функционал (через запятую)", ",".join(data.get('key_features', [])))

        # Блок Калькулятора (твой пункт 7)
        st.subheader("Матрица трудозатрат")
        col_btns1, col_btns2 = st.columns(2)
        with col_btns1:
            if st.button("Добавить роль"): add_role_dialog()
        with col_btns2:
            if st.button("Добавить этап"): add_stage_dialog()

        roles = list(st.session_state['roles_config'].keys())
        stages = st.session_state['stages_list']
        
        # Создаем таблицу для ввода часов
        df_hours = pd.DataFrame(0, index=stages, columns=roles)
        edited_hours_df = st.data_editor(df_hours, use_container_width=True)

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
        st.table(pd.DataFrame(summary_data))
        st.metric("Общая стоимость проекта", f"{total_project_cost:,.0f} р.")

        if st.button("Утвердить и Сгенерировать КП"):
            updated_data = {
                "client_name": client_name,
                "project_essence": project_essence,
                "key_features": features.split(","),
                "business_goals": data.get('business_goals')
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
        st.header("3. Готовое КП")
        if state.get('final_proposal'):
            st.markdown(state['final_proposal'])
        else:
            st.warning("Результат пуст. Проверьте логи worker'а.")
            
        if st.button("Начать заново (Финал)"):
            del st.session_state['workflow_id']
            st.rerun()