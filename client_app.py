import streamlit as st
from backend import DataManager
import time
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

# Configuração da Página
st.set_page_config(page_title="Portal do Cliente | Orçamentos", page_icon="🏠")

# Instancia o banco de dados
db = DataManager()

# --- ESTILOS CSS ---
st.markdown("""
<style>
    .stButton>button { width: 100%; border-radius: 5px; }
    .success-msg { color: green; font-weight: bold; }
    .error-msg { color: red; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- GERENCIAMENTO DE ESTADO ---
if 'page' not in st.session_state: st.session_state.page = 'login'
if 'user' not in st.session_state: st.session_state.user = None
if 'map_center' not in st.session_state: st.session_state.map_center = [-14.2350, -51.9253] # Centro do Brasil
if 'map_zoom' not in st.session_state: st.session_state.map_zoom = 4
if 'selected_location_text' not in st.session_state: st.session_state.selected_location_text = ""

def navigate_to(page):
    st.session_state.page = page
    st.rerun()

# --- FUNÇÕES AUXILIARES DE MAPA ---
def get_address_from_coords(lat, lon):
    try:
        geolocator = Nominatim(user_agent="app_orcamentos_melissa")
        location = geolocator.reverse(f"{lat}, {lon}", timeout=10)
        return location.address if location else f"{lat}, {lon}"
    except:
        return f"Coordenadas: {lat}, {lon}"

def get_coords_from_address(address):
    try:
        geolocator = Nominatim(user_agent="app_orcamentos_melissa")
        location = geolocator.geocode(address, timeout=10)
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
        st.subheader("Acessar Sistema")
        email = st.text_input("Email")
        senha = st.text_input("Senha", type="password")
        
        if st.button("Entrar", type="primary"):
            with st.spinner("Verificando..."):
                user = db.check_login(email, senha)
            if user:
                st.session_state.user = user
                navigate_to('home')
            else:
                st.error("Email ou senha incorretos. (Verifique se cadastrou com este email)")
        
        if st.button("Esqueci a senha"):
            st.session_state.page = 'forgot_password'
            st.rerun()

    elif auth_mode == 'register':
        st.subheader("Novo Cadastro")
        nome = st.text_input("Nome")
        sobrenome = st.text_input("Sobrenome")
        
        col_tel, col_dd = st.columns([3, 1])
        telefone = st.text_input("Telefone (Ex: 99999-9999)")
        ddd = st.text_input("DDD (Ex: 11)", max_chars=2)
        
        email = st.text_input("Email")
        conf_email = st.text_input("Confirmar Email")
        senha = st.text_input("Senha (Min 4 caracteres)", type="password")
        conf_senha = st.text_input("Confirmar Senha", type="password")

        if st.button("Cadastrar", type="primary"):
            if email != conf_email:
                st.error("Emails não conferem.")
            elif senha != conf_senha:
                st.error("Senhas não conferem.")
            elif len(senha) < 4:
                st.error("Senha muito curta.")
            elif not nome or not sobrenome or not telefone or not ddd:
                st.error("Preencha todos os campos.")
            else:
                full_phone = f"55{ddd}{telefone.replace('-','').replace(' ','')}"
                user_data = {
                    "nome": nome, "sobrenome": sobrenome, 
                    "telefone": full_phone, "email": email, "senha": senha
                }
                with st.spinner("Salvando cadastro..."):
                    success, msg = db.register_user(user_data)
                if success:
                    st.success(msg)
                    time.sleep(2)
                    st.session_state.auth_mode = 'login'
                    st.rerun()
                else:
                    st.error(msg)

def forgot_password_screen():
    st.subheader("Recuperar Senha")
    email = st.text_input("Digite seu email cadastrado")
    if st.button("Recuperar"):
        with st.spinner("Enviando email..."):
            success, msg = db.recover_password(email)
        if success: st.success(msg)
        else: st.error(msg)
    
    if st.button("Voltar ao Login"): navigate_to('login')

def home_screen():
    st.title(f"Olá, {st.session_state.user['nome']}!")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("➕ Novo Orçamento", type="primary", use_container_width=True):
            # Reseta o mapa ao iniciar novo orcamento
            st.session_state.map_center = [-14.2350, -51.9253]
            st.session_state.map_zoom = 4
            st.session_state.selected_location_text = ""
            navigate_to('new_budget')
    with col2:
        if st.button("📋 Meus Pedidos", use_container_width=True):
            navigate_to('history')
            
    st.divider()
    if st.button("Sair"):
        st.session_state.user = None
        navigate_to('login')

def new_budget_screen():
    st.subheader("Solicitar Novo Orçamento")
    
    # --- LÓGICA DO MAPA ---
    st.markdown("### 1. Localização do Terreno")
    st.info("Pesquise sua cidade/rua ou clique no mapa para marcar o local exato.")
    
    search_query = st.text_input("🔍 Pesquisar endereço (Ex: Rua das Flores, São Paulo)", key="search_box")
    
    # Botão de busca manual para atualizar o centro do mapa
    if st.button("Buscar no Mapa") and search_query:
        coords = get_coords_from_address(search_query)
        if coords:
            st.session_state.map_center = [coords[0], coords[1]]
            st.session_state.map_zoom = 16
        else:
            st.warning("Endereço não encontrado.")

    # Criação do Mapa
    m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom)
    
    # Adiciona marcador se já tiver selecionado algo
    if st.session_state.selected_location_text:
        # Tenta extrair lat/long do link se possível, ou usa o centro atual
        folium.Marker(
            st.session_state.map_center, 
            popup="Local Selecionado", 
            icon=folium.Icon(color="green", icon="check")
        ).add_to(m)

    # Exibe o mapa e captura o clique
    map_data = st_folium(m, height=400, width=700)

    # Lógica ao Clicar no Mapa
    if map_data.get("last_clicked"):
        lat = map_data["last_clicked"]["lat"]
        lng = map_data["last_clicked"]["lng"]
        
        # Atualiza o estado apenas se mudou (para evitar loop)
        if [lat, lng] != st.session_state.map_center:
            st.session_state.map_center = [lat, lng]
            st.session_state.map_zoom = 18 # Aproxima ao clicar
            
            # Gera o link do Google Maps
            gmaps_link = f"https://www.google.com/maps?q={lat},{lng}"
            
            # Tenta pegar o nome da rua
            address_name = get_address_from_coords(lat, lng)
            
            st.session_state.selected_location_text = f"{gmaps_link} | ({address_name})"
            st.rerun()

    # Formulário Principal
    with st.form("budget_form"):
        # Campo de localização preenchido automaticamente
        localizacao = st.text_input("Link da Localização (Preenchido pelo mapa)", 
                                  value=st.session_state.selected_location_text,
                                  placeholder="Clique no mapa acima para preencher automaticamente")
        
        st.markdown("---")
        medidas = st.text_input("2. Medidas do Terreno", placeholder="Ex: 10m frente x 20m fundo")
        
        st.markdown("3. Fotos do Terreno (Opcional - Máx 4)")
        fotos = st.file_uploader("Envie as fotos", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
        if len(fotos) > 4:
            st.warning("Máximo de 4 fotos permitidas. Apenas as 4 primeiras serão enviadas.")
            fotos = fotos[:4]

        descricao = st.text_area("4. O que você deseja fazer?", placeholder="Descreva sua ideia: casa, muro, reforma, quantidade de quartos...")
        
        submitted = st.form_submit_button("Enviar Solicitação")
        
        if submitted:
            if not localizacao or not medidas or not descricao:
                st.error("Preencha todos os campos obrigatórios (Não esqueça de selecionar o local no mapa).")
            else:
                data = {
                    "user_email": st.session_state.user['email'],
                    "user_nome": st.session_state.user['nome'],
                    "localizacao": localizacao,
                    "medidas": medidas,
                    "descricao": descricao,
                    "status": "Pendente"
                }
                with st.spinner("Enviando informações e fazendo upload das fotos (isso pode demorar um pouco)..."):
                    db.save_budget(data, fotos)
                st.success("Orçamento enviado com sucesso!")
                time.sleep(2)
                navigate_to('home')

    if st.button("Cancelar / Voltar"): navigate_to('home')

def history_screen():
    st.subheader("Histórico de Orçamentos")
    
    with st.spinner("Carregando seus pedidos..."):
        budgets = db.get_budgets(st.session_state.user['email'])
    
    if budgets.empty:
        st.info("Você ainda não fez nenhum pedido.")
    else:
        st.dataframe(budgets[['data_criacao', 'status', 'descricao']], use_container_width=True)
        
        opts = budgets['id'].astype(str).tolist()
        selection = st.selectbox("Selecione um pedido para ver detalhes ou editar:", ["Selecione..."] + opts)
        
        if selection != "Selecione...":
            item = budgets[budgets['id'].astype(str) == str(selection)].iloc[0]
            
            st.divider()
            st.write(f"**Status:** {item['status']}")
            
            # Modo de Edição
            if 'edit_mode' not in st.session_state: st.session_state.edit_mode = False
            
            if not st.session_state.edit_mode:
                # Tenta mostrar link clicavel
                st.markdown(f"**Localização:** {item['localizacao']}")
                if "http" in item['localizacao']:
                    link_url = item['localizacao'].split("|")[0].strip()
                    st.markdown(f"[Abrir no Google Maps]({link_url})")

                st.write(f"**Medidas:** {item['medidas']}")
                st.write(f"**Descrição:** {item['descricao']}")
                
                if item['imagens']:
                    imgs = item['imagens'].split(" | ")
                    st.markdown("**Fotos enviadas:**")
                    cols = st.columns(4)
                    for i, img_path in enumerate(imgs):
                        if img_path:
                            with cols[i % 4]:
                                st.image(img_path, use_container_width=True)

                if st.button("✏️ Editar Informações"):
                    st.session_state.edit_mode = True
                    st.rerun()
            
            else:
                st.warning("⚠️ Você tem alterações não salvas.")
                with st.form("edit_form"):
                    new_loc = st.text_input("Localização", value=item['localizacao'])
                    new_med = st.text_input("Medidas", value=item['medidas'])
                    new_desc = st.text_area("Descrição", value=item['descricao'])
                    
                    if st.form_submit_button("💾 Salvar Alterações"):
                        db.update_budget(item['id'], {
                            "localizacao": new_loc,
                            "medidas": new_med,
                            "descricao": new_desc
                        })
                        st.success("Salvo!")
                        st.session_state.edit_mode = False
                        time.sleep(1)
                        st.rerun()
                
                if st.button("Cancelar Edição"):
                    st.session_state.edit_mode = False
                    st.rerun()

    if st.button("Voltar"): navigate_to('home')

# --- ROTEAMENTO PRINCIPAL ---
if st.session_state.page == 'login': login_screen()
elif st.session_state.page == 'forgot_password': forgot_password_screen()
elif st.session_state.page == 'home': home_screen()
elif st.session_state.page == 'new_budget': new_budget_screen()
elif st.session_state.page == 'history': history_screen()
