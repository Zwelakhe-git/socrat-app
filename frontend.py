import streamlit as st
import requests

API_URL = "http://localhost:8000"

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
    """Helper for authenticated API calls."""
    headers = auth_headers()
    url = f"{API_URL}{path}"
    if method == "get":
        return requests.get(url, headers=headers, **kwargs)
    return requests.post(url, headers=headers, **kwargs)


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

with col2:
    st.markdown("### 🎧 Подкаст")

    if st.session_state.current_session_id:
        if st.button("🎙️ Сгенерировать подкаст", use_container_width=True, type="primary"):
            with st.spinner("Генерирую... (30–60 сек)"):
                res = api(
                    "post",
                    f"/api/sessions/{st.session_state.current_session_id}/podcast"
                )
                if res.status_code == 200:
                    data = res.json()
                    st.session_state.podcast_url = data["podcast_url"]
                    st.session_state.script = data.get("script", "")
                    load_sessions()
                    st.rerun()
                else:
                    st.error(f"Ошибка: {res.text}")

        if st.session_state.podcast_url:
            st.audio(f"{API_URL}{st.session_state.podcast_url}", format="audio/mp3")
            if st.session_state.script:
                with st.expander("📜 Показать сценарий"):
                    st.text(st.session_state.script)
        else:
            st.info("Нажми кнопку, чтобы создать подкаст из этого диалога")
    else:
        st.info("Создай чат, чтобы начать")