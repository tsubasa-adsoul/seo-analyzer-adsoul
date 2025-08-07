# config_from_spreadsheet.py
import json
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import streamlit as st

class SpreadsheetConfigLoader:
    def __init__(self, spreadsheet_id='1gwLASONia-UIaXuQV0S7nQn8oHpz7F_ONMC_rlAM15s'):
        self.spreadsheet_id = spreadsheet_id
        self.config_sheet_name = 'サイト設定'  # 新しいシート名
        self.credentials_file = 'credentials/gemini-analysis-467706-e19bcd6a67bb.json'
        
    def get_credentials(self):
        """認証情報を取得（Secrets対応）"""
        try:
            # Secretsから読み込み
            if 'gcp_service_account' in st.secrets:
                credentials_dict = dict(st.secrets["gcp_service_account"])
                credentials = service_account.Credentials.from_service_account_info(
                    credentials_dict,
                    scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
                )
                return credentials
            else:
                # ローカルファイルから読み込み
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_file,
                    scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
                )
                return credentials
        except Exception as e:
            st.error(f"認証エラー: {e}")
            return None
        
    def load_sites_from_spreadsheet(self):
        """スプレッドシートからサイト情報を読み込む"""
        try:
            # 認証
            credentials = self.get_credentials()
            if not credentials:
                return None
                
            service = build('sheets', 'v4', credentials=credentials)
            
            # スプレッドシートから読み込み
            # A列: サイト名, B列: URL, C列: GA4 ID, D列: 個別スプレッドシートID（オプション）
            result = service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f'{self.config_sheet_name}!A2:D100'  # ヘッダー行をスキップ
            ).execute()
            
            values = result.get('values', [])
            sites = []
            
            for row in values:
                if len(row) >= 3 and row[0] and row[1] and row[2]:  # 必須項目チェック
                    site = {
                        "name": row[0].strip(),
                        "gsc_url": row[1].strip(),
                        "ga4_property_id": row[2].strip(),
                        "spreadsheet_id": row[3].strip() if len(row) > 3 and row[3] else self.spreadsheet_id
                    }
                    sites.append(site)
                    
            return sites
            
        except Exception as e:
            print(f"スプレッドシート読み込みエラー: {e}")
            return None
    
    def create_config_with_sites(self, sites):
        """サイト情報を含む完全な設定を作成"""
        config = {
            "gemini_api_key": "AIzaSyA8meCgGFsO9VNztFaGXv2Q39N_vPvonz0",
            "credentials_file": "credentials/gemini-analysis-467706-e19bcd6a67bb.json",
            "default_spreadsheet_id": self.spreadsheet_id,
            "sites": sites,
            "analysis_settings": {
                "gsc_days_ago": 30,
                "comparison_days_ago": 60,
                "min_clicks_for_trend": 5,
                "min_impressions_for_intent": 100,
                "max_ctr_for_intent": 0.05,
                "trend_change_threshold": 50,
                "display_limit": 20
            }
        }
        return config
