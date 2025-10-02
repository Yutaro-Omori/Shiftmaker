import sys
from llm_shift_da_concept_extractor import DA_Concept
import requests
import json
from datetime import datetime, timedelta, time
#from telegram.ext import Updater, CommandHandler, MessageHandler, filters
import re
import shiftmaker
from llm_shift_concept_extractor import get_shift_info_from_utterance
from llm_shift_da_concept_extractor import DA_Concept
import calendar


class FrameShiftSystem:
    # 日付のリスト
    #month = ["今月","来月"]
    
    uttdic = {"start-dialog": "いつのシフトを作成しますか",
            "input-hope": "従業員の出勤希望を入力してください",
            "hope-confirm": "従業員の出勤希望を確認します",
            "initialize": "入力を初期化します",
            "correct-info": "入力を訂正します",
            "output-shift": "シフトを出力します",
            }
    
    def __init__(self):
        # 対話セッションを管理するための辞書
        self.sessiondic = {}
        
        # 対話行為タイプとコンセプトを抽出するためのモジュールの読み込み
        self.da_concept = DA_Concept()
    
    # 発話から得られた情報をもとにフレームを更新
    def update_frame(self, frame, da, conceptdic):
        for k, v in conceptdic.items():
            #値の整合性を確認し，整合しないものは空文字にする
            if k == "worker" and not isinstance(v, str):
                conceptdic[k] = f"Noname_{len(frame['workers'])}"
            # 月については「今月」または「来月」のいずれかであることを確認
            # if k == "month":
            #     if v not in ["今月", "来月"]:
            #         conceptdic[k] = "来月"
            #     frame["month"] = conceptdic[k]
                    
            # それぞれの日付について，指定した月の範囲外だった場合，除外する
            elif k == "date":
                if not isinstance(v, list) or not all(isinstance(d, str) for d in v):
                    conceptdic[k] = []
                else:
                    # 月の範囲を確認
                    valid_dates = []
                    for d in v:
                        #正規表現により m-d形式であることを確認(m,dは2桁である可能性があることに注意)
                        if re.match(r'^\d{1,2}-\d{1,2}$', d):
                            month_num, day_num = map(int, d.split('-'))
                            # 現在の日付をdatetime.now()により取得し，対象となる月とmonth_numが一致するか確認
                            if month_num == datetime.now().month:
                                if day_num < calendar.monthrange(datetime.now().year, month_num)[1]:
                                    valid_dates.append(d)
                                
                    conceptdic[k] = valid_dates
            # 曜日については0から6の整数のリストであることを確認
            elif k == "weekday":
                if not isinstance(v, list) or not all(isinstance(w, int) and 0 <= w <= 6 for w in v):
                    conceptdic[k] = []
                # 曜日に重複があった場合，重複しているもののうち一つを除去
                elif len(v) != len(set(v)):
                    conceptdic[k] = list(set(v))
            # 反転フラグについては0または1であることを確認
            elif k == "date_inv" or k == "weekday_inv":
                if v not in [0, 1]:
                    conceptdic[k] = 0
        if da == "input-hope":
            # 従業員の希望休を入力
            #もし従業員名の名前がなければ仮でつける
            #もし従業員名が既出でなければ,フレームの従業員リストworkerに追加
            worker = conceptdic.get("worker", f"Noname_{len(frame['workers'])}")
            if worker == "":
                worker = f"Noname_{len(frame['workers'])}"
            print(worker)
            if worker and worker not in frame.get("workers", []):
                frame["workers"].append(worker)
            # 希望休の日付をフレームの希望休リストに追加()
            date = conceptdic.get("date", [])
            if "hopes" not in frame:
                frame["hopes"] = []
            hope_date = []
            for d in date:
                # 希望休を従業員名と日付(月日から日にちだけを抜き出したint型)のタプルとして追加
                day = int(d.split('-')[1])  # m-d形式から日にちを抽出
                hope_date.append(day)
            # date_invが1の場合は希望休を反転
            month_info = shiftmaker.get_next_month_info(1 if frame["month"] == "来月" else 0)
            if conceptdic.get("date_inv", 0) == 1:
                l = [i + 1 for i in range(month_info[1])]
                hope_date = [d for d in l if d not in hope_date]
            # 希望休をフレームの希望休リストに追加
            frame["hopes"] += [(worker, day) for day in hope_date]
            # 曜日が指定されている場合は、希望休の曜日をフレームに追加
            weekday = conceptdic.get("weekday", [])
            hope_weekday = []
            if weekday:
                now = datetime.now()
                year = now.year + (1 if now.month == 12 and frame["month"] == "来月" else 0)
                month = now.month + (1 if frame["month"] == "来月" else 0)%12
                hope_weekday = shiftmaker.get_days_by_weekdays(datetime(year, month, 1), weekday)
            # weekday_invが1の場合は希望休の曜日を反転
            if conceptdic.get("weekday_inv", 0) == 1:
                l = [i + 1 for i in range(month_info[1])]
                hope_weekday = [d for d in l if d not in hope_weekday]
            hope_weekday = list(set(hope_weekday)-set(hope_date))  # 希望休の日付と重複しないようにする
            # 希望休の曜日をフレームの希望休リストに追加
            frame["hopes"] += [(worker, day) for day in hope_weekday]
            
        elif da == "initialize":
            # 入力を初期化
            frame = {"workers": [], "month": "", "hopes": []}

        elif da == "correct-info":
            # monthの修正
            month = conceptdic.get("month", "来月")
            #monthが入力されていたらフレームを修正
            if month:
                frame["month"] = month
            # 入力の訂正
            worker = conceptdic.get("worker", "")
            if worker in frame.get("workers", []):
                frame["workers"].remove(worker)
            # 指定された従業員の希望休をフレームの希望休リストから全て削除
            date = conceptdic.get("date", [])
            if "hopes" in frame:
                # 指定された従業員の希望休がないリストを作り，frame["hopes"]を差し替える
                frame["hopes"] = [hope for hope in frame["hopes"] if hope[0] != worker]
        
        return frame
    

    # フレームの状態から次のシステム対話行為を決定
    def next_system_da(self, frame):
        # すべてのスロットが空であればオープンな質問を行う
        if frame["workers"] == [] and frame["month"] == "" and frame.get("hopes", []) == []:
            return "start-dialog"
        # 空のスロットがあればその要素を質問する
        else:
            return "input-hope"

    def initial_message(self, input):
        text = input["utt"]
        sessionId = input["sessionId"]
        # セッションIDとセッションに関連する情報を格納した辞書
        self.sessiondic[sessionId] = {"frame": {"workers": [], "month": "", "hopes": []}}

        return {"utt":"こちらはシフト作成システムです。ご用件をどうぞ。", "end":False}

    def reply(self, input):
        text = input["utt"]
        sessionId = input["sessionId"]
        print("sessionId is" + sessionId)

        # 現在のセッションのフレームを取得
        frame = self.sessiondic[sessionId]["frame"]
        print("frame=", frame)

        # 発話から対話行為タイプとコンセプトを取得
        da, conceptdic = self.da_concept.process(text)
        print(da, conceptdic)
        
        # 対話行為タイプとコンセプトを用いてフレームを更新
        frame = self.update_frame(frame, da, conceptdic)
        print("updated frame=", frame)

        # 更新後のフレームを保存
        self.sessiondic[sessionId] = {"frame": frame}

        # フレームからシステム対話行為を得る
        sys_da = self.next_system_da(frame)
        if da == "hope-confirm":
            utts = []
            utts.append("ただいまの入力は以下の通りです:")
            utts.append(json.dumps(frame))
            return {"utt":utts, "end": False}
            
        if da == "output-shift":
            # もしフレームの従業員リストがからであればsys_daを"input-hope"にしてシステム発話を生成
            if not frame["workers"]:
                sys_da = "input-hope"
                sysutt = self.uttdic[sys_da]
                return {"utt":"従業員が登録されていません．" + sysutt, "end": False}
            # シフトを出力する
            shift = shiftmaker.Shiftmaker(frame["workers"], frame["hopes"])
            shift_info = shift.make_shift()#pandas DataFrameを返す
            # シフト情報を出力
            utts = []
            utts.append(frame["month"] + "のシフトを出力します")
            utts.append(shift_info.to_string())
            utts.append("ご利用ありがとうございました")
            self.sessiondic[sessionId] = {"frame": {"workers": [], "month": "", "hopes": []}}
            return {"utt":"\n".join(utts), "end": True}
        
        else:
            # その他の遷移先の場合は状態に紐づいたシステム発話を生成
            sysutt = self.uttdic[sys_da]            
            return {"utt":sysutt, "end": False}

if __name__ == '__main__':
    system = FrameShiftSystem()
    # テスト用の入力
    test_input = {
        "utt": "来月のシフトを作成してください",
        "sessionId": "test_session_1"
    }
    # 初期メッセージの取得
    initial_response = system.initial_message(test_input)
    print("Initial Response:", initial_response)
    # システムへの応答
    response = system.reply(test_input)
    print("Response:", response)
    # 追加のテスト入力
    test_input["utt"] = "大森は9月1日から9月5日と9月11~30日に出勤できます"
    response = system.reply(test_input)
    print("Response:", response)
    test_input["utt"] = "小林は水曜日以外は出勤できる"
    response = system.reply(test_input)
    print("Response:", response)
    test_input["utt"] = "東は9/1~10,9/20~30に出勤できる"
    response = system.reply(test_input)
    print("Response:", response)
    test_input["utt"] = "小室は9/1~10,9/25~30に出勤できる"
    
    test_input["utt"] = "シフトを出力"
    response = system.reply(test_input)
    print("Response:", response)
    

# end of file
