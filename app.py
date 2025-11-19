# app.py
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from datetime import datetime, timedelta
from collections import deque, defaultdict
import time
import html

app = Flask(__name__)
CORS(app)  # In production, restrict origins: CORS(app, origins=["https://www.kellinnovations.com"])

# -----------------------
# In-memory storage (Option B)
# -----------------------
# posts: list of dicts: {id, title, name, content, created_at}
posts = []
next_id = 1

# -----------------------
# Simple rate limiting per IP
# -----------------------
# allow up to 5 posts per hour per IP
RATE_LIMIT_COUNT = 5
RATE_LIMIT_WINDOW = 3600  # seconds

ip_timestamps = defaultdict(lambda: deque())  # ip -> deque of post timestamps


# -----------------------
# Simple spam checks
# -----------------------
MAX_TITLE_LEN = 200
MAX_NAME_LEN = 100
MAX_CONTENT_LEN = 5000

def sanitize_text(s: str) -> str:
    # Keep raw text but escape when rendering. Here we still strip bizarrely long whitespace
    return s.strip()

def is_spam(title, name, content):
    # Basic tests: length, repetition, suspicious tokens
    if len(title) > MAX_TITLE_LEN or len(name) > MAX_NAME_LEN or len(content) > MAX_CONTENT_LEN:
        return True
    # reject if content contains <script> etc (we also escape on frontend)
    lowered = (title + " " + content).lower()
    if "<script" in lowered or "javascript:" in lowered:
        return True
    # reject too many repeated characters (aaaaaaaa)
    if any(segment * 10 in content for segment in ["a", "e", "i", "o", "u", " "]):
        # rudimentary; don't be too strict
        pass
    return False

def check_rate_limit(ip):
    now = time.time()
    dq = ip_timestamps[ip]
    # prune old timestamps
    while dq and dq[0] <= now - RATE_LIMIT_WINDOW:
        dq.popleft()
    if len(dq) >= RATE_LIMIT_COUNT:
        return False, RATE_LIMIT_COUNT - len(dq)
    return True, RATE_LIMIT_COUNT - len(dq)

def record_post_ip(ip):
    ip_timestamps[ip].append(time.time())


# -----------------------
# Routes
# -----------------------
@app.route("/api/posts", methods=["GET"])
def list_posts():
    # return posts newest first
    out = list(reversed(posts))
    return jsonify(out), 200

@app.route("/api/posts", methods=["POST"])
def create_post():
    global next_id
    data = request.get_json() or {}
    title = sanitize_text(data.get("title", ""))
    name = sanitize_text(data.get("name", "")) or "Anonymous"
    content = sanitize_text(data.get("content", ""))

    # basic validation
    if not title or not content:
        return jsonify({"error": "Title and content are required."}), 400

    if is_spam(title, name, content):
        return jsonify({"error": "Rejected — failed basic content checks."}), 400

    # rate limiting by IP
    ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
    ok, remaining = check_rate_limit(ip)
    if not ok:
        return jsonify({"error": "Rate limit exceeded. Try again later."}), 429

    # create post
    created_at = datetime.utcnow().isoformat() + "Z"
    post = {
        "id": next_id,
        "title": title,
        "name": name,
        "content": content,
        "created_at": created_at,
    }
    next_id += 1
    posts.append(post)
    record_post_ip(ip)
    return jsonify(post), 201

# (Optional) lightweight index so visiting the app shows a small message
@app.route("/", methods=["GET"])
def index():
    return (
        "<h3>Render Blog API (in-memory)</h3>"
        "<p>Endpoints: GET /api/posts, POST /api/posts</p>"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=False)
