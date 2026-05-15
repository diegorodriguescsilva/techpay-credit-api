import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/v1/credit-check")
def credit_check():
    api_key = os.environ.get("CREDIT_API_KEY", "NOT_FOUND")
    return jsonify({
        "service": "credit-api",
        "status": "active",
        "vault_access": True if api_key != "NOT_FOUND" else False,
        "revision_tag": os.environ.get("REVISION_TAG", "raw")
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))