import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
import pandas as pd
from llm_shift_concept_extractor2 import get_shift_info_from_utterance
from shiftmaker import Shiftmaker # 追加
import re
from datetime import datetime, timedelta, time
from database import ShiftHopeDB 

load_dotenv()

app = App(token=os.environ["SLACK_BOT_TOKEN"]) 

# データベースマネージャーの初期化
db_manager = ShiftHopeDB(year=datetime.now().year) 

# --- ここに自動管理機能を組み込む ---
# ボットが起動するたびに実行することで、3ヶ月ごとのメンテナンス（削除・初期化）が実施されます
db_manager.auto_manage_dates() 


@app.command("/input_shift")#呼ばれた際に指定された日付でシフトの登録を行う(一旦は入力をそのまま出力するだけ)
def input_shift(ack, body, respond):
    ack()
    worker = body["user_name"]
    text = body.get("text", "").strip()
    
    if not text:
        respond("シフト情報が提供されていません。正しい形式でシフト情報を入力してください。")
        return
    
    #シフト情報抽出
    conceptdic = get_shift_info_from_utterance(text)
    print(conceptdic)
    respond(f"シフト情報を受け取りました: {text}")
    respond(f"抽出されたシフト情報: {conceptdic}")
    
    # 従業員の希望休を入力
    #もし従業員名の名前がなければ仮でつける
    #もし従業員名が既出でなければ,フレームの従業員リストworkerに追加

    # print(worker)
    # # 希望休の日付をフレームの希望休リストに追加()
    # date = conceptdic.get("date", [])

    # hope_date = []
    # for d in date:
    #     # 希望休を従業員名と日付(月日から日にちだけを抜き出したint型)のタプルとして追加
    #     day = int(d.split('-')[1])  # m-d形式から日にちを抽出
    #     hope_date.append(day)
    # # date_invが1の場合は希望休を反転
    # if conceptdic.get("date_inv", 0) == 1:
    #     l = [i + 1 for i in range(month_info[1])]
    #     hope_date = [d for d in l if d not in hope_date]
    # # 希望休をフレームの希望休リストに追加
    # frame["hopes"] += [(worker, day) for day in hope_date]
    # # 曜日が指定されている場合は、希望休の曜日をフレームに追加
    # weekday = conceptdic.get("weekday", [])
    # hope_weekday = []
    # if weekday:
    #     now = datetime.now()
    #     year = now.year + (1 if now.month == 12 and frame["month"] == "来月" else 0)
    #     month = now.month + (1 if frame["month"] == "来月" else 0)%12
    #     hope_weekday = shiftmaker.get_days_by_weekdays(datetime(year, month, 1), weekday)
    # # weekday_invが1の場合は希望休の曜日を反転
    # if conceptdic.get("weekday_inv", 0) == 1:
    #     l = [i + 1 for i in range(month_info[1])]
    #     hope_weekday = [d for d in l if d not in hope_weekday]
    # hope_weekday = list(set(hope_weekday)-set(hope_date))  # 希望休の日付と重複しないようにする
    # # 希望休の曜日をフレームの希望休リストに追加
    # frame["hopes"] += [(worker, day) for day in hope_weekday]
    # respond(f"{user_name}のシフト情報を受け取りました: {text}")

# /create_shift スラッシュコマンドへのリスナー
@app.command("/create_shift")
def handle_command(ack, body, respond):
    ack()
    respond("シフト作成を開始します。シフト情報を記載したファイルをアップロードしてください。")

# ボットへのメンションイベントへのリスナー
@app.event("app_mention")
def handle_app_mention(event, say, client):
    user_utterance = event['text']
    user_id = event['user']
    
    # メンション部分を除去
    # <@U12345678> シフト希望です
    # のような文字列から、"シフト希望です" の部分だけを抽出
    mention_pattern = re.compile(r'<@\w+>\s*')
    cleaned_utterance = mention_pattern.sub('', user_utterance, 1)

    say(f"メンションを受け付けました: '{cleaned_utterance}'")
    llm_da = DA_Concept()
    # ここにNLPロジックを統合
    da, concept = llm_da.process(cleaned_utterance)

    if da == 'input-hope':
        # ここでシフト希望情報を処理・保存
        say(f"出勤希望を受け付けました。担当者: {concept['worker']}、希望日: {concept['date']}")
        # データベースやファイルに希望情報を保存するロジックを実装
        # 例: save_hope_to_database(concept)
    elif da == 'start-dialog':
        say("シフト作成を開始します。シフト情報をチャットに投稿してください。")
    elif da == 'correct-info':
        say("情報の訂正ですね。変更したいシフト内容を教えてください。")
    elif da == 'output-shift':
        say("シフトを出力します。")
        # ここにシフト作成・出力ロジックを呼び出す
    else:
        say("すみません、その意図は理解できませんでした。")
# ファイルアップロードイベントへのリスナー
@app.event("file_shared")
def handle_file_shared(event, client, say):
    file_id = event["file"]["id"]
    file_info = client.files_info(file=file_id)
    file_url = file_info["file"]["url_private"]
    file_name = file_info["file"]["name"]
    #... handle_file_shared関数の続き
    file_extension = file_name.split('.')[-1].lower()

    if file_extension in ['xlsx', 'xls']:
        df = pd.read_excel(file_url)
    elif file_extension == 'csv':
        df = pd.read_csv(file_url)
    else:
        say("サポートされていないファイル形式です。CSVまたはExcelファイルをアップロードしてください。")
        return
# DataFrameをログに出力して確認
    print(df.head())

# ここにNLPとシフト作成ロジックを統合する
# 例：シフト作成ロジックの関数を呼び出し、DataFrameを渡す
# create_shift_schedule(df)
    # ここにファイルダウンロードと解析のロジックを実装
    say(f"ファイル '{file_name}' を受け取りました。解析を開始します。")
    

if __name__ == "__main__":
    handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))
    handler.start()