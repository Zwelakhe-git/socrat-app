import streamlit as st
import requests

API_URL = "http://localhost:8020"

st.set_page_config(
    page_title="Socrat",
    page_icon="🎙️",
    layout="wide"
)

# ---------- State ----------
defaults = {
    "token": None,
    "username": None,
    "current_session_id": None,
    "messages": [],
    "podcast_url": None,
    "script": None,
    "sessions": [],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def auth_headers():
    return {"Authorization": f"Bearer {st.session_state.token}"}


def api(method, path, **kwargs):
    """Helper for authenticated API calls. Supports get/post/put/delete."""
    headers = auth_headers()
    url = f"{API_URL}{path}"
    method = method.lower()
    if method == "get":
        return requests.get(url, headers=headers, **kwargs)
    if method == "post":
        return requests.post(url, headers=headers, **kwargs)
    if method == "put":
        return requests.put(url, headers=headers, **kwargs)
    if method == "delete":
        return requests.delete(url, headers=headers, **kwargs)
    raise ValueError(f"Unsupported method: {method}")


def load_sessions():
    res = api("get", "/api/sessions")
    if res.status_code == 200:
        st.session_state.sessions = res.json()


def load_session(session_id):
    res = api("get", f"/api/sessions/{session_id}")
    if res.status_code == 200:
        data = res.json()
        st.session_state.current_session_id = session_id
        st.session_state.messages = data["messages"]
        st.session_state.podcast_url = data["podcast_url"]
        st.session_state.script = None


# ============================================================
# LOGIN / REGISTER SCREEN
# ============================================================
if not st.session_state.token:
    st.markdown("<h1 style='text-align: center;'>🎙️ Socrat</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align: center; color: #7f8c8d;'>ИИ-наставник, который превращает вопросы в подкасты</p>",
        unsafe_allow_html=True
    )
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab1, tab2 = st.tabs(["Вход", "Регистрация"])

        with tab1:
            with st.form("login_form"):
                u = st.text_input("Логин", key="login_u")
                p = st.text_input("Пароль", type="password", key="login_p")
                if st.form_submit_button("Войти", use_container_width=True):
                    res = requests.post(
                        f"{API_URL}/api/auth/login",
                        data={"username": u, "password": p}
                    )
                    if res.status_code == 200:
                        data = res.json()
                        st.session_state.token = data["access_token"]
                        st.session_state.username = data["username"]
                        st.rerun()
                    else:
                        st.error("Неверный логин или пароль")

        with tab2:
            with st.form("register_form"):
                u = st.text_input("Логин", key="reg_u")
                p = st.text_input("Пароль (мин. 6 символов)", type="password", key="reg_p")
                if st.form_submit_button("Создать аккаунт", use_container_width=True):
                    res = requests.post(
                        f"{API_URL}/api/auth/register",
                        json={"username": u, "password": p}
                    )
                    if res.status_code == 200:
                        data = res.json()
                        st.session_state.token = data["access_token"]
                        st.session_state.username = data["username"]
                        st.rerun()
                    else:
                        st.error(res.json().get("detail", "Ошибка регистрации"))

    st.stop()  # Don't render anything else until logged in


# ============================================================
# MAIN APP (logged in)
# ============================================================

# Load sessions on first render
if not st.session_state.sessions and st.session_state.token:
    load_sessions()

# Auto-open first session if nothing is selected
if not st.session_state.current_session_id and st.session_state.sessions:
    load_session(st.session_state.sessions[0]["id"])


# ---------- SIDEBAR ----------
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.username}")

    if st.button("➕ Новый чат", use_container_width=True, type="primary"):
        res = api("post", "/api/sessions")
        if res.status_code == 200:
            new_id = res.json()["session_id"]
            load_sessions()
            load_session(new_id)
            st.rerun()

    st.divider()
    st.markdown("### 💬 Мои чаты")

    if not st.session_state.sessions:
        st.caption("Пока нет чатов")
    else:
        for s in st.session_state.sessions:
            is_active = (s["id"] == st.session_state.current_session_id)
            label = f"{'🟢' if s['podcast_status'] == 'ready' else '💬'} {s['title'][:30]}"
            if st.button(
                label,
                key=f"sess_{s['id']}",
                use_container_width=True,
                type="primary" if is_active else "secondary"
            ):
                load_session(s["id"])
                st.rerun()

    st.divider()
    if st.button("🚪 Выйти", use_container_width=True):
        for k in defaults:
            st.session_state[k] = defaults[k]
        st.rerun()


# ---------- MAIN LAYOUT ----------
col1, col2 = st.columns([3, 2])

