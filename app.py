from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
from collections import deque, defaultdict
import time
import json
import os

app = Flask(__name__)
# Allow Squarespace domain for CORS
CORS(app, origins=["https://kellinnovations.com"])

# -----------------------
# Persistent storage
# -----------------------
POSTS_FILE = "posts.json"

if os.path.exists(POSTS_FILE):
    with open(POSTS_FILE, "r") as f:
        posts = json.load(f)
else:
    posts = []

next_id = max([p["id"] for p in posts], default=0) + 1

def save_posts():
    with open(POSTS_FILE, "w") as f:
        json.dump(posts, f)

# -----------------------
# Rate limiting
# -----------------------
RATE_LIMIT_COUNT = 5
RATE_LIMIT_WINDOW = 3600  # seconds
ip_timestamps = defaultdict(lambda: deque())

def check_rate_limit(ip):
    now = time.time()
    dq = ip_timestamps[ip]
    # prune old timestamps
    while dq and dq[0] <= now - RATE_LIMIT_WINDOW:
        dq.popleft()
    if len(dq) >= RATE_LIMIT_COUNT:
        return False
    return True

def record_post_ip(ip):
    ip_timestamps[ip].append(time.time())

# -----------------------
# Spam / length checks
# -----------------------
MAX_TITLE_LEN = 200
MAX_NAME_LEN = 100
MAX_CONTENT_LEN = 5000

def sanitize_text(s: str) -> str:
    return s.strip()

def is_spam(title, name, content):
    if len(title) > MAX_TITLE_LEN or len(name) > MAX_NAME_LEN or len(content) > MAX_CONTENT_LEN:
        return True
    lowered = (title + " " + content).lower()
    if "<script" in lowered or "javascript:" in lowered:
        return True
    return False

# -----------------------
# Admin key for deletion
# -----------------------
ADMIN_KEY = "beastydog8"  # replace with a secure key

# -----------------------
# Routes
# -----------------------
@app.route("/api/posts", methods=["GET"])
def list_posts():
    return jsonify(list(reversed(posts))), 200

@app.route("/api/posts", methods=["POST"])
def create_post():
    global next_id
    data = request.get_json() or {}
    title = sanitize_text(data.get("title", ""))
    name = sanitize_text(data.get("name", "")) or "Anonymous"
    content = sanitize_text(data.get("content", ""))

    if not title or not content:
        return jsonify({"error": "Title and content are required."}), 400

    if is_spam(title, name, content):
        return jsonify({"error": "Rejected — failed basic content checks."}), 400

    ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
    if not check_rate_limit(ip):
        return jsonify({"error": "Rate limit exceeded. Try again later."}), 429

    created_at = datetime.utcnow().isoformat() + "Z"
    post = {"id": next_id, "title": title, "name": name, "content": content, "created_at": created_at}
    next_id += 1
    posts.append(post)
    record_post_ip(ip)
    save_posts()
    return jsonify(post), 201

@app.route("/api/posts/<int:post_id>", methods=["DELETE"])
def delete_post(post_id):
    key = request.headers.get("X-Admin-Key")
    if key != ADMIN_KEY:
        return jsonify({"error": "Unauthorized"}), 403
    global posts
    posts = [p for p in posts if p["id"] != post_id]
    save_posts()
    return jsonify({"status": "deleted"}), 200

@app.route("/", methods=["GET"])
def index():
    return (
        "<h3>Render Blog API (persistent)</h3>"
        "<p>Endpoints: GET /api/posts, POST /api/posts, DELETE /api/posts/&lt;id&gt;</p>"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=False)
