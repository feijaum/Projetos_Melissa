import streamlit as st
from backend import DataManager
import pandas as pd

# Configuração para parecer um app Desktop
st.set_page_config(page_title="Painel do Projetista", layout="wide", page_icon="🏗️")

st.sidebar.title("🏗️ Projetos Melissa")
st.sidebar.markdown("Conectando ao banco de dados...")

# Inicializa DB
db = DataManager()

st.sidebar.success("Conectado!")
st.sidebar.markdown("---")

# Menu Lateral
menu = st.sidebar.radio("Navegação", ["Todos os Clientes", "Orçamentos Recentes"])

def open_whatsapp(phone):
    # Limpa formatação
    clean_phone = ''.join(filter(str.isdigit, str(phone)))
    return f"https://wa.me/{clean_phone}"

if menu == "Todos os Clientes":
    st.title("👥 Base de Clientes")
    users = db.get_users()
    
    if not users.empty:
        # Tabela interativa
        st.dataframe(users[['nome', 'sobrenome', 'email', 'telefone']], use_container_width=True)
        
        st.markdown("### Ação Rápida")
        # Cria lista de opções
        options = (users['nome'] + " " + users['sobrenome']).tolist()
        selected_client_name = st.selectbox("Selecione um cliente para contato:", ["Selecione..."] + options)
        
        if selected_client_name != "Selecione...":
            # Filtra usuário
            mask = (users['nome'] + " " + users['sobrenome']) == selected_client_name
            client_data = users[mask].iloc[0]
            
            st.info(f"Dados de {client_data['nome']}:")
            st.write(f"Email: {client_data['email']}")
            
            url = open_whatsapp(client_data['telefone'])
            st.markdown(f"""
                <a href="{url}" target="_blank">
                    <button style="background-color:#25D366; color:white; border:none; padding:10px 20px; border-radius:5px; font-weight:bold; cursor:pointer;">
                        💬 Conversar no WhatsApp
                    </button>
                </a>
            """, unsafe_allow_html=True)
    else:
        st.warning("Nenhum cliente cadastrado ainda.")

elif menu == "Orçamentos Recentes":
    st.title("🏠 Gerenciamento de Orçamentos")
    
    budgets = db.get_budgets() # Pega todos
    
    if not budgets.empty:
        # Seleção lateral de orçamento
        st.sidebar.markdown("### Selecionar Orçamento")
        
        # Cria label bonita para o selectbox
        # Trata caso data_criacao seja vazia
        budgets['display_label'] = budgets.apply(lambda x: f"{x['user_nome']} ({str(x['data_criacao'])[:10]})", axis=1)
        
        selected_budget_idx = st.sidebar.selectbox("Escolha:", budgets.index, format_func=lambda x: budgets.loc[x, 'display_label'])
        
        item = budgets.loc[selected_budget_idx]
        
        # Área Principal - Detalhes do Orçamento
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader(f"Projeto de {item['user_nome']}")
            st.markdown(f"**Localização:** [Abrir no Maps]({item['localizacao']})")
            st.text_area("Descrição do Cliente", item['descricao'], height=150, disabled=True)
            st.info(f"Medidas informadas: {item['medidas']}")
            
            # Grid de Imagens
            st.markdown("#### 📷 Fotos do Terreno")
            if item['imagens']:
                imgs = item['imagens'].split(" | ")
                cols = st.columns(2)
                for i, img_path in enumerate(imgs):
                    if img_path:
                        with cols[i % 2]:
                            try:
                                st.image(img_path, caption=f"Foto {i+1}")
                            except:
                                st.write(f"Erro ao carregar imagem. Link: {img_path}")
            else:
                st.write("Cliente não enviou fotos.")

        with col2:
            st.markdown("### Contato")
            # Busca telefone do usuario cruzando email
            users = db.get_users()
            user_match = users[users['email'] == item['user_email']]
            
            if not user_match.empty:
                user_phone = user_match.iloc[0]['telefone']
                wa_link = open_whatsapp(user_phone)
                
                st.markdown(f"""
                    <a href="{wa_link}" target="_blank">
                        <button style="background-color:#25D366; color:white; width:100%; border:none; padding:15px; border-radius:5px; font-weight:bold; cursor:pointer; font-size:16px;">
                            📲 Chamar no WhatsApp
                        </button>
                    </a>
                """, unsafe_allow_html=True)
            else:
                st.error("Telefone do cliente não encontrado.")
            
            st.divider()
            st.markdown("### Status do Projeto")
            
            # Lista de status possíveis
            status_options = ["Pendente", "Em Análise", "Orçamento Enviado", "Fechado"]
            
            # Tenta achar o index atual, se não default para 0
            try:
                current_idx = status_options.index(item['status'])
            except:
                current_idx = 0
                
            new_status = st.selectbox("Situação", status_options, index=current_idx)
            
            if st.button("Atualizar Status"):
                db.update_budget(item['id'], {"status": new_status})
                st.success("Status atualizado!")
                st.rerun()

    else:
        st.info("Nenhum orçamento recebido.")