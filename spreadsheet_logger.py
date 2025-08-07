import json
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
import streamlit as st
import os

class SpreadsheetLogger:
    def __init__(self, config):
        self.config = config
        self.sheets_service = None
        self.spreadsheet_id = config.get('default_spreadsheet_id')
        self.init_sheets_service()
    
    def get_credentials(self):
        """認証情報を取得（Secrets対応）"""
        try:
            # Secretsから読み込み
            if 'gcp_service_account' in st.secrets:
                credentials_dict = dict(st.secrets["gcp_service_account"])
                credentials = service_account.Credentials.from_service_account_info(
                    credentials_dict,
                    scopes=['https://www.googleapis.com/auth/spreadsheets']
                )
                return credentials
            else:
                # ローカルファイルから読み込み
                credentials = service_account.Credentials.from_service_account_file(
                    self.config['credentials_file'],
                    scopes=['https://www.googleapis.com/auth/spreadsheets']
                )
                return credentials
        except Exception as e:
            st.error(f"認証エラー: {e}")
            return None
    
    def init_sheets_service(self):
        """Sheets APIを初期化"""
        try:
            credentials = self.get_credentials()
            if not credentials:
                return
                
            self.sheets_service = build('sheets', 'v4', credentials=credentials)
            
            # 履歴シートを作成/確認
            self.ensure_history_sheet()
        except Exception as e:
            st.error(f"Sheets API初期化エラー: {e}")
    
    def ensure_history_sheet(self):
        """履歴シートが存在しなければ作成"""
        try:
            # 既存のシート一覧を取得
            sheet_metadata = self.sheets_service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            sheets = sheet_metadata.get('sheets', [])
            sheet_names = [s['properties']['title'] for s in sheets]
            
            if 'SEO分析履歴' not in sheet_names:
                # シートを追加
                request = {
                    'requests': [{
                        'addSheet': {
                            'properties': {
                                'title': 'SEO分析履歴'
                            }
                        }
                    }]
                }
                self.sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body=request
                ).execute()
                
                # ヘッダー行を追加
                headers = [['タイムスタンプ', 'サイト', 'ユーザー', 'キーワード', 'URL', 'モード', '分析結果']]
                self.sheets_service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range='SEO分析履歴!A1:G1',
                    valueInputOption='RAW',
                    body={'values': headers}
                ).execute()
                
        except Exception as e:
            st.error(f"シート作成エラー: {e}")
    
    def save_analysis(self, keyword, url, analysis, mode):
        """分析結果をスプレッドシートに保存"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            user_name = os.environ.get('USERNAME', 'unknown')
            site_name = st.session_state.site['name']
            
            # 分析結果を短縮（スプレッドシートのセル制限対策）
            analysis_short = analysis[:5000] if len(analysis) > 5000 else analysis
            
            # 新しい行のデータ
            new_row = [[timestamp, site_name, user_name, keyword, url, mode, analysis_short]]
            
            # シートに追加
            self.sheets_service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range='SEO分析履歴!A:G',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': new_row}
            ).execute()
            
            return f"{timestamp}_{keyword}"
            
        except Exception as e:
            st.error(f"スプレッドシート保存エラー: {e}")
            return None
    
    def load_history(self, site_name=None, limit=20):
        """スプレッドシートから履歴を読み込み"""
        try:
            # データを取得
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='SEO分析履歴!A:G'
            ).execute()
            
            values = result.get('values', [])
            if len(values) <= 1:  # ヘッダーのみ
                return []
            
            # データを辞書形式に変換（ヘッダーを除く）
            history = []
            for row in reversed(values[1:]):  # 新しい順
                if len(row) >= 7:
                    data = {
                        'timestamp': row[0],
                        'site': row[1],
                        'user': row[2],
                        'keyword': row[3],
                        'url': row[4],
                        'mode': row[5],
                        'analysis': row[6]
                    }
                    
                    # サイト名でフィルタ
                    if site_name is None or data['site'] == site_name:
                        history.append(data)
                        if len(history) >= limit:
                            break
            
            return history
            
        except Exception as e:
            st.error(f"履歴読み込みエラー: {e}")
            return []
