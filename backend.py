import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import json
import datetime
import streamlit as st

# Importações do Google
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- CONFIGURAÇÃO ---
# Mude para FALSE para usar o Google Sheets/Drive real.
MOCK_MODE = False 

# Configurações do Google
GOOGLE_CREDENTIALS_FILE = 'credentials.json' # O arquivo que você baixou
SHEET_NAME = 'Sistema_Orcamentos'
DRIVE_FOLDER_NAME = 'Projetos_Melissa_Arquivos' # Nome da pasta que será criada automaticamente

# Configurações de Email (Para recuperação de senha - Gmail requer Senha de App)
EMAIL_SENDER = "seu.email.real@gmail.com" # <--- PREENCHA AQUI SEU EMAIL
EMAIL_PASSWORD = "sua_senha_de_app"       # <--- PREENCHA AQUI SUA SENHA DE APP

class DataManager:
    def __init__(self):
        # --- CORREÇÃO DO ERRO ---
        # O 'global' deve ser a PRIMEIRA coisa dentro da função __init__
        global MOCK_MODE 
        
        self.mock_users_file = 'local_users.json'
        self.mock_budgets_file = 'local_budgets.json'
        self.drive_folder_id = None
        
        # Tenta conectar ao Google
        if not MOCK_MODE:
            try:
                # Escopos necessários: Planilhas e Drive
                scope = [
                    'https://www.googleapis.com/auth/spreadsheets', 
                    'https://www.googleapis.com/auth/drive'
                ]
                
                # LÓGICA HÍBRIDA: Tenta arquivo local OU Secrets do Streamlit Cloud
                creds = None
                if os.path.exists(GOOGLE_CREDENTIALS_FILE):
                    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scope)
                elif "gcp_service_account" in st.secrets:
                    # Se não tiver arquivo, tenta pegar dos Segredos do Streamlit (Configuração de Nuvem)
                    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
                else:
                    raise FileNotFoundError(f"Arquivo '{GOOGLE_CREDENTIALS_FILE}' não encontrado e secrets não configurados.")

                self.creds = creds
                
                # Cliente do Sheets (gspread)
                self.client = gspread.authorize(self.creds)
                
                # Cliente do Drive (google-api-python-client)
                self.drive_service = build('drive', 'v3', credentials=self.creds)
                
                # Abre a planilha (ou cria se não existir)
                try:
                    self.sheet = self.client.open(SHEET_NAME)
                except gspread.SpreadsheetNotFound:
                    self.sheet = self.client.create(SHEET_NAME)

                # Configura a pasta do Drive
                self._setup_drive_folder()

            except Exception as e:
                # Se der erro, ativa o modo MOCK e avisa na tela
                st.error(f"Erro na conexão Google: {e}. Ativando modo OFFLINE (MOCK).")
                MOCK_MODE = True
                self._init_local_db()
        else:
            self._init_local_db()

    def _init_local_db(self):
        """Inicializa arquivos locais para teste sem Google"""
        if not os.path.exists(self.mock_users_file):
            with open(self.mock_users_file, 'w') as f: json.dump([], f)
        if not os.path.exists(self.mock_budgets_file):
            with open(self.mock_budgets_file, 'w') as f: json.dump([], f)

    def _setup_drive_folder(self):
        """Verifica se a pasta de arquivos existe no Drive, se não, cria."""
        try:
            query = f"mimeType='application/vnd.google-apps.folder' and name='{DRIVE_FOLDER_NAME}' and trashed=false"
            results = self.drive_service.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])

            if not files:
                file_metadata = {
                    'name': DRIVE_FOLDER_NAME,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                file = self.drive_service.files().create(body=file_metadata, fields='id').execute()
                self.drive_folder_id = file.get('id')
            else:
                self.drive_folder_id = files[0]['id']
        except Exception as e:
            st.error(f"Erro ao configurar Drive: {e}")

    def _make_file_public(self, file_id):
        """Torna um arquivo público para leitura"""
        try:
            user_permission = {'type': 'anyone', 'role': 'reader'}
            self.drive_service.permissions().create(
                fileId=file_id,
                body=user_permission,
                fields='id',
            ).execute()
        except Exception as e:
            print(f"Erro ao tornar arquivo público: {e}")

    # --- GERENCIAMENTO DE USUÁRIOS ---

    def get_users(self):
        if MOCK_MODE:
            with open(self.mock_users_file, 'r') as f: return pd.DataFrame(json.load(f))
        else:
            try:
                try:
                    worksheet = self.sheet.worksheet("Usuarios")
                except gspread.WorksheetNotFound:
                    worksheet = self.sheet.add_worksheet(title="Usuarios", rows=100, cols=10)
                    worksheet.append_row(["nome", "sobrenome", "telefone", "email", "senha"])
                    return pd.DataFrame(columns=["nome", "sobrenome", "telefone", "email", "senha"])
                
                records = worksheet.get_all_records()
                return pd.DataFrame(records)
            except Exception as e:
                st.error(f"Erro ao ler usuarios: {e}")
                return pd.DataFrame()

    def register_user(self, user_data):
        df = self.get_users()
        
        # Validação de Duplicidade
        if not df.empty and 'email' in df.columns and user_data['email'] in df['email'].values:
            return False, "Email já cadastrado."

        if MOCK_MODE:
            users = df.to_dict('records')
            users.append(user_data)
            with open(self.mock_users_file, 'w') as f: json.dump(users, f)
        else:
            try:
                worksheet = self.sheet.worksheet("Usuarios")
            except:
                worksheet = self.sheet.add_worksheet(title="Usuarios", rows=100, cols=10)
                worksheet.append_row(["nome", "sobrenome", "telefone", "email", "senha"])
            
            row = [user_data['nome'], user_data['sobrenome'], user_data['telefone'], user_data['email'], user_data['senha']]
            worksheet.append_row(row)
            
        return True, "Cadastro realizado com sucesso!"

    def check_login(self, email, password):
        df = self.get_users()
        if df.empty: return None
        
        if 'senha' in df.columns:
            df['senha'] = df['senha'].astype(str)
            user = df[(df['email'] == email) & (df['senha'] == str(password))]
            if not user.empty:
                return user.iloc[0].to_dict()
        return None

    def recover_password(self, email):
        return False, "Configure o email no backend.py para usar esta função."

    # --- GERENCIAMENTO DE ORÇAMENTOS ---

    def get_budgets(self, user_email=None):
        if MOCK_MODE:
            with open(self.mock_budgets_file, 'r') as f: 
                data = json.load(f)
                df = pd.DataFrame(data)
        else:
            try:
                try:
                    worksheet = self.sheet.worksheet("Orcamentos")
                    records = worksheet.get_all_records()
                    df = pd.DataFrame(records)
                except gspread.WorksheetNotFound:
                    return pd.DataFrame()
            except Exception as e:
                st.error(f"Erro ao ler orçamentos: {e}")
                return pd.DataFrame()

        if df.empty: return df
        if user_email:
            return df[df['user_email'] == user_email]
        return df

    def save_budget(self, budget_data, images_files):
        image_links = []
        
        if images_files:
            for img in images_files:
                if MOCK_MODE:
                    if not os.path.exists("uploads"): os.makedirs("uploads")
                    path = f"uploads/{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{img.name}"
                    with open(path, "wb") as f: f.write(img.getbuffer())
                    image_links.append(path)
                else:
                    try:
                        file_metadata = {
                            'name': f"{budget_data['user_nome']}_{img.name}",
                            'parents': [self.drive_folder_id]
                        }
                        media = MediaIoBaseUpload(img, mimetype=img.type)
                        file = self.drive_service.files().create(
                            body=file_metadata, media_body=media, fields='id'
                        ).execute()
                        
                        file_id = file.get('id')
                        self._make_file_public(file_id)
                        link = f"https://drive.google.com/uc?id={file_id}"
                        image_links.append(link)
                    except Exception as e:
                        st.error(f"Erro no upload da imagem {img.name}: {e}")

        budget_data['imagens'] = " | ".join(image_links)
        budget_data['data_criacao'] = str(datetime.datetime.now())
        budget_data['id'] = str(abs(hash(str(datetime.datetime.now()))))

        if MOCK_MODE:
            current_data = []
            if os.path.exists(self.mock_budgets_file):
                with open(self.mock_budgets_file, 'r') as f: current_data = json.load(f)
            current_data.append(budget_data)
            with open(self.mock_budgets_file, 'w') as f: json.dump(current_data, f)
        else:
            try:
                worksheet = self.sheet.worksheet("Orcamentos")
            except:
                worksheet = self.sheet.add_worksheet(title="Orcamentos", rows=1000, cols=10)
                worksheet.append_row(["id", "user_email", "user_nome", "localizacao", "medidas", "descricao", "status", "imagens", "data_criacao"])
            
            row = [
                budget_data.get('id', ''), budget_data.get('user_email', ''),
                budget_data.get('user_nome', ''), budget_data.get('localizacao', ''),
                budget_data.get('medidas', ''), budget_data.get('descricao', ''),
                budget_data.get('status', 'Pendente'), budget_data.get('imagens', ''),
                budget_data.get('data_criacao', '')
            ]
            worksheet.append_row(row)
        return True

    def update_budget(self, budget_id, new_data):
        if MOCK_MODE:
            with open(self.mock_budgets_file, 'r') as f: data = json.load(f)
            for item in data:
                if str(item['id']) == str(budget_id):
                    item.update(new_data)
            with open(self.mock_budgets_file, 'w') as f: json.dump(data, f)
        else:
            try:
                worksheet = self.sheet.worksheet("Orcamentos")
                cell = worksheet.find(str(budget_id))
                if cell:
                    if 'status' in new_data: worksheet.update_cell(cell.row, 7, new_data['status'])
                    if 'localizacao' in new_data: worksheet.update_cell(cell.row, 4, new_data['localizacao'])
                    if 'medidas' in new_data: worksheet.update_cell(cell.row, 5, new_data['medidas'])
                    if 'descricao' in new_data: worksheet.update_cell(cell.row, 6, new_data['descricao'])
            except Exception as e:
                st.error(f"Erro ao atualizar: {e}")
        return True
