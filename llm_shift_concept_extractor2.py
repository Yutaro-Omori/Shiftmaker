import google.generativeai as genai
from dotenv import load_dotenv
import json
import logging
import os
import re
import datetime

load_dotenv()  # .envファイルから環境変数を読み込む

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

api_key = os.environ["gemini_api_key"]  # 環境変数からAPIキーを取得
if not api_key:
    logging.error("環境変数 'gemini_api_key' が設定されていません。Geminiモデルを初期化できません。")
    model = None
    
else:
    logging.info("Geminiモデルを初期化します...")

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.0-flash-exp')

#DEFAULT_WEATHER_INFO = {"place": "", "date": "", "type": ""}
DEFAULT_SHIFT_INFO = {"weekday": [], "weekday_inv": 0, "date": [], "date_inv": 0}

def get_shift_info_from_utterance(utterance: str) -> dict:
    if not model:
        logging.error("Geminiモデルが初期化されていません。デフォルト値を返します。")
        return DEFAULT_SHIFT_INFO.copy()

    month = datetime.datetime.now().month
    prompt = f"""
以下のユーザ発話から,シフト情報を抽出してください。
抽出する情報は,月日のリスト, 指定された日に出勤できるかまたは!その日以外!で出勤できるのか，曜日,指定された曜日に出勤できるかまたは!その日以外!で出勤できるのかです。
結果は,キー "date","date_inv","weekday","weekday_inv", を持つJSONオブジェクトとして返してください。
もし情報が見つからない場合は,対応する値として空文字列 "" を使用してください。
なお，今月は{month}月です。
月に関して言及がなかった場合は，上の情報を使ってください。

制約:
- "date" は m-d 形式の文字列のリストで,月日のリストを表します。(例:1月1日,1月2日,1月5日 -> ["1-1", "1-2", "1-5"],1/1と1/3~6 -> ["1-1", "1-3", "1-4", "1-5", "1-6"]このように期間で日付を指定されることもあるので注意してください)出勤できる日がない場合は空リストにしてください。
- "date_inv" は0または1で,指定された日に出勤できるかどうかを表します。0は指定された日に出勤できる,1は指定された日!以外!に出勤できることを意味します。言及がない場合は0にしてください。
- "weekday" は0から6の整数のリストで,0=月曜, 1=火曜, ..., 6=日曜を表します(例: 月，水，金->[0,2,4],木~土->[4,5,6]このように波線で指定されることもあるので注意してください)。言及がなかった場合は[0,1,2,3,4,5,6]にしてください。
- "weekday_inv" は0または1で,指定された曜日に出勤できるかどうかを表します。0は指定された曜日に出勤できる,1は指定された曜日!以外!に出勤できることを意味します。言及がない場合は0にしてください。

ユーザ発話: 「{utterance}」

抽出結果 (JSON形式):
"""

    logging.info(f"Geminiに送信するプロンプト:\n---\n{prompt}\n---")

    try:
        response = model.generate_content(prompt)

        if not response.parts:
            logging.warning(f"Geminiからの応答が空またはブロックされました。 Safety feedback: {response.prompt_feedback}")
            return DEFAULT_SHIFT_INFO.copy()

        response_text = response.text.strip()
        logging.info(f"Geminiからの生レスポンス: {response_text}")

        #レスポンス変換部分
        # Markdownのコードブロック形式 (```json ... ```) を除去
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip() # 再度トリム

        # JSON文字列をPython辞書に変換
        extracted_data = json.loads(response_text)

        # 期待されるキーが存在し,値が文字列であることを確認
        # place = str(extracted_data.get("place", ""))
        # date = str(extracted_data.get("date", ""))
        # type_ = str(extracted_data.get("type", "")) # typeは組み込み関数名なのでtype_を使用
        #month = str(extracted_data.get("month", ""))
        date = extracted_data.get("date", [])
        date_inv = int(extracted_data.get("date_inv", 0)) # 0または1
        weekday = extracted_data.get("weekday", [])
        weekday_inv = int(extracted_data.get("weekday_inv", 0)) # 0または1

        # 入力された月が「今月」または「来月」のいずれかであることを確認
        # if month not in ["今月", "来月"]:
        #     logging.warning(f"予期しない月 '{month}' が抽出されました。来月に設定します。")
        #      = "来月"
        #入力された日付データがすべてm-d形式の文字列であることを確認(月と日は2桁である可能性もあることに注意)
        if not all(isinstance(d, str) and re.match(r'^\d{1,2}-\d{1,2}$', d) for d in date):
            logging.warning(f"予期しない日付形式が抽出されました。空リストに設定します。")
            date = []
        #入力された曜日データが0から6の整数のリストであることを確認
        if not all(isinstance(w, int) and 0 <= w <= 6 for w in weekday):
            logging.warning(f"予期しない曜日形式が抽出されました。空リストに設定します。")
            weekday = []
        # 入力されたdate_invとweekday_invが0または1であることを確認
        if date_inv not in [0, 1]:
            logging.warning(f"予期しない日付反転フラグ '{date_inv}' が抽出されました。0に設定します。")
            date_inv = 0
        if weekday_inv not in [0, 1]:
            logging.warning(f"予期しない曜日反転フラグ '{weekday_inv}' が抽出されました。0に設定します。")
            weekday_inv = 0
        
        #result = {"place": place, "date": date, "type": type_}
        result = {"date": date, "date_inv": date_inv, "weekday": weekday, "weekday_inv": weekday_inv}
        # 抽出結果をログに出力
        logging.info(f"抽出・整形後の結果: {result}")
        return result

    except json.JSONDecodeError as e:
        logging.error(f"Geminiからの応答のJSON解析に失敗しました: {e}")
        logging.error(f"解析対象のテキスト: {response_text}")
        return DEFAULT_SHIFT_INFO.copy()
    except Exception as e:
        # API呼び出し中のエラーやその他の予期せぬエラー
        logging.error(f"シフト情報の抽出中に予期せぬエラーが発生しました: {e}")
        return DEFAULT_SHIFT_INFO.copy()

# --- 実行例 ---
if __name__ == "__main__":
    if model is None:
        print("Geminiモデルが利用できないため,テストを実行できません。")
        print("環境変数 'GEMINI_API_KEY' を設定して,再度実行してください。")
        exit(1)
    test_utterances = [
        "来月のシフト",
        "大森は1月1日から1月5日まで出勤できる",
        "佐藤は水曜日に出勤できる",
        "小林は水~金以外で出勤できる",
        "杉田は水曜日以外の1/1~5に出勤できる",
        "東堂は1/1日以外は毎日出勤できる"
    ]

    if model: # モデルが正常に初期化された場合のみ実行
        for utt in test_utterances:
            info = get_shift_info_from_utterance(utt)
            print(f"発話: 「{utt}」 -> 抽出結果: {info}")
    else:
        print("Geminiモデルが利用できないため,テストを実行できません。")
        print("環境変数 'GEMINI_API_KEY' を設定して,再度実行してください。")
