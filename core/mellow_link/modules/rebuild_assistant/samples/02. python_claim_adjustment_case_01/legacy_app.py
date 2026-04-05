from flask import Flask, request, render_template_string
import sqlite3

app = Flask(__name__)

PAGE = """
<html>
<body>
    <h1>Claim Adjustment</h1>
    {% if error %}<p style="color:red">{{ error }}</p>{% endif %}
    <p>claim_id={{ claim["claim_id"] }}</p>
    <p>status={{ claim["status"] }}</p>
    <p>amount={{ claim["claim_amount"] }}</p>
    <p>branch={{ claim["branch_code"] }}</p>
    {% if claim["status"] == "REVIEW" and user_role in ["BRANCH_MANAGER", "HQ_REVIEWER"] %}
        <button>승인 가능</button>
    {% endif %}
    {% if claim["is_urgent"] == "Y" %}
        <p>긴급건: 4시간 내 처리 대상</p>
    {% endif %}
</body>
</html>
"""


def get_conn():
    return sqlite3.connect("claims.db")


@app.route("/claim/adjust")
def adjust_claim():
    claim_id = request.args.get("claim_id")
    user_role = request.args.get("user_role", "")
    dept_code = request.args.get("dept_code", "")

    conn = get_conn()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT claim_id, status, claim_amount, branch_code, is_urgent, accident_type
        FROM insurance_claim
        WHERE claim_id = ?
        """,
        (claim_id,),
    ).fetchone()
    conn.close()

    if not row:
        return render_template_string(PAGE, error="청구건 없음", claim={}, user_role=user_role)

    claim = dict(row)

    if claim["status"] in ["CLOSED", "CANCELLED"]:
        return render_template_string(PAGE, error="마감 또는 취소 건은 조정 불가", claim=claim, user_role=user_role)

    if claim["accident_type"] == "FRAUD" and user_role != "HQ_REVIEWER":
        return render_template_string(PAGE, error="특수 사고건은 본사 심사만 가능", claim=claim, user_role=user_role)

    if claim["claim_amount"] >= 3000000 and user_role == "BRANCH_MANAGER":
        return render_template_string(PAGE, error="지점장 한도 초과", claim=claim, user_role=user_role)

    if claim["claim_amount"] >= 10000000 and dept_code != "CLAIM_AUDIT":
        return render_template_string(PAGE, error="고액 청구는 심사전담부서만 조정 가능", claim=claim, user_role=user_role)

    if claim["branch_code"] == "B99" and claim["is_urgent"] == "Y" and user_role == "BRANCH_MANAGER":
        return render_template_string(PAGE, error="특수지점 긴급건은 본사 선승인 필요", claim=claim, user_role=user_role)

    return render_template_string(PAGE, claim=claim, error="", user_role=user_role)


if __name__ == "__main__":
    app.run(debug=True)
