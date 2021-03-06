from flask import Blueprint, request, jsonify
import bcrypt

from models.user import User
from models.auth import Auth
from models import db
from sp_token.tokens import create_token, revoke_token
from sp_token import get_user_from_token
from api.name import get_rand_name
from api.user import update_user_info
from api.account import Account

auth_api = Blueprint("Auth", __name__)


@auth_api.route("/api/v1/login", methods=["POST"])
def login():
    payload = request.get_json()
    email = payload["email"]
    password = payload["password"]

    # Allow user to use user id to login, but it's not exposed
    # in the UI for simplicity
    if email.isdigit():
        user = User.query.filter(User.id == email).first()
    else:
        user = User.query.filter(User.email == email).first()

    if not user:
        return jsonify({"error": "用户不存在"}), 400

    auth = Auth.query.filter_by(user_id=user.id).first()
    if not auth:
        # some really really old legacy user maybe
        # shouldn't happen
        return jsonify({"error": "账号不存在"}), 400

    correct_pwd = auth.password
    try:
        # Mysql db return string type
        correct_pwd = correct_pwd.encode("utf8")
    except:
        # sqlite return byte type
        print('password is byte type already for sqlite')

    if bcrypt.checkpw(password.encode("utf8"), correct_pwd):
        # password is correct
        # check if banned or not before letting in

        if user.is_banned():
            return jsonify({"error": "封禁中"}), 403

        user_dict = user.to_dict(return_email=True)

        token = create_token(user_dict)
        account_data = Account(token, user_dict).to_dict()
        return jsonify(account_data)
    else:
        return jsonify({"error": "密码错误"}), 401


@auth_api.route("/api/v1/account", methods=["GET"])
@get_user_from_token(required=True)
def get_account_data(user=None):
    """
    Not currently used, could use it when we want to get latest
    user data of himself.
    """
    token = request.headers.get("token")
    account_data = Account(token, user).to_dict()
    return jsonify(account_data)


@auth_api.route("/api/v1/change_password", methods=["POST"])
@get_user_from_token(required=True)
def change_password(user=None):
    payload = request.get_json()
    new_password = payload["password"]
    new_hash = bcrypt.hashpw(new_password.encode("utf8"), bcrypt.gensalt(10))
    Auth.query.filter_by(user_id=user['id']).update(
        {"password": new_hash})
    db.session.commit()
    return "success"


@auth_api.route("/api/v1/register", methods=["POST"])
def register():

    email = request.form.get("email")

    existing_user = User.query.filter(User.email == email).first()
    if existing_user:
        return jsonify({"error": "邮箱已经注册"}), 409

    password = request.form.get("password")
    password_hash = bcrypt.hashpw(password.encode("utf8"), bcrypt.gensalt(10))

    user = User()
    db.session.add(user)
    db.session.commit()

    auth = Auth(user_id=user.id, password=password_hash)
    db.session.add(auth)
    db.session.commit()

    update_user_info(user)

    user_dict = user.to_dict(return_email=True)
    # TODO: sometimes create token failed due to connection
    # to redis, but user is already created, still return 200 OK
    # to client in this case
    token = create_token(user_dict)
    account_data = Account(token, user_dict).to_dict()
    return jsonify(account_data)


@auth_api.route("/api/v1/logout", methods=["POST"])
@get_user_from_token(required=True)
def logout(user=None):
    revoke_token(request.headers.get("token"))
    return "success"
