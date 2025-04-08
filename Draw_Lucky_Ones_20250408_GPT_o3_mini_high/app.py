from flask import Flask, render_template, request, flash, redirect, url_for
import pandas as pd
import os, uuid, random

app = Flask(__name__)
app.secret_key = "supersecretkey"  # 請在正式環境中換成安全的金鑰

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 全域儲存暫存資料，模擬 session，可根據需求改用 flask.session 或資料庫
storage = {}

# 去識別化函式：依據字串長度保留部分字元，再以 "*" 替換中間部分  
def deidentify(s):
    s = str(s)
    n = len(s)
    if n <= 3:
        return s
    elif n == 4:
        # 例如: "EriX" -> "Er*X"
        return s[:2] + "*" + s[3:]
    elif n <= 7:
        # 例如: 長度 5 或 6, 保留前 2 個、最後 1 個，中間換成 "*" 重複 (n-3) 次
        return s[:2] + "*"*(n-3) + s[-1]
    else:
        # 當字串長度 ≥ 8，保留前 3 個字與末 3 個字，其餘以 "*" 取代
        return s[:3] + "*"*(n-6) + s[-3:]

# 根據總筆數決定 prefix 的補零位數，並依序將 prefix 加入 de識別化後的字串中
def assign_prefixes(values):
    total = len(values)
    if total < 10:
        pad_width = 1
    elif total < 100:
        pad_width = 2
    elif total < 1000:
        pad_width = 3
    else:
        pad_width = len(str(total-1))
    result = []
    for i, val in enumerate(values):
        prefix = str(i).zfill(pad_width)
        deid = deidentify(val)
        result.append(f"{prefix}_{deid}")
    return result

@app.route("/", methods=["GET", "POST"])
def index():
    # stage: "upload" / "select_column" / "preview" / "result"
    stage = "upload"  # 預設為上傳階段
    context = {"stage": stage}
    if request.method == "POST":
        step = request.form.get("step")
        if step == "upload":
            # 步驟 1：檔案上傳
            if "file" not in request.files:
                flash("😢 沒有檔案上傳！請選擇檔案再試一次。")
                context["stage"] = "upload"
                return render_template("index.html", **context)
            file = request.files["file"]
            if file.filename == "":
                flash("😢 檔案名稱空白，請重新選擇檔案。")
                context["stage"] = "upload"
                return render_template("index.html", **context)
            if file and allowed_file(file.filename):
                filename = file.filename
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)
                # 依副檔名讀取檔案內容
                try:
                    ext = filename.rsplit('.', 1)[1].lower()
                    if ext == "csv":
                        df = pd.read_csv(filepath)
                    else:
                        df = pd.read_excel(filepath)
                except Exception as e:
                    flash("😢 讀取檔案時發生錯誤: " + str(e))
                    context["stage"] = "upload"
                    return render_template("index.html", **context)
                # 產生一組唯一 ID 以記憶該筆上傳資料
                session_id = str(uuid.uuid4())
                storage[session_id] = {"df": df}
                columns = list(df.columns)
                context.update({
                    "stage": "select_column",
                    "columns": columns,
                    "session_id": session_id,
                    "total_entries": len(df)
                })
                flash("✅ 檔案上傳成功！請選擇要抽籤的欄位。")
                return render_template("index.html", **context)
            else:
                flash("😢 檔案格式不允許！請上傳 CSV 或 Excel 檔案。")
                context["stage"] = "upload"
                return render_template("index.html", **context)
        elif step == "select_column":
            # 步驟 2：選擇欄位
            session_id = request.form.get("session_id")
            selected_column = request.form.get("column")
            if session_id not in storage:
                flash("😢 找不到對應的檔案資料，請重新上傳。")
                context["stage"] = "upload"
                return render_template("index.html", **context)
            df = storage[session_id]["df"]
            if selected_column not in df.columns:
                flash("😢 選擇的欄位不存在，請重新選擇。")
                context["stage"] = "select_column"
                context["columns"] = list(df.columns)
                context["session_id"] = session_id
                return render_template("index.html", **context)
            # 取得選擇欄位中不為空的值，並將每個元素去識別化後加上 prefix
            values = df[selected_column].dropna().astype(str).tolist()
            if len(values) == 0:
                flash("😢 選擇的欄位中沒有有效資料，請重新選擇。")
                context["stage"] = "select_column"
                context["columns"] = list(df.columns)
                context["session_id"] = session_id
                return render_template("index.html", **context)
            preview_list = assign_prefixes(values)
            # 儲存處理結果
            storage[session_id]["preview"] = preview_list
            storage[session_id]["selected_column"] = selected_column
            storage[session_id]["values"] = values
            context.update({
                "stage": "preview",
                "preview_list": preview_list,
                "session_id": session_id,
                "selected_column": selected_column,
                "total_preview": len(preview_list)
            })
            flash("✅ 已選擇欄位「" + selected_column + "」！請確認下方預覽資料，再輸入抽籤數量。")
            return render_template("index.html", **context)
        elif step == "draw":
            # 步驟 3：隨機抽籤
            session_id = request.form.get("session_id")
            draw_count_str = request.form.get("draw_count")
            if session_id not in storage or "preview" not in storage[session_id]:
                flash("😢 資料錯誤，請從頭開始。")
                context["stage"] = "upload"
                return render_template("index.html", **context)
            try:
                draw_count = int(draw_count_str)
            except ValueError:
                flash("😢 請輸入正確的數字！")
                context["stage"] = "preview"
                context["preview_list"] = storage[session_id]["preview"]
                context["session_id"] = session_id
                context["selected_column"] = storage[session_id]["selected_column"]
                context["total_preview"] = len(storage[session_id]["preview"])
                return render_template("index.html", **context)
            total = len(storage[session_id]["preview"])
            if draw_count > total:
                flash(f"😢 抽籤數量 {draw_count} 超過預覽資料總數 {total}！請調整數量。")
                context["stage"] = "preview"
                context["preview_list"] = storage[session_id]["preview"]
                context["session_id"] = session_id
                context["selected_column"] = storage[session_id]["selected_column"]
                context["total_preview"] = total
                return render_template("index.html", **context)
            result_list = random.sample(storage[session_id]["preview"], draw_count)
            context.update({
                "stage": "result",
                "result_list": result_list,
                "preview_list": storage[session_id]["preview"],
                "session_id": session_id,
                "selected_column": storage[session_id]["selected_column"],
                "draw_count": draw_count,
                "total_preview": total
            })
            flash("🎉 抽籤完成！以下是抽中的結果：")
            return render_template("index.html", **context)
    else:
        # GET 請求，顯示初始上傳畫面
        context["stage"] = "upload"
        return render_template("index.html", **context)

if __name__ == '__main__':
    app.run(debug=True)
