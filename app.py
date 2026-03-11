from flask import (
    Flask, render_template, request, abort, redirect,
    url_for, flash, session, jsonify
)
import sqlite3
import datetime
import os
import random

from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash


# =========================================================
#  Flaskアプリ設定
# =========================================================
app = Flask(__name__)
app.secret_key = "secret-key"  # セッション用キー（本番では環境変数にする）


def format_yen(value):
    # 数値に変換できる場合のみ 3 桁カンマを付与して表示する
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return value
    return f"{number:,}"


@app.template_filter("yen")
def yen_filter(value):
    return format_yen(value)


COUPON_5 = "5%引き券"
COUPON_10 = "10%引き券"
DEFAULT_USER_ICON = "user-icons/user-icon3.webp"
# クーポン名称は DB / セッション / フロント間で同じ文字列を使う


# =========================================================
#  SQLiteデータベース設定
# =========================================================
DB_PATH = os.path.join(os.path.dirname(__file__), "ec.db")

UPLOAD_FOLDER = os.path.join(
    os.path.dirname(__file__), "static", "img", "products"
)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ---------------------------------------------------------
#  データベース接続（row factory付き）
# ---------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------
#  データベース初期化（必要なテーブルが無ければ作成）
# ---------------------------------------------------------
def init_db():
    conn = get_db()

    # カテゴリ
    conn.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        categoryID INTEGER PRIMARY KEY AUTOINCREMENT,
        categoryName TEXT NOT NULL
    )
    """)

    # タグ
    conn.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        tagID INTEGER PRIMARY KEY AUTOINCREMENT,
        tagName TEXT NOT NULL
    )
    """)

    # 商品テーブル
    conn.execute("""
    CREATE TABLE IF NOT EXISTS products (
        pID INTEGER PRIMARY KEY AUTOINCREMENT,
        tagID INTEGER,
        pName TEXT NOT NULL,
        price INTEGER NOT NULL,
        pDescription TEXT,
        country TEXT,
        image TEXT,
        FOREIGN KEY (tagID) REFERENCES tags(tagID)
    )
    """)

    # おすすめ表示テーブル
    conn.execute("""
    CREATE TABLE IF NOT EXISTS recommendations (
        recommendationID INTEGER PRIMARY KEY AUTOINCREMENT,
        productID INTEGER NOT NULL,
        slot INTEGER,
        month TEXT,
        FOREIGN KEY (productID) REFERENCES products(pID)
    )
    """)

    # carts用テーブル
    conn.execute("""
    CREATE TABLE IF NOT EXISTS carts (
        cartID INTEGER PRIMARY KEY AUTOINCREMENT,
        userID INTEGER NOT NULL,
        pID INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (pID) REFERENCES products(pID)
    )
    """)

    # usersテーブル（注文情報）
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        userID INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ordersテーブル（注文情報）
    conn.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        orderID INTEGER PRIMARY KEY AUTOINCREMENT,
        userID INTEGER NOT NULL,
        total INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (userID) REFERENCES users(userID)
    )
    """)

    # order_itemsテーブル（注文情報）
    conn.execute("""
    CREATE TABLE IF NOT EXISTS order_items (
        orderItemID INTEGER PRIMARY KEY AUTOINCREMENT,
        orderID INTEGER NOT NULL,
        pID INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        price INTEGER NOT NULL,
        FOREIGN KEY (orderID) REFERENCES orders(orderID),
        FOREIGN KEY (pID) REFERENCES products(pID)
    )
    """)

    conn.commit()
    
    # 既存 DB 向け移行:
    # CREATE TABLE IF NOT EXISTS では列追加されないため、存在確認して ALTER する
    user_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
    }
    if "user_icon" not in user_columns:
        conn.execute(
            f"ALTER TABLE users ADD COLUMN user_icon TEXT DEFAULT '{DEFAULT_USER_ICON}'"
        )
    if "gacha_count" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN gacha_count INTEGER DEFAULT 0")
    if "coupon_5_count" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN coupon_5_count INTEGER DEFAULT 0")
    if "coupon_10_count" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN coupon_10_count INTEGER DEFAULT 0")

    # 画像拡張子移行: products.image が webp 以外の場合、対応する webp があれば置き換える
    if os.path.isdir(app.config["UPLOAD_FOLDER"]):
        file_name_map = {
            name.lower(): name
            for name in os.listdir(app.config["UPLOAD_FOLDER"])
        }

        image_rows = conn.execute("""
            SELECT pID, image
            FROM products
            WHERE image IS NOT NULL
        """).fetchall()

        for row in image_rows:
            image_name = row["image"]
            root, ext = os.path.splitext(image_name)
            if not root or ext.lower() == ".webp":
                continue

            webp_candidate = f"{root}.webp"
            matched_webp_name = file_name_map.get(webp_candidate.lower())
            if matched_webp_name and matched_webp_name != image_name:
                conn.execute(
                    "UPDATE products SET image = ? WHERE pID = ?",
                    (matched_webp_name, row["pID"])
                )

    conn.commit()

    conn.close()


# アプリ起動時にデータベースを初期化
init_db()


@app.context_processor
def inject_gacha_count():
    # 全テンプレートで {{ gacha_count }} を参照できるようにする
    user_id = session.get("user_id")
    if not user_id:
        return {"gacha_count": None}

    conn = get_db()
    row = conn.execute(
        "SELECT gacha_count FROM users WHERE userID = ?",
        (user_id,)
    ).fetchone()
    conn.close()

    return {"gacha_count": row["gacha_count"] if row else 0}


# =========================================================
#  ルーティング
# =========================================================

# ---------------------------------------------------------
#  トップページ（おすすめ商品 + 全商品一覧）
# ---------------------------------------------------------
@app.route("/")
def index():
    conn = get_db()
    current_month = datetime.datetime.now().strftime("%Y-%m")

    all_products = conn.execute(
        "SELECT * FROM products;"
    ).fetchall()

    sql_rec = """
        SELECT products.*
        FROM recommendations
        JOIN products ON recommendations.productID = products.pID
        WHERE recommendations.month = ?
        ORDER BY recommendations.slot;
    """
    recommended = conn.execute(sql_rec, (current_month,)).fetchall()

    conn.close()

    return render_template(
        "pages/index.html",
        recommended=recommended,
        all_products=all_products,
        q=""
    )


# ---------------------------------------------------------
#  商品ページ
# ---------------------------------------------------------
@app.route("/product")
def product():
    product_id = request.args.get("id")
    if not product_id:
        abort(404)

    conn = get_db()
    product_row = conn.execute(
        "SELECT * FROM products WHERE pID=?",
        (product_id,)
    ).fetchone()
    conn.close()

    if not product_row:
        abort(404)

    return render_template("pages/product.html", product=product_row)


# ---------------------------------------------------------
#  ミニゲーム（ガチャ画面）
# ---------------------------------------------------------
@app.route("/gacha")
def gacha():
    return render_template("pages/game-gacha.html")

@app.route("/gacha/use", methods=["POST"])
def gacha_use():
    user_id = session.get("user_id")
    if not user_id:
        return {"ok": False, "message": "ログインしてください"}

    conn = get_db()

    row = conn.execute(
        "SELECT gacha_count FROM users WHERE userID = ?",
        (user_id,)
    ).fetchone()

    if not row or row["gacha_count"] <= 0:
        conn.close()
        return {"ok": False, "message": "わくわく券がありません"}

    # 🔽 1回消費
    conn.execute(
        "UPDATE users SET gacha_count = gacha_count - 1 WHERE userID = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()

    return {"ok": True}


# ---------------------------------------------------------
#  ガチャ抽選API（フロントから呼び出し）
# ---------------------------------------------------------
@app.route("/draw")
def draw():
    # 重み付き抽選（合計 100）
    rewards = [
        ("ハズレ", 50),
        ("5％引き券", 30),
        ("10％引き券", 20)
    ]

    reward = random.choices(
        [r[0] for r in rewards],
        weights=[r[1] for r in rewards],
        k=1
    )[0]

    return jsonify({"reward": reward})

@app.route("/apply_discount", methods=["POST"])
def apply_discount():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "ログインしてください。"}), 401

    data = request.get_json() or {}
    coupon = data.get("coupon")
    if coupon not in (COUPON_5, COUPON_10):
        return jsonify({"status": "error", "message": "無効な引き券です。"}), 400

    conn = get_db()
    # ガチャで当選した券をユーザー保有数として加算
    if coupon == COUPON_10:
        conn.execute(
            "UPDATE users SET coupon_10_count = coupon_10_count + 1 WHERE userID = ?",
            (user_id,)
        )
    else:
        conn.execute(
            "UPDATE users SET coupon_5_count = coupon_5_count + 1 WHERE userID = ?",
            (user_id,)
        )
    conn.commit()
    conn.close()

    # 獲得した券を次回購入時に選択しやすいように保持
    session["discount_coupon"] = coupon
    return jsonify({"status": "ok"})


# ---------------------------------------------------------
#  新規登録
# ---------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        email = request.form.get("email")
        password = request.form.get("password")

        if not name or not phone or not email or not password:
            flash("すべての項目を入力してください。")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        conn = get_db()
        try:
            conn.execute("""
                INSERT INTO users (name, phone, email, password, user_icon)
                VALUES (?, ?, ?, ?, ?)
            """, (name, phone, email, hashed_password, DEFAULT_USER_ICON))
            conn.commit()
        except sqlite3.IntegrityError:
            flash("このメールアドレスは既に使用されています。")
            return redirect(url_for("register"))
        finally:
            conn.close()

        flash("登録が完了しました。ログインしてください。")
        return redirect(url_for("login"))

    return render_template("pages/register.html")


# ---------------------------------------------------------
#  ログイン
# ---------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email=?",
            (email,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["userID"]
            session["user_name"] = user["name"]
            session["user_icon"] = user["user_icon"] or DEFAULT_USER_ICON
            flash(f"{user['name']}さん、ログインしました。")
            return redirect(url_for("index"))

        flash("メールアドレスかパスワードが間違っています。")
        return redirect(url_for("login"))

    return render_template("pages/login.html")


# ---------------------------------------------------------
#  ログアウト
# ---------------------------------------------------------
@app.route("/logout")
def logout():
    session.clear()
    flash("ログアウトしました。")
    return redirect(url_for("index"))


# ---------------------------------------------------------
#  カートに追加
# ---------------------------------------------------------
@app.route("/cart/add/<int:pID>", methods=["POST"])
def add_to_cart(pID):
    user_id = session.get("user_id")
    if not user_id:
        flash("ログインが必要です。")
        return redirect(url_for("login"))

    try:
        quantity = int(request.form.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, quantity)

    conn = get_db()
    product = conn.execute("""
        SELECT pName, stock FROM products WHERE pID=?
    """, (pID,)).fetchone()
    if not product:
        conn.close()
        flash("商品が見つかりません。")
        return redirect(url_for("products"))

    stock = max(0, product["stock"])
    # カート投入時点で在庫を予約する（以降は carts 側数量が正）
    reserved_quantity = min(quantity, stock)

    if reserved_quantity <= 0:
        conn.close()
        flash(f"{product['pName']} は在庫切れです。")
        return redirect(url_for("cart"))

    existing = conn.execute("""
        SELECT * FROM carts WHERE userID=? AND pID=?
    """, (user_id, pID)).fetchone()

    if existing:
        conn.execute("""
            UPDATE carts SET quantity = quantity + ?
            WHERE cartID=?
        """, (reserved_quantity, existing["cartID"]))
    else:
        conn.execute("""
            INSERT INTO carts (userID, pID, quantity)
            VALUES (?, ?, ?)
        """, (user_id, pID, reserved_quantity))

    conn.execute("""
        UPDATE products
        SET stock = stock - ?
        WHERE pID = ?
    """, (reserved_quantity, pID))

    conn.commit()
    conn.close()

    if reserved_quantity < quantity:
        flash(f"{product['pName']} は在庫上限（{stock}個）まで追加しました。")
    else:
        flash("カートに追加しました。")
    return redirect(url_for("cart"))


# ---------------------------------------------------------
#  カートページ
# ---------------------------------------------------------
@app.route("/cart")
def cart():
    user_id = session.get("user_id")
    if not user_id:
        flash("ログインが必要です。")
        return redirect(url_for("login"))

    conn = get_db()
    items = conn.execute("""
        SELECT c.cartID, c.quantity, p.pName, p.price, p.image, p.stock,
               (p.stock + c.quantity) AS max_quantity
        FROM carts c
        JOIN products p ON c.pID = p.pID
        WHERE c.userID = ?
    """, (user_id,)).fetchall()
    conn.close()

    total = sum(item["price"] * item["quantity"] for item in items)

    return render_template("pages/cart.html",
                           items=items,
                           total=total)


# ---------------------------------------------------------
#  カート削除
# ---------------------------------------------------------
@app.route("/cart/delete/<int:cartID>", methods=["POST"])
def delete_cart_item(cartID):
    user_id = session.get("user_id")
    if not user_id:
        flash("ログインが必要です。")
        return redirect(url_for("login"))

    conn = get_db()
    cart_item = conn.execute("""
        SELECT pID, quantity FROM carts
        WHERE cartID=? AND userID=?
    """, (cartID, user_id)).fetchone()
    if cart_item:
        # カート削除時は予約分在庫を商品へ戻す
        conn.execute("""
            UPDATE products SET stock = stock + ?
            WHERE pID = ?
        """, (cart_item["quantity"], cart_item["pID"]))
        conn.execute("DELETE FROM carts WHERE cartID=?", (cartID,))
    conn.commit()
    conn.close()
    return redirect(url_for("cart"))


# ---------------------------------------------------------
#  数量変更
# ---------------------------------------------------------
@app.route("/cart/update/<int:cartID>", methods=["POST"])
def update_cart_item(cartID):
    user_id = session.get("user_id")
    if not user_id:
        flash("ログインが必要です。")
        return redirect(url_for("login"))

    try:
        quantity = int(request.form.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1

    conn = get_db()
    cart_item = conn.execute("""
        SELECT c.cartID, c.pID, c.quantity AS current_quantity, p.pName, p.stock
        FROM carts c
        JOIN products p ON c.pID = p.pID
        WHERE c.cartID=? AND c.userID=?
    """, (cartID, user_id)).fetchone()
    if not cart_item:
        conn.close()
        flash("対象のカート商品が見つかりません。")
        return redirect(url_for("cart"))

    current_quantity = cart_item["current_quantity"]

    if quantity <= 0:
        # 0 以下指定は削除扱い。予約在庫を全返却
        conn.execute("UPDATE products SET stock = stock + ? WHERE pID = ?",
                     (current_quantity, cart_item["pID"]))
        conn.execute("DELETE FROM carts WHERE cartID=?", (cartID,))
    else:
        desired_quantity = max(1, quantity)
        delta = desired_quantity - current_quantity

        if delta > 0:
            # 増量時は商品在庫の残数分だけ反映
            addable = min(delta, max(0, cart_item["stock"]))
            new_quantity = current_quantity + addable
            if addable > 0:
                conn.execute("UPDATE products SET stock = stock - ? WHERE pID = ?",
                             (addable, cart_item["pID"]))
            if new_quantity <= 0:
                conn.execute("DELETE FROM carts WHERE cartID=?", (cartID,))
            else:
                conn.execute("UPDATE carts SET quantity=? WHERE cartID=?",
                             (new_quantity, cartID))
            if addable < delta:
                flash(f"{cart_item['pName']} は在庫上限まで更新しました。")
        elif delta < 0:
            # 減量時は差分を商品在庫へ返却
            restored = -delta
            conn.execute("UPDATE products SET stock = stock + ? WHERE pID = ?",
                         (restored, cart_item["pID"]))
            conn.execute("UPDATE carts SET quantity=? WHERE cartID=?",
                         (desired_quantity, cartID))

    conn.commit()
    conn.close()
    return redirect(url_for("cart"))


# ---------------------------------------------------------
#  購入確認ページ
# ---------------------------------------------------------
@app.route("/checkout")
def checkout():
    user_id = session.get("user_id")
    if not user_id:
        flash("ログインしてください。")
        return redirect(url_for("login"))

    conn = get_db()
    items = conn.execute("""
        SELECT c.pID, c.quantity, p.pName, p.price, p.image, p.stock
        FROM carts c
        JOIN products p ON c.pID = p.pID
        WHERE c.userID = ?
    """, (user_id,)).fetchall()
    subtotal = sum(item["quantity"] * item["price"] for item in items)
    coupon_available = subtotal >= 2000

    user_coupon_row = conn.execute(
        "SELECT coupon_5_count, coupon_10_count FROM users WHERE userID = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    coupon_5_count = user_coupon_row["coupon_5_count"] if user_coupon_row else 0
    coupon_10_count = user_coupon_row["coupon_10_count"] if user_coupon_row else 0

    # セッションの選択中引き券をチェック（2,000 円以上かつ保有数ありで適用）
    discount = 0
    coupon = session.get("discount_coupon")
    if coupon_available and coupon == COUPON_10 and coupon_10_count > 0:
        discount = subtotal * 0.10
    elif coupon_available and coupon == COUPON_5 and coupon_5_count > 0:
        discount = subtotal * 0.05
    else:
        coupon = None

    total_after_discount = subtotal - discount

    return render_template(
        "pages/checkout.html",
        items=items,
        subtotal=subtotal,
        total=total_after_discount,
        discount=discount,
        coupon=coupon,
        coupon_available=coupon_available,
        coupon_5_count=coupon_5_count,
        coupon_10_count=coupon_10_count,
    )

@app.route("/checkout/select_coupon", methods=["POST"])
def checkout_select_coupon():
    user_id = session.get("user_id")
    if not user_id:
        flash("ログインしてください。")
        return redirect(url_for("login"))

    selected_coupon = request.form.get("coupon", "")
    if selected_coupon not in ("", COUPON_5, COUPON_10):
        flash("引き券の選択が不正です。")
        return redirect(url_for("checkout"))

    conn = get_db()
    cart_items = conn.execute("""
        SELECT c.quantity, p.price
        FROM carts c
        JOIN products p ON c.pID = p.pID
        WHERE c.userID = ?
    """, (user_id,)).fetchall()
    coupon_row = conn.execute(
        "SELECT coupon_5_count, coupon_10_count FROM users WHERE userID = ?",
        (user_id,)
    ).fetchone()
    conn.close()

    subtotal = sum(item["quantity"] * item["price"] for item in cart_items)
    # 適用条件: 最低購入金額、かつ選択券の保有数
    if selected_coupon and subtotal < 2000:
        flash("引き券は購入金額が2,000円以上のときに使用できます。")
        session.pop("discount_coupon", None)
        return redirect(url_for("checkout"))

    if selected_coupon == COUPON_10 and (not coupon_row or coupon_row["coupon_10_count"] <= 0):
        flash("10%引き券を所持していません。")
        session.pop("discount_coupon", None)
        return redirect(url_for("checkout"))

    if selected_coupon == COUPON_5 and (not coupon_row or coupon_row["coupon_5_count"] <= 0):
        flash("5%引き券を所持していません。")
        session.pop("discount_coupon", None)
        return redirect(url_for("checkout"))

    if selected_coupon:
        session["discount_coupon"] = selected_coupon
    else:
        session.pop("discount_coupon", None)
    return redirect(url_for("checkout"))


# ---------------------------------------------------------
#  配送について / 返金について / お問い合わせ
#  ※URLが /templates/pages/... になっていたので、普通のルートに修正
# ---------------------------------------------------------
@app.route("/information/about_delivery")
def about_delivery():
    return render_template("pages/information/about_delivery.html")

@app.route("/information/refund")
def refund():
    return render_template("pages/information/refund.html")

@app.route("/information/info")
def info():
    return render_template("pages/information/info.html")

@app.route("/information/privacy_policy")
def privacy_policy():
    return render_template("pages/information/privacy_policy.html")

@app.route("/information/terms_of_service")
def terms_of_service():
    return render_template("pages/information/terms_of_service.html")

@app.route("/information/site_overview")
def site_overview():
    return render_template("pages/information/site_overview.html")


# ---------------------------------------------------------
#  マイページ
# ---------------------------------------------------------
@app.route("/mypage")
def mypage():
    user_id = session.get("user_id")
    if not user_id:
        flash("ログインが必要です。")
        return redirect(url_for("login"))

    conn = get_db()
    user = conn.execute(
        """
        SELECT
            userID,
            name,
            phone,
            email,
            DATE(created_at) AS created_date,
            user_icon,
            gacha_count,
            coupon_5_count,
            coupon_10_count
        FROM users
        WHERE userID = ?
        """,
        (user_id,)
    ).fetchone()
    order_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM orders WHERE userID = ?",
        (user_id,)
    ).fetchone()["cnt"]
    order_history = conn.execute(
        """
        SELECT
            o.orderID,
            DATE(o.created_at) AS ordered_date,
            o.total,
            COALESCE(SUM(oi.quantity), 0) AS item_count
        FROM orders o
        LEFT JOIN order_items oi ON oi.orderID = o.orderID
        WHERE o.userID = ?
        GROUP BY o.orderID
        ORDER BY o.created_at DESC
        """,
        (user_id,)
    ).fetchall()
    conn.close()

    return render_template(
        "pages/mypage.html",
        user=user,
        order_count=order_count,
        order_history=order_history,
    )

@app.route("/mypage/icons", methods=["GET", "POST"])
def mypage_icons():
    user_id = session.get("user_id")
    if not user_id:
        flash("ログインが必要です。")
        return redirect(url_for("login"))

    icon_choices = [
        "user-icons/user-icon1.webp",
        "user-icons/user-icon2.webp",
        "user-icons/user-icon3.webp",
        "user-icons/user-icon4.webp",
        "user-icons/user-icon5.webp",
        "user-icons/user-icon6.webp",
    ]

    conn = get_db()
    if request.method == "POST":
        selected_icon = request.form.get("user_icon")
        if selected_icon not in icon_choices:
            flash("アイコンを選択してください。")
            conn.close()
            return redirect(url_for("mypage_icons"))

        conn.execute(
            "UPDATE users SET user_icon = ? WHERE userID = ?",
            (selected_icon, user_id)
        )
        conn.commit()
        session["user_icon"] = selected_icon
        conn.close()
        flash("アイコンを更新しました。")
        return redirect(url_for("mypage"))

    user = conn.execute(
        "SELECT userID, name, user_icon FROM users WHERE userID = ?",
        (user_id,)
    ).fetchone()
    conn.close()

    return render_template(
        "pages/mypage_icons.html",
        user=user,
        icon_choices=icon_choices,
    )


# ---------------------------------------------------------
#  購入確定（注文登録）
# ---------------------------------------------------------
@app.route("/checkout/confirm", methods=["POST"])
def checkout_confirm():
    user_id = session.get("user_id")
    if not user_id:
        flash("ログインしてください。")
        return redirect(url_for("login"))

    conn = get_db()

    cart_items = conn.execute("""
        SELECT c.pID, c.quantity, p.price, p.pName, p.stock
        FROM carts c
        JOIN products p ON c.pID = p.pID
        WHERE c.userID = ?
    """, (user_id,)).fetchall()

    if not cart_items:
        flash("カートに商品が入っていません。")
        conn.close()
        return redirect(url_for("cart"))

    # 引き券確認（2,000 円以上で所持券がある場合のみ）
    # 在庫はカート投入時に予約済みのため、ここではクーポン反映と注文確定が中心
    discount_coupon = session.get("discount_coupon")
    subtotal = sum(item["quantity"] * item["price"] for item in cart_items)
    total = subtotal
    used_coupon = None

    coupon_row = conn.execute(
        "SELECT coupon_5_count, coupon_10_count FROM users WHERE userID = ?",
        (user_id,)
    ).fetchone()
    if subtotal >= 2000:
        if discount_coupon == COUPON_10 and coupon_row and coupon_row["coupon_10_count"] > 0:
            total = int(subtotal * 0.9)
            used_coupon = COUPON_10
        elif discount_coupon == COUPON_5 and coupon_row and coupon_row["coupon_5_count"] > 0:
            total = int(subtotal * 0.95)
            used_coupon = COUPON_5

    if used_coupon == COUPON_10:
        # 利用確定した券だけ消費する
        conn.execute(
            "UPDATE users SET coupon_10_count = coupon_10_count - 1 WHERE userID = ?",
            (user_id,)
        )
    elif used_coupon == COUPON_5:
        conn.execute(
            "UPDATE users SET coupon_5_count = coupon_5_count - 1 WHERE userID = ?",
            (user_id,)
        )

    if total < 0:
        total = 0

    # ===== 購入金額 3,000 円ごとに わくわく券を付与 =====
    gacha_reward = total // 3000
    if gacha_reward > 0:
        conn.execute(
            "UPDATE users SET gacha_count = gacha_count + ? WHERE userID = ?",
            (gacha_reward, user_id)
        )

    # 使った引き券選択をクリア
    session.pop("discount_coupon", None)

    # ===== 注文登録 =====
    cursor = conn.execute("""
        INSERT INTO orders (userID, total)
        VALUES (?, ?)
    """, (user_id, total))
    order_id = cursor.lastrowid

    # ===== 注文明細登録 =====
    # 価格は購入時点の単価を保存し、商品マスタの後続更新の影響を受けないようにする
    for item in cart_items:
        conn.execute(
            "INSERT INTO order_items (orderID, pID, quantity, price) VALUES (?, ?, ?, ?)",
            (order_id, item["pID"], item["quantity"], item["price"])
        )

    # カート削除
    conn.execute("DELETE FROM carts WHERE userID = ?", (user_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("order_complete", order_id=order_id, total=total))


# ---------------------------------------------------------
#  注文完了ページ
# ---------------------------------------------------------
@app.route("/order/complete/<int:order_id>")
def order_complete(order_id):
    total = request.args.get("total")
    return render_template("pages/order_complete.html",
                           order_id=order_id,
                           total=total)

# ---------------------------------------------------------
#  管理：商品一覧
# ---------------------------------------------------------
@app.route("/admin/stock", methods=["GET", "POST"])
def admin_stock():
    conn = get_db()

    # 在庫更新処理
    if request.method == "POST":
        pID = request.form.get("pID")
        stock = request.form.get("stock")

        if pID is not None and stock is not None:
            conn.execute(
                "UPDATE products SET stock = ? WHERE pID = ?",
                (int(stock), int(pID))
            )
            conn.commit()

    # 商品一覧取得
    products = conn.execute("""
        SELECT pID, pName, price, stock
        FROM products
        ORDER BY pID
    """).fetchall()

    conn.close()
    return render_template("pages/admin_stock.html", products=products)



# ---------------------------------------------------------
#  管理：商品追加
# ---------------------------------------------------------
def allowed_file(filename):
    # 拡張子ベースの簡易判定（厳密な MIME 検証は未実装）
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_product_image(image_file):
    filename = secure_filename(image_file.filename)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    root, ext = os.path.splitext(filename)
    candidate = filename
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], candidate)
    counter = 1
    # 同名ファイル衝突を回避（foo.webp -> foo_1.webp ...）
    while os.path.exists(save_path):
        candidate = f"{root}_{counter}{ext}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], candidate)
        counter += 1

    image_file.save(save_path)
    return candidate


@app.route("/products/add", methods=["GET", "POST"])
def add_product():
    conn = get_db()
    if request.method == "POST":
        tagID = request.form.get("tagID")
        pName = request.form["pName"]
        price = request.form["price"]
        pDescription = request.form.get("pDescription", "")
        pDescription = pDescription.replace("\r\n", "\n").replace("/n", "\n").replace("\\n", "\n")
        country = request.form["country"]

        image_file = request.files.get("image")
        if image_file and image_file.filename:
            if not allowed_file(image_file.filename):
                conn.close()
                return "画像形式は jpg / jpeg / png / webp のみ対応です。", 400
            filename = save_uploaded_product_image(image_file)
        else:
            filename = None

        conn.execute("""
            INSERT INTO products (tagID, pName, price, pDescription, country, image)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (tagID, pName, price, pDescription, country, filename))

        conn.commit()
        conn.close()
        return redirect(url_for("add_product"))

    tags = conn.execute("SELECT * FROM tags").fetchall()
    conn.close()

    return render_template("pages/add_product.html", tags=tags)


