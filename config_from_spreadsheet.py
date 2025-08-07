# config_from_spreadsheet.py
import json
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

class SpreadsheetConfigLoader:
    def __init__(self, spreadsheet_id='1gwLASONia-UIaXuQV0S7nQn8oHpz7F_ONMC_rlAM15s'):
        self.spreadsheet_id = spreadsheet_id
        self.config_sheet_name = 'サイト設定'  # 新しいシート名
        self.credentials_file = 'credentials/gemini-analysis-467706-e19bcd6a67bb.json'
        
    def load_sites_from_spreadsheet(self):
        """スプレチE��シートからサイト情報を読み込む"""
        try:
            # 認証
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_file,
                scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
            )
            service = build('sheets', 'v4', credentials=credentials)
            
            # スプレチE��シートから読み込み
            # A刁E サイト名, B刁E URL, C刁E GA4 ID, D刁E 個別スプレチE��シーチED�E�オプション�E�E
            result = service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f'{self.config_sheet_name}!A2:D100'  # ヘッダー行をスキチE�E
            ).execute()
            
            values = result.get('values', [])
            sites = []
            
            for row in values:
                if len(row) >= 3 and row[0] and row[1] and row[2]:  # 忁E��頁E��チェチE��
                    site = {
                        "name": row[0].strip(),
                        "gsc_url": row[1].strip(),
                        "ga4_property_id": row[2].strip(),
                        "spreadsheet_id": row[3].strip() if len(row) > 3 and row[3] else self.spreadsheet_id
                    }
                    sites.append(site)
                    
            return sites
            
        except Exception as e:
            print(f"スプレチE��シート読み込みエラー: {e}")
            return None
    
    def create_config_with_sites(self, sites):
        """サイト情報を含む完�Eな設定を作�E"""
        config = {
            "gemini_api_key": "AIzaSyA8meCgGFsO9VNztFaGXv2Q39N_vPvonz0",
            "credentials_file":"credentials/gemini-analysis-467706-e19bcd6a67bb.json",
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
