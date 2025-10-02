import google.generativeai as genai
import logging
import os
from llm_shift_concept_extractor import get_shift_info_from_utterance
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

api_key = os.environ["gemini_api_key"]  # 環境変数からAPIキーを取得
if not api_key:
    logging.error("環境変数 'gemini_api_key' が設定されていません。Geminiモデルを初期化できません。")
    model = None
else:
    logging.info("Geminiモデルを初期化します...")

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.0-flash-exp')

DEFAULT_DA = ""
DEFAULT_CONCEPT = {
    "worker": "",
    "month": "",
    "date": [],
    "date_inv": 0,
    "weekday": [],
    "weekday_inv": 0
}

class DA_Concept:
    def __init__(self):
        self.model = model

    def process(self, utt):
        # 対話行為タイプの抽出
        if not self.model:
            logging.error("Geminiモデルが初期化されていません。デフォルト値を返します。")
            return DEFAULT_DA, DEFAULT_CONCEPT.copy()

        prompt = f"""
以下のユーザ発話から,対話行為タイプのみを抽出してください。
対話行為タイプは,以下の5つのラベルのいずれかです:
- start-dialog: 対話の開始(入力例: 「来月のシフトを作成してください」,「今月のシフト」)
- input-hope: 従業員の出勤希望を入力(入力例:「大森は1月1日から1月5日と1月11日に出勤できます」)
- hope-confirm: 従業員の出勤希望を確認する(入力例「大森のシフトをおしえて」)
- initialize: 入力の初期化(入力例:「シフトを初期化してください」,「シフトをリセット」,「初めから」，「キャンセル」)
- correct-info: 入力の訂正(入力例:「今月じゃない」,「大森のシフトを治したい」,「大森のシフトを訂正」)
- output-shift: シフトの出力(入力例:「シフトを出力」,「シフトを見せて」,「シフトを確認」)
出力はラベルのみで,他の説明や装飾は不要です。

ユーザ発話: 「{utt}」
"""

        try:
            response = self.model.generate_content(prompt)
            if not response.parts:
                logging.warning("Geminiからの応答が空またはブロックされました。")
                da = DEFAULT_DA
            else:
                da = response.text.strip().split()[0]  # 先頭の単語のみ

        except Exception as e:
            logging.error(f"Gemini APIでエラー: {e}")
            da = DEFAULT_DA

        # コンセプト抽出
        concept = get_shift_info_from_utterance(utt)
        print("da:" + da)
        return da, concept

if __name__ == "__main__":
    llm_da = DA_Concept()
    utt = "リセット"
    da, concept = llm_da.process(utt)
    print("対話行為タイプ:", da)
    print("コンセプト:", concept)