# ---------------------------------------------------------
#  管理：商品編集
# ---------------------------------------------------------
@app.route("/products/edit/<int:pID>", methods=["GET", "POST"])
def edit_product(pID):
    conn = get_db()
    product_row = conn.execute(
        "SELECT * FROM products WHERE pID=?",
        (pID,)
    ).fetchone()

    if request.method == "POST":
        tagID = request.form["tagID"]
        pName = request.form["pName"]
        price = request.form["price"]
        pDescription = request.form.get("pDescription", "")
        pDescription = pDescription.replace("\r\n", "\n").replace("/n", "\n").replace("\\n", "\n")
        country = request.form["country"]
        image = product_row["image"] if product_row else None
        image_file = request.files.get("image_file")
        if image_file and image_file.filename:
            if not allowed_file(image_file.filename):
                conn.close()
                return "画像形式は jpg / jpeg / png / webp のみ対応です。", 400
            image = save_uploaded_product_image(image_file)

        conn.execute("""
            UPDATE products
            SET tagID=?, pName=?, price=?, pDescription=?, country=?, image=?
            WHERE pID=?
        """, (tagID, pName, price, pDescription, country, image, pID))

        conn.commit()
        conn.close()
        return redirect(url_for("product_list"))

    tags = conn.execute("SELECT * FROM tags").fetchall()
    conn.close()

    return render_template("pages/edit_product.html",
                           product=product_row,
                           tags=tags)


