from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route("/")
def index():
    return jsonify({
        "message": "Backend is running",
        "version": os.getenv("APP_VERSION", "1.0.0"),
        "gitops": "powered by ArgoCD + GitHub Actions"
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/items")
def items():
    return jsonify({"items": ["itemv1", "item2", "item3"]})  # Change "item1" to "itemv1" to reflect the new version

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
