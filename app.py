from flask import Flask, render_template, request, redirect, Response, session
import sqlite3, os, base64
from datetime import datetime
import cv2
import face_recognition
import numpy as np

app = Flask(__name__)
app.secret_key = "face-attendance-secret"   # 🔐 REQUIRED FOR SESSION

DB = "database.db"
KNOWN = "known_faces"

# 🔐 ADMIN CREDENTIALS
ADMIN_USER = "admin"
ADMIN_PASS = "1234"

# ---------- DATABASE ----------
def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS students(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll TEXT,
        name TEXT,
        image TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS attendance(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        date TEXT,
        time TEXT
    )
    """)
    conn.commit()
    conn.close()

# ---------- ROUTES ----------
@app.route("/")
def index():
    return render_template("index.html")

# 🔐 ADMIN LOGIN
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        user = request.form["username"]
        pwd = request.form["password"]

        if user == ADMIN_USER and pwd == ADMIN_PASS:
            session["admin"] = True
            return redirect("/register")
        else:
            return render_template("admin_login.html", error="Invalid login")

    return render_template("admin_login.html")

# 🔒 REGISTER LOCKED
@app.route("/register")
def register():
    if not session.get("admin"):
        return redirect("/admin_login")
    return render_template("register.html")

@app.route("/recognize")
def recognize():
    return render_template("recognize.html")

@app.route("/attendance")
def attendance():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT students.name, students.roll, attendance.date, attendance.time
        FROM attendance
        JOIN students ON students.id = attendance.student_id
        ORDER BY attendance.id DESC
    """)
    data = cur.fetchall()
    conn.close()
    return render_template("attendance.html", data=data)

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect("/")

# ---------- RESET ATTENDANCE ----------
@app.route("/reset_attendance", methods=["POST"])
def reset_attendance():
    if not session.get("admin"):
        return "Unauthorized", 403

    pwd = request.form.get("password")

    if pwd != ADMIN_PASS:
        return "Wrong Password", 401

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM attendance")
    conn.commit()
    conn.close()

    return redirect("/attendance")
ADMIN_PASS = "1234"


# ---------- SAVE STUDENT ----------
@app.route("/save_student", methods=["POST"])
def save_student():
    if not session.get("admin"):
        return redirect("/admin_login")

    roll = request.form["roll"]
    name = request.form["name"]
    image_data = request.form["image_data"].split(",")[1]

    img_bytes = base64.b64decode(image_data)
    filename = f"{roll}_{name}.jpg"
    path = os.path.join(KNOWN, filename)

    with open(path, "wb") as f:
        f.write(img_bytes)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO students (roll, name, image) VALUES (?,?,?)",
        (roll, name, path)
    )
    conn.commit()
    conn.close()

    return redirect("/")

# ---------- FACE RECOGNITION ----------
def gen_frames():
    known_enc = []
    known_ids = []

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, image FROM students")
    students = cur.fetchall()
    conn.close()

    for sid, img_path in students:
        if not os.path.exists(img_path):
            continue

        try:
            img = face_recognition.load_image_file(img_path)
            encs = face_recognition.face_encodings(img)

            if len(encs) == 0:
                continue

            known_enc.append(encs[0])
            known_ids.append(sid)

        except:
            continue

    cap = cv2.VideoCapture(0)
    marked = set()

    while True:
        success, frame = cap.read()
        if not success:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        locs = face_recognition.face_locations(rgb)
        encs = face_recognition.face_encodings(rgb, locs)

        for enc, loc in zip(encs, locs):
            if len(known_enc) == 0:
                continue

            matches = face_recognition.compare_faces(known_enc, enc)
            if True in matches:
                idx = matches.index(True)
                sid = known_ids[idx]

                if sid not in marked:
                    now = datetime.now()
                    conn = sqlite3.connect(DB)
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO attendance (student_id, date, time) VALUES (?,?,?)",
                        (sid, now.date(), now.strftime("%H:%M:%S"))
                    )
                    conn.commit()
                    conn.close()
                    marked.add(sid)

                top, right, bottom, left = loc
                cv2.rectangle(frame, (left, top), (right, bottom), (0,255,0), 2)

        ret, buffer = cv2.imencode(".jpg", frame)
        frame = buffer.tobytes()

        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")

@app.route("/video_feed")
def video_feed():
    return Response(gen_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame")
    import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# ---------- MAIN ----------
if __name__ == "__main__":
    init_db()
    if not os.path.exists(KNOWN):
        os.mkdir(KNOWN)
    app.run(debug=True)