# ---------------------------------------------------------
#  管理：商品削除
# ---------------------------------------------------------
@app.route("/products/delete/<int:pID>", methods=["POST"])
def delete_product(pID):
    conn = get_db()
    row = conn.execute(
        "SELECT image FROM products WHERE pID=?",
        (pID,)
    ).fetchone()

    conn.execute("DELETE FROM products WHERE pID=?", (pID,))

    image_filename = row["image"] if row else None
    if image_filename:
        in_use_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM products WHERE image=?",
            (image_filename,)
        ).fetchone()["cnt"]
        if in_use_count == 0:
            # 他商品で参照されなくなった画像だけ物理削除
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
            if os.path.isfile(image_path):
                os.remove(image_path)

    conn.commit()
    conn.close()
    return redirect(url_for("admin_stock"))

# ---------------------------------------------------------
#  検索API
# ---------------------------------------------------------
@app.route("/search")
def search_page():
    # サーバーサイド検索（初期表示時は結果なし）
    q = request.args.get("q", "").strip()

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM products WHERE pName LIKE ?",
        (f"%{q}%",)
    ).fetchall() if q else []
    conn.close()

    return render_template("pages/search.html", q=q, results=rows)


@app.route("/api/search")
def search():
    # オートコンプリート用 API（軽量レスポンス）
    keyword = request.args.get("keyword", "").strip()
    print("keyword:", keyword)

    conn = get_db()
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT pName, price FROM products WHERE pName LIKE ?",
        (f"%{keyword}%",)
    ).fetchall()

    conn.close()
    print("rows:", rows)

    return jsonify([
        {"name": row["pName"], "price": row["price"]}
        for row in rows
    ])


# ミニゲーム入口
@app.route("/game")
def game():
    return render_template("pages/game.html")

# じゃんけん
@app.route("/janken")
def janken():
    return render_template("pages/game-janken.html")


# =========================================================
#  アプリ起動
# =========================================================
if __name__ == "__main__":
    app.run(debug=True)
