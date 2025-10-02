import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import logging
import calendar


class ShiftHopeDB:
    """
    従業員の希望シフトを「日付が行、従業員が列」の表形式で管理するSQLiteクラス。
    """
    DB_NAME = 'shift_hopes_pivot.db'
    TABLE_NAME = 'HopeSheet'
    
    def __init__(self, year=datetime.now().year):
        self.year = year
        self.conn = sqlite3.connect(self.DB_NAME)
        self.cursor = self.conn.cursor()
        self._ensure_table_exists()
        
    def _ensure_table_exists(self):
        """データベーステーブルが存在することを確認し、日付列を追加します。"""
        # DATE_ID (例: 2025-09-10) を主キーとする
        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                date_id TEXT PRIMARY KEY NOT NULL
            )
        """)
        self.conn.commit()
    
    def add_employee_column(self, worker_name: str):
        """
        テーブルに新しい従業員（列）を追加します。
        すでに存在する場合は何もしません。
        """
        # SQLの列名は予約語や特殊文字を避けるため、安全な形式に整形します
        safe_worker_name = worker_name.replace(' ', '_').replace('-', '_')
        try:
            # ALTER TABLEで新しい列を追加
            self.cursor.execute(f"ALTER TABLE {self.TABLE_NAME} ADD COLUMN {safe_worker_name} INTEGER DEFAULT 0")
            self.conn.commit()
            print(f"新しい従業員 '{worker_name}' の列を追加しました。")
        except sqlite3.OperationalError as e:
            # 列がすでに存在する場合のエラーを無視
            if "duplicate column name" in str(e):
                pass
            else:
                raise e


    def _get_target_months(self, current_date: datetime):
        """
        現在の月を基準に、保持すべき「前後6ヶ月」の日付ID範囲を計算します。
        例: 9月の場合、3月から翌年3月1日までを計算します。
        """
        # 開始日（現在から6ヶ月前）を計算
        start_month = current_date.month - 5
        start_year = current_date.year
        while start_month <= 0:
            start_month += 12
            start_year -= 1
        
        # 終了日（現在から6ヶ月後）を計算
        end_month = current_date.month + 6
        end_year = current_date.year
        while end_month > 12:
            end_month -= 12
            end_year += 1
            
        # 保持期間の開始日（月初の1日）
        start_date = datetime(start_year, start_month, 1)
        
        # 保持期間の終了日（終了月の末日）
        # 終了月（end_month）の1日より一つ進んだ月、その月の1日より1日前にすることで末日を取得
        try:
            next_month = end_month + 1 if end_month < 12 else 1
            next_year = end_year if end_month < 12 else end_year + 1
            end_of_range = datetime(next_year, next_month, 1) - timedelta(days=1)
        except ValueError:
            # 例外処理: 月が12を超える場合
            last_day = calendar.monthrange(end_year, end_month)[1]
            end_of_range = datetime(end_year, end_month, last_day)

        # YYYY-MM-DD 形式の文字列を返す
        return start_date.strftime('%Y-%m-%d'), end_of_range.strftime('%Y-%m-%d')


    def auto_manage_dates(self):
        """
        1. 保持期間外（前後6ヶ月の範囲外）の日付をデータベースから削除します。
        2. 新しい月（まだデータがない月）を初期状態（希望0）で追加します。
        """
        # 現在の日付（実行時）を基準とします
        current_date = datetime.now()
        
        # 従業員リストを取得 (DATE_ID列を除いたすべての列名)
        self.cursor.execute(f"PRAGMA table_info({self.TABLE_NAME})")
        columns = [col[1] for col in self.cursor.fetchall()]
        employee_cols = [col for col in columns if col != 'date_id']
        
        # ★ 修正点1: 従業員がいない場合は、日付のみを挿入するSQLに切り替える
        if not employee_cols:
            print("従業員が登録されていないため、日付の初期化をDATE_IDのみで行います。")
            cols_str = '' # 列名は空のまま
            value_placeholders = '' # プレースホルダも空のまま
        else:
            cols_str = ', '.join(employee_cols)
            # ?の数（従業員列の数）に合わせて値のプレースホルダを作成
            value_placeholders = ', '.join(['?'] * len(employee_cols)) # ★修正点2: ?を使う


        # --- 1. 古いデータの削除 ---
        start_date_str, end_date_str = self._get_target_months(current_date)
        print(f"保持すべき日付範囲: {start_date_str} から {end_date_str}")
        
        # 保持範囲外の日付（date_id）を削除
        self.cursor.execute(f"""
            DELETE FROM {self.TABLE_NAME}
            WHERE date_id < ? OR date_id > ?
        """, (start_date_str, end_date_str))
        
        print(f"古い日付を削除しました。保持範囲: {start_date_str} から {end_date_str}")
        
        
        # --- 2. 新しい月の初期化（出勤希望 0） ---
        
        # 保持すべき全期間（開始日〜終了日）の各日付をリストアップ
        current = datetime.strptime(start_date_str, '%Y-%m-%d')
        end = datetime.strptime(end_date_str, '%Y-%m-%d')
        all_dates_in_range = []
        while current <= end:
            all_dates_in_range.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
            
        # 既存の日付を取得
        self.cursor.execute(f"SELECT date_id FROM {self.TABLE_NAME}")
        existing_dates = {row[0] for row in self.cursor.fetchall()}
        
        # 存在しない日付（初期化が必要な日付）を抽出
        dates_to_insert = [date_id for date_id in all_dates_in_range if date_id not in existing_dates]
        
        if dates_to_insert:
            insert_count = 0
            
            # ★ 修正点3: SQL文を条件によって分岐させる
            if employee_cols:
                # 従業員がいる場合: 全列に0を挿入
                initial_values_sql = f"""
                    INSERT INTO {self.TABLE_NAME} (date_id, {cols_str})
                    VALUES (?, {value_placeholders})
                """
                
                # date_idと、0を並べたタプルを生成
                initial_params = [0] * len(employee_cols)
                
                for date_id in dates_to_insert:
                    self.cursor.execute(initial_values_sql, (date_id, *initial_params)) # ★修正点4: パラメータに0を含める
                    insert_count += 1
            else:
                # 従業員がいない場合: date_idのみ挿入
                initial_values_sql = f"""
                    INSERT INTO {self.TABLE_NAME} (date_id)
                    VALUES (?)
                """
                for date_id in dates_to_insert:
                    self.cursor.execute(initial_values_sql, (date_id,))
                    insert_count += 1

            self.conn.commit()
            print(f"✅ 新しい月を含め、{insert_count} 日分を初期状態（出勤希望 0）で追加しました。")
        else:
            print("初期化が必要な新しい日付はありませんでした。")

    def insert_or_update_hopes(self, worker: str, concept: dict):
        """
        Geminiから抽出された希望シフト情報を挿入または更新します。
        """
        self.add_employee_column(worker) # まず従業員列が存在することを確認

        # 挿入する値 (date_inv=0: 出勤希望 -> 1, date_inv=1: 休み希望 -> 0)
        hope_value = 1 if concept.get('date_inv', 0) == 0 else 0
        safe_worker_name = worker.replace(' ', '_').replace('-', '_')

        for date_str in concept.get('date', []):
            try:
                # 日付を YYYY-MM-DD 形式に変換（年を補完）
                month, day = map(int, date_str.split('-'))
                # 現在の年を使用し、日付IDを確定
                date_id = f"{self.year}-{month:02d}-{day:02d}"

                # 1. まず日付（行）が存在するか確認し、存在しない場合は挿入
                self.cursor.execute(f"INSERT OR IGNORE INTO {self.TABLE_NAME} (date_id) VALUES (?)", (date_id,))
                
                # 2. 従業員の列を更新 (ON CONFLICT REPLACEは使えないためUPDATEで対応)
                self.cursor.execute(f"""
                    UPDATE {self.TABLE_NAME}
                    SET {safe_worker_name} = ?
                    WHERE date_id = ?
                """, (hope_value, date_id))
                
            except Exception as e:
                print(f"データの挿入中にエラーが発生しました ({date_str}): {e}")
                continue

        self.conn.commit()
        return len(concept.get('date', []))
    

    def get_hope_sheet_as_dataframe(self):
        """
        全希望シフトデータをPandas DataFrameとして取得します。
        """
        query = f"SELECT * FROM {self.TABLE_NAME} ORDER BY date_id"
        df = pd.read_sql_query(query, self.conn, index_col='date_id')
        return df

    def close(self):
        """データベース接続を閉じます。"""
        if self.conn:
            self.conn.close()

# --- 使用例 ---
if __name__ == '__main__':
    # データベースファイルの削除（テスト用）
    if os.path.exists(ShiftHopeDB.DB_NAME):
        os.remove(ShiftHopeDB.DB_NAME)
        
    db_manager = ShiftHopeDB(year=2025)
    db_manager.auto_manage_dates()
    # サンプルデータ1: 大森の9月の出勤希望
    omori_hope = {
        "worker": "大森", 
        "date": ["9-10", "9-11", "9-12", "9-25"], 
        "date_inv": 0 # 出勤希望
    }
    db_manager.insert_or_update_hopes(omori_hope['worker'], omori_hope)
    
    # サンプルデータ2: 小林の10月の休み希望
    kobayashi_hope = {
        "worker": "kobayashi", 
        "date": ["10-1", "10-2"], 
        "date_inv": 1 # 休み希望
    }
    db_manager.insert_or_update_hopes(kobayashi_hope['worker'], kobayashi_hope)

    # サンプルデータ3: 大森の9月の希望を上書き
    omori_update = {
        "worker": "大森", 
        "date": ["9-10", "9-13"], # 9-11, 9-12の希望はそのまま残る
        "date_inv": 0 # 出勤希望
    }
    db_manager.insert_or_update_hopes(omori_update['worker'], omori_update)
    
    # 古いデータの削除と新しい月の初期化

    # 全データの取得と表示 (DataFrame形式)
    hope_df = db_manager.get_hope_sheet_as_dataframe()
    print("\n--- シフト希望データベース (DataFrame) ---")
    print(hope_df)
    
    db_manager.close()