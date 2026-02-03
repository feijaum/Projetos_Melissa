import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import json
import datetime
import streamlit as st
import re

# Importações do Google
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- CONFIGURAÇÃO ---
MOCK_MODE = False 

# Configurações do Google
GOOGLE_CREDENTIALS_FILE = 'credentials.json'
SHEET_NAME = 'Sistema_Orcamentos'
DRIVE_FOLDER_NAME = 'Projetos_Melissa_Arquivos'

# Configurações de Email
EMAIL_SENDER = "seu.email.real@gmail.com" # <--- MANTENHA SEU EMAIL AQUI
EMAIL_PASSWORD = "sua_senha_de_app"       # <--- MANTENHA SUA SENHA AQUI

class DataManager:
    def __init__(self):
        global MOCK_MODE 
        
        self.mock_users_file = 'local_users.json'
        self.mock_budgets_file = 'local_budgets.json'
        self.drive_folder_id = None
        
        if not MOCK_MODE:
            try:
                scope = [
                    'https://www.googleapis.com/auth/spreadsheets', 
                    'https://www.googleapis.com/auth/drive'
                ]
                
                service_account_info = None
                
                # 1. Tenta carregar do Arquivo JSON (Prioridade Local)
                if os.path.exists(GOOGLE_CREDENTIALS_FILE):
                    try:
                        with open(GOOGLE_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                            service_account_info = json.load(f)
                    except Exception as e:
                        print(f"Erro ao ler JSON local: {e}")

                # 2. Se não achou arquivo, tenta Secrets (Streamlit Cloud)
                if not service_account_info and "gcp_service_account" in st.secrets:
                    # Converte o objeto Secrets para um dicionário Python normal
                    service_account_info = dict(st.secrets["gcp_service_account"])

                if not service_account_info:
                    raise FileNotFoundError("Credenciais não encontradas (Nem arquivo JSON, nem Secrets).")

                # --- CORREÇÃO BLINDADA DA CHAVE PRIVADA ---
                if "private_key" in service_account_info:
                    raw_key = service_account_info["private_key"]
                    service_account_info["private_key"] = self._clean_private_key(raw_key)

                # Cria as credenciais
                self.creds = Credentials.from_service_account_info(service_account_info, scopes=scope)
                
                # Cliente do Sheets
                self.client = gspread.authorize(self.creds)
                
                # Cliente do Drive
                self.drive_service = build('drive', 'v3', credentials=self.creds)
                
                # Testa conexão abrindo a planilha
                try:
                    self.sheet = self.client.open(SHEET_NAME)
                except gspread.SpreadsheetNotFound:
                    self.sheet = self.client.create(SHEET_NAME)

                self._setup_drive_folder()

            except Exception as e:
                st.error(f"⚠️ Erro de Conexão Google: {e}. O sistema está OFFLINE.")
                MOCK_MODE = True
                self._init_local_db()
        else:
            self._init_local_db()

    def _clean_private_key(self, key):
        """Limpa a chave privada para evitar erro de JWT Invalid Signature"""
        if not key: return ""
        
        # Remove aspas extras que podem ter vindo da cópia
        key = key.strip().strip('"').strip("'")
        
        # Correção de escape duplo (comum em TOML/JSON mal formatado)
        key = key.replace("\\\\n", "\n")
        
        # Substitui \\n literais por quebras de linha reais
        key = key.replace("\\n", "\n")
            
        # Garante cabeçalhos em linhas separadas se tudo virou uma linha só
        if "-----BEGIN PRIVATE KEY-----" in key and "\n" not in key:
            key = key.replace("-----BEGIN PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----\n")
            key = key.replace("-----END PRIVATE KEY-----", "\n-----END PRIVATE KEY-----")
            
        return key

    def _init_local_db(self):
        if not os.path.exists(self.mock_users_file):
            with open(self.mock_users_file, 'w') as f: json.dump([], f)
        if not os.path.exists(self.mock_budgets_file):
            with open(self.mock_budgets_file, 'w') as f: json.dump([], f)

    def _setup_drive_folder(self):
        try:
            query = f"mimeType='application/vnd.google-apps.folder' and name='{DRIVE_FOLDER_NAME}' and trashed=false"
            results = self.drive_service.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])

            if not files:
                file_metadata = {'name': DRIVE_FOLDER_NAME, 'mimeType': 'application/vnd.google-apps.folder'}
                file = self.drive_service.files().create(body=file_metadata, fields='id').execute()
                self.drive_folder_id = file.get('id')
            else:
                self.drive_folder_id = files[0]['id']
        except Exception as e:
            # Silencia erro de Drive no modo offline para não assustar o usuário
            if not MOCK_MODE: print(f"Aviso Drive: {e}")

    def _make_file_public(self, file_id):
        try:
            self.drive_service.permissions().create(
                fileId=file_id,
                body={'type': 'anyone', 'role': 'reader'},
                fields='id',
            ).execute()
        except Exception:
            pass

    # --- FUNÇÕES DE NEGÓCIO ---
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
                return pd.DataFrame(worksheet.get_all_records())
            except:
                return pd.DataFrame()

    def register_user(self, user_data):
        df = self.get_users()
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
            
            worksheet.append_row([user_data['nome'], user_data['sobrenome'], user_data['telefone'], user_data['email'], user_data['senha']])
        return True, "Cadastro realizado!"

    def check_login(self, email, password):
        df = self.get_users()
        if df.empty: return None
        if 'senha' in df.columns:
            df['senha'] = df['senha'].astype(str)
            user = df[(df['email'] == email) & (df['senha'] == str(password))]
            if not user.empty: return user.iloc[0].to_dict()
        return None

    def recover_password(self, email):
        df = self.get_users()
        if df.empty or 'email' not in df.columns: return False, "Base vazia."
        user = df[df['email'] == email]
        if user.empty: return False, "Email não encontrado."
        
        if "seu.email.real" in EMAIL_SENDER:
            return False, "O sistema ainda não configurou o email de envio."

        try:
            nome = user.iloc[0]['nome']
            senha = str(user.iloc[0]['senha'])
            
            msg = MIMEMultipart()
            msg['From'] = EMAIL_SENDER
            msg['To'] = email
            msg['Subject'] = "Recuperação de Senha"
            msg.attach(MIMEText(f"Olá {nome},\n\nSua senha é: {senha}", 'plain'))
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
            server.quit()
            return True, "Senha enviada!"
        except Exception as e:
            return False, f"Erro envio: {str(e)}"

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
            except:
                return pd.DataFrame()

        if df.empty: return df
        if user_email: return df[df['user_email'] == user_email]
        return df

    def save_budget(self, budget_data, images_files):
        image_links = []
        if images_files:
            for img in images_files:
                if MOCK_MODE:
                    image_links.append(f"mock_{img.name}")
                else:
                    try:
                        file_metadata = {'name': f"{budget_data['user_nome']}_{img.name}", 'parents': [self.drive_folder_id]}
                        media = MediaIoBaseUpload(img, mimetype=img.type)
                        file = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                        file_id = file.get('id')
                        self._make_file_public(file_id)
                        image_links.append(f"https://drive.google.com/uc?id={file_id}")
                    except:
                        pass

        budget_data['imagens'] = " | ".join(image_links)
        budget_data['data_criacao'] = str(datetime.datetime.now())
        budget_data['id'] = str(abs(hash(str(datetime.datetime.now()))))

        if MOCK_MODE:
            current = []
            if os.path.exists(self.mock_budgets_file):
                with open(self.mock_budgets_file, 'r') as f: current = json.load(f)
            current.append(budget_data)
            with open(self.mock_budgets_file, 'w') as f: json.dump(current, f)
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
                if str(item['id']) == str(budget_id): item.update(new_data)
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
            except:
                pass
        return True
