import pulp
from datetime import datetime, timedelta
import datetime
import calendar
import pandas as pd
from IPython.display import display # display関数をインポート


day_name = ['月曜', '火曜', '水曜', '木曜', '金曜', '土曜', '日曜']

# def get_next_month_info():
#     # 現在の日付と時刻を取得
#     now = datetime.datetime.now()

#     # 次の月を計算
#     if now.month == 12:
#         next_month = 1
#         year = now.year + 1
#     else:
#         next_month = now.month + 1
#         year = now.year

#     # 次の月の1日を表すdatetimeオブジェクトを作成
#     first_day = datetime.datetime(year, next_month, 1)

#     # 月の日数を取得
#     days_in_month = calendar.monthrange(year, next_month)[1]

#     # 曜日を取得（calendarでは月曜=0、日曜=6）
#     weekday = first_day.weekday()

#     return [first_day, days_in_month, weekday]

def get_next_month_info(month_diff: int = 1):#来月の情報を取得する関数
    # 現在の日付と時刻を取得
    now = datetime.datetime.now()
    # 月の差を考慮して次の月を計算
    if now.month + month_diff > 12:
        next_month = (now.month + month_diff) % 12
        year = now.year + (now.month + month_diff) // 12
    else:
        next_month = now.month + month_diff
        year = now.year

    # 次の月の1日を表すdatetimeオブジェクトを作成
    first_day = datetime.datetime(year, next_month, 1)

    # 月の日数を取得
    days_in_month = calendar.monthrange(year, next_month)[1]

    # 曜日を取得（calendarでは月曜=0、日曜=6）
    weekday = first_day.weekday()

    return [first_day, days_in_month, weekday]


def get_days_by_weekdays(date: datetime.datetime, Dotw: list):#指定された曜日のリストに基づいて、指定された月の日付を取得する関数
    year = date.year
    month = date.month

    # 月の日数を取得
    days_in_month = calendar.monthrange(year, month)[1]

    # 該当する日をリストアップ
    matching_days = []
    for day in range(1, days_in_month + 1):
        current_date = datetime.datetime(year, month, day)
        if current_date.weekday() in Dotw:
            matching_days.append(day)

    return matching_days


class Shiftmaker:
    def __init__(self, Emp, Hope):
        """
        Shiftmakerクラスのコンストラクタ

        Args:
            Emp (list): 従業員のリスト
            Hope (list of tuples): 各従業員の希望休のリスト. タプルの形式は (従業員名, 希望日)
            希望日は日付 (int) で指定します。
        """
        self.Emp = Emp
        self.Hope = Hope # 希望休をインスタンス変数として保持
        self.next_month_info = get_next_month_info() # インスタンス変数として保持
        self.day = self.next_month_info[1] # 来月の日数
        self.Day = list(range(1, self.day + 1)) # 日付リスト

    def make_shift(self):
        """
        シフトを作成する

        Returns:
            pandas.DataFrame: 作成されたシフトデータ
        """

        # 必要人数
        n_req = 1

        # 最適化モデル
        prob = pulp.LpProblem("ShiftFittingProblem",pulp.LpMinimize)

        # 変数定義
        ED = [(e, d) for e in self.Emp for d in self.Day]
        x = pulp.LpVariable.dicts("x", ED, cat = "Binary")

        """
        シフト作成の制約条件:
        各従業員の希望休を反映する (希望日は出勤としない)
        従業員全員の勤務日数が平均勤務日数の半分以上
        従業員全員の勤務日数の1.5倍以下
        1日あたりの出勤人数はS_req人
        3連勤以上を作らない
        """
        #希望休を反映
        for e, d in self.Hope:
          prob += x[e, d] ==1

        # 1日あたりの出勤人数はS_req人
        for d in self.Day:
          prob += pulp.lpSum([1 - x[e, d] for e in self.Emp]) == n_req

        # 従業員全員の勤務日数が平均勤務日数の1/1.5倍以上
        for e in self.Emp:
          # 出勤日数をカウント
          prob += self.day - pulp.lpSum([x[e, d] for d in self.Day]) >= (self.day / len(self.Emp) / (1.5))

        # 従業員全員の勤務日数が平均勤務日数の1.5倍以下
        for e in self.Emp:
          # 出勤日数をカウント
          prob += self.day - pulp.lpSum([x[e, d] for d in self.Day]) <= (self.day / len(self.Emp) * 2)

        # 3連勤以上を作らない
        workday = 3
        for e in self.Emp:
          for d in self.Day[:-(workday-1)]:
            sum_x = pulp.lpSum([x[e, d+i] for i in range(workday)])
            prob += sum_x >= 1
        # 目的関数: 休みの合計日数を最小化する（つまり、出勤日数を最大化する）
        status = prob.solve()
        print("Status:", pulp.LpStatus[status])

        # 結果表示部分と同様の操作を行い、DataFrameを返す
        #workdata = pd.DataFrame([[x[e, d].value() for d in Day]for e in Emp])
        workdata = pd.DataFrame([[1 - x[e, d].value() if x[e, d].value() is not None else None for d in self.Day] for e in self.Emp])
        Weekdays = [day_name[(self.next_month_info[2]+day-1)%7] for day in self.Day]
        multi_columns = pd.MultiIndex.from_tuples([(day, day_name[(self.next_month_info[2]+day-1)%7]) for day in self.Day], names=['Day', 'Weekday'])
        workdata.index = self.Emp
        workdata.columns = multi_columns
        workdata["合計出勤回数"] = workdata.sum(axis = 1)

        return workdata.T # pd.DataFrameを返す