with col1:
    st.markdown("### 💬 Диалог")

    chat_container = st.container(height=500, border=True)
    with chat_container:
        if not st.session_state.messages:
            st.caption("Задай вопрос, чтобы начать...")
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    if prompt := st.chat_input("Задай вопрос Socrat'у..."):
        if not st.session_state.current_session_id:
            st.warning("Сначала создай чат")
        else:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)

            with st.spinner("Socrat думает..."):
                res = api(
                    "post",
                    f"/api/sessions/{st.session_state.current_session_id}/chat",
                    json={"user_message": prompt}
                )
                if res.status_code == 200:
                    ai_response = res.json()["ai_response"]
                    st.session_state.messages.append(
                        {"role": "assistant", "content": ai_response}
                    )
                    load_sessions()  # refresh titles
                    st.rerun()
                else:
                    st.error(f"Ошибка: {res.text}")

import time

# Polling config
POLL_INTERVAL = 3        # seconds between checks
MAX_WAIT = 120           # max seconds to wait before giving up

with col2:
    st.markdown("### 🎧 Подкаст")

    if not st.session_state.current_session_id:
        st.info("Создай чат, чтобы начать")
        st.stop()

    # Fetch fresh status from API directly (not stale local state)
    status_res = api("get", f"/api/sessions/{st.session_state.current_session_id}/podcast/status")
    if status_res.status_code != 200:
        st.error("Не удалось получить статус подкаста")
        st.stop()

    status_data = status_res.json()
    status = status_data["status"]
    podcast_url = status_data["podcast_url"]

    # ---------- READY ----------
    if status == "ready" and podcast_url:
        st.success("✅ Подкаст готов")
        st.audio(f"{podcast_url}", format="audio/mp3")

        if st.session_state.script:
            with st.expander("📜 Показать сценарий"):
                st.text(st.session_state.script)

        if st.button("🗑️ Удалить и создать заново", use_container_width=True):
            res = api("delete", f"/api/sessions/{st.session_state.current_session_id}/podcast")
            if res.status_code == 200:
                st.session_state.podcast_url = None
                st.session_state.script = None
                load_sessions()
                st.rerun()
            else:
                st.error(f"Ошибка удаления: {res.text}")

    # ---------- FAILED ----------
    elif status == "failed":
        st.error("❌ Генерация не удалась")
        if st.button("🔄 Попробовать снова", use_container_width=True):
            api("post", f"/api/sessions/{st.session_state.current_session_id}/podcast")
            st.rerun()

    # ---------- GENERATING ----------
    elif status == "generating":
        # Show progress and poll with a max wait limit
        progress_placeholder = st.empty()
        cancel_placeholder = st.empty()

        start_time = time.time()
        elapsed = 0

        while elapsed < MAX_WAIT:
            remaining = MAX_WAIT - int(elapsed)
            progress_placeholder.info(
                f"⏳ Генерирую подкаст... (осталось ~{remaining} сек)\n\n"
                f"Можно свернуть вкладку — генерация продолжится на сервере."
            )

            time.sleep(POLL_INTERVAL)
            elapsed = time.time() - start_time

            # Check status
            res = api("get", f"/api/sessions/{st.session_state.current_session_id}/podcast/status")
            if res.status_code == 200:
                data = res.json()
                if data["status"] != "generating":
                    # Status changed! Refresh and let the loop exit.
                    load_sessions()
                    if data["status"] == "ready":
                        # Load the script too
                        detail = api("get", f"/api/sessions/{st.session_state.current_session_id}")
                        if detail.status_code == 200:
                            st.session_state.script = detail.json().get("podcast_script")
                    st.rerun()

        # Timeout reached
        progress_placeholder.warning(
            f"⏱️ Превышено время ожидания ({MAX_WAIT} сек).\n\n"
            f"Генерация продолжается на сервере. "
            f"Проверь результат позже — вернись в этот чат или обнови страницу."
        )
        if st.button("🔄 Проверить статус сейчас", use_container_width=True):
            load_sessions()
            st.rerun()

    # ---------- NONE ----------
    else:
        st.info("Нажми кнопку, чтобы создать подкаст из этого диалога")
        if st.button("🎙️ Сгенерировать подкаст", use_container_width=True, type="primary"):
            res = api("post", f"/api/sessions/{st.session_state.current_session_id}/podcast")
            if res.status_code == 200:
                data = res.json()
                # If already ready, just jump straight to displaying it
                if data.get("status") == "ready":
                    load_sessions()
                st.rerun()
            else:
                st.error(f"Ошибка запуска: {res.text}")
