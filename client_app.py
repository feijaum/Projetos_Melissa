import streamlit as st
from backend import DataManager
import time
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

# Configuração da Página - CRÍTICO: Deve ser o primeiro comando
st.set_page_config(page_title="Portal do Cliente", page_icon="🏠", layout="centered")

# CSS para melhorar visualização no iPhone
st.markdown("""
<style>
    .stButton>button { width: 100%; border-radius: 8px; height: 50px; font-size: 16px; }
    /* Ajuste para inputs no mobile não darem zoom automático */
    input, textarea { font-size: 16px !important; }
    .success-msg { color: green; font-weight: bold; }
    .error-msg { color: red; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Instancia o banco de dados
db = DataManager()

# --- GERENCIAMENTO DE ESTADO ---
if 'page' not in st.session_state: st.session_state.page = 'login'
if 'user' not in st.session_state: st.session_state.user = None
if 'map_center' not in st.session_state: st.session_state.map_center = [-12.2716, -38.9631]
if 'map_zoom' not in st.session_state: st.session_state.map_zoom = 13
if 'selected_location_link' not in st.session_state: st.session_state.selected_location_link = ""
if 'selected_address_text' not in st.session_state: st.session_state.selected_address_text = ""

def navigate_to(page):
    st.session_state.page = page
    st.rerun()

# --- FUNÇÕES AUXILIARES DE MAPA ---
def get_address_from_coords(lat, lon):
    try:
        geolocator = Nominatim(user_agent="app_melissa_safari_fix")
        location = geolocator.reverse(f"{lat}, {lon}", timeout=5)
        return location.address if location else "Endereço não identificado"
    except:
        return "Endereço não identificado"

def get_coords_from_address(address):
    try:
        geolocator = Nominatim(user_agent="app_melissa_safari_fix")
        location = geolocator.geocode(address, timeout=5)
        if location:
            return location.latitude, location.longitude
        return None
    except:
        return None

# --- TELAS ---

def login_screen():
    st.title("🏠 Bem-vindo(a)")
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Já tenho conta"): st.session_state.auth_mode = 'login'
    with col2:
        if st.button("Primeiro Acesso"): st.session_state.auth_mode = 'register'

    auth_mode = st.session_state.get('auth_mode', 'login')

    if auth_mode == 'login':
        st.subheader("Login")
        email = st.text_input("Email")
        senha = st.text_input("Senha", type="password")
        
        if st.button("Entrar", type="primary"):
            with st.spinner("Conectando..."):
                user = db.check_login(email, senha)
            if user:
                st.session_state.user = user
                navigate_to('home')
            else:
                st.error("Dados incorretos.")
        
        if st.button("Esqueci a senha"):
            navigate_to('forgot_password')

    elif auth_mode == 'register':
        st.subheader("Cadastro")
        nome = st.text_input("Nome")
        sobrenome = st.text_input("Sobrenome")
        
        col_tel, col_dd = st.columns([3, 1])
        telefone = st.text_input("Telefone (Ex: 99999-9999)")
        ddd = st.text_input("DDD", max_chars=2)
        
        email = st.text_input("Email")
        conf_email = st.text_input("Confirmar Email")
        senha = st.text_input("Senha", type="password")
        conf_senha = st.text_input("Confirmar Senha", type="password")

        if st.button("Cadastrar", type="primary"):
            if email != conf_email:
                st.error("Emails diferentes.")
            elif senha != conf_senha:
                st.error("Senhas diferentes.")
            elif not nome or not telefone:
                st.error("Preencha tudo.")
            else:
                full_phone = f"55{ddd}{telefone.replace('-','').replace(' ','')}"
                user_data = {"nome": nome, "sobrenome": sobrenome, "telefone": full_phone, "email": email, "senha": senha}
                success, msg = db.register_user(user_data)
                if success:
                    st.success(msg)
                    time.sleep(1)
                    st.session_state.auth_mode = 'login'
                    st.rerun()
                else:
                    st.error(msg)

def forgot_password_screen():
    st.subheader("Recuperar Senha")
    email = st.text_input("Seu email")
    if st.button("Recuperar"):
        success, msg = db.recover_password(email)
        if success: st.success(msg)
        else: st.error(msg)
    if st.button("Voltar"): navigate_to('login')

def home_screen():
    st.title(f"Olá, {st.session_state.user['nome']}")
    
    # Botões grandes para facilitar toque no celular
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("➕ NOVO ORÇAMENTO", type="primary", use_container_width=True):
        st.session_state.map_center = [-12.2716, -38.9631]
        st.session_state.selected_location_link = ""
        st.session_state.selected_address_text = ""
        navigate_to('new_budget')
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("📋 MEUS PEDIDOS", use_container_width=True):
        navigate_to('history')
            
    st.divider()
    if st.button("Sair"):
        st.session_state.user = None
        navigate_to('login')

def new_budget_screen():
    st.subheader("Novo Orçamento")
    
    st.markdown("##### 1. Onde é o terreno?")
    
    col_search, col_btn = st.columns([3, 1])
    with col_search:
        search_query = st.text_input("Busca", placeholder="Ex: Rua A, Feira de Santana", label_visibility="collapsed")
    with col_btn:
        btn_buscar = st.button("🔍 Ir")

    if btn_buscar and search_query:
        coords = get_coords_from_address(search_query)
        if coords:
            st.session_state.map_center = [coords[0], coords[1]]
            st.session_state.map_zoom = 18
        else:
            st.warning("Não encontrado.")

    # Mapa Protegido para Mobile
    try:
        m = folium.Map(
            location=st.session_state.map_center, 
            zoom_start=st.session_state.map_zoom,
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google Maps"
        )
        if st.session_state.selected_location_link:
            folium.Marker(st.session_state.map_center, icon=folium.Icon(color="red")).add_to(m)

        # width=100% é crucial para mobile
        map_data = st_folium(m, height=350, width="100%")

        if map_data and map_data.get("last_clicked"):
            lat = map_data["last_clicked"]["lat"]
            lng = map_data["last_clicked"]["lng"]
            
            if abs(lat - st.session_state.map_center[0]) > 0.0001 or abs(lng - st.session_state.map_center[1]) > 0.0001:
                st.session_state.map_center = [lat, lng]
                st.session_state.selected_location_link = f"https://www.google.com/maps?q={lat},{lng}"
                st.session_state.selected_address_text = get_address_from_coords(lat, lng)
                st.rerun()
    except Exception as e:
        st.error("Erro ao carregar mapa no dispositivo. Digite o endereço abaixo.")

    if st.session_state.selected_address_text:
        st.caption(f"📍 {st.session_state.selected_address_text}")

    with st.form("budget_form"):
        localizacao = st.text_input("Link / Localização", 
                                  value=st.session_state.selected_location_link,
                                  placeholder="Toque no mapa ou cole um link")
        
        medidas = st.text_input("2. Medidas", placeholder="Ex: 10x20")
        
        st.markdown("3. Fotos (Opcional)")
        fotos = st.file_uploader("Fotos", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'], label_visibility="collapsed")
        
        descricao = st.text_area("4. O que vamos construir?", placeholder="Descreva sua ideia...", height=150)
        
        submitted = st.form_submit_button("ENVIAR PEDIDO", type="primary")
        
        if submitted:
            if not localizacao or not medidas or not descricao:
                st.error("Preencha Localização, Medidas e Descrição.")
            else:
                data = {
                    "user_email": st.session_state.user['email'],
                    "user_nome": st.session_state.user['nome'],
                    "localizacao": localizacao,
                    "medidas": medidas,
                    "descricao": descricao,
                    "status": "Pendente"
                }
                with st.spinner("Enviando..."):
                    db.save_budget(data, fotos[:4] if fotos else [])
                st.success("Enviado!")
                time.sleep(2)
                navigate_to('home')

    if st.button("Cancelar"): navigate_to('home')

def history_screen():
    st.subheader("Meus Pedidos")
    budgets = db.get_budgets(st.session_state.user['email'])
    
    if budgets.empty:
        st.info("Nenhum pedido.")
    else:
        for idx, row in budgets.iterrows():
            with st.expander(f"{row['data_criacao'][:10]} - {row['status']}"):
                st.write(f"**Local:** {row['localizacao']}")
                st.write(f"**Medidas:** {row['medidas']}")
                st.write(f"**Desc:** {row['descricao']}")
                if row['imagens']:
                    st.write("**Fotos:**")
                    imgs = row['imagens'].split(" | ")
                    cols = st.columns(3)
                    for i, img in enumerate(imgs):
                        if img: 
                            with cols[i%3]: st.image(img, use_container_width=True)

    if st.button("Voltar"): navigate_to('home')

# ROTEAMENTO
if st.session_state.page == 'login': login_screen()
elif st.session_state.page == 'forgot_password': forgot_password_screen()
elif st.session_state.page == 'home': home_screen()
elif st.session_state.page == 'new_budget': new_budget_screen()
elif st.session_state.page == 'history': history_screen()
