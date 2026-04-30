from flask import Flask, send_from_directory, make_response
from routes.auth_routes import auth_bp
from routes.contract_routes import contract_bp
from db import init_db, check_expiry_and_notify
from db import cleanup_old_contracts

def create_app():
    app = Flask(__name__)
    
    #  Secret Key
    app.secret_key = "supersecretkey"

    #  Initialize DB
    init_db()

    #  Expiry Check
    check_expiry_and_notify()


#  CLEANUP OLD CONTRACTS
    cleanup_old_contracts()

    # 📌 Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(contract_bp)

    #  FILE SERVING (FINAL FIX)
    @app.route('/uploads/<path:filename>')
    def download_file(filename):
        #  Normalize path
        filename = filename.replace("uploads/", "").replace("\\", "/")

        response = make_response(send_from_directory('uploads', filename))
        response.headers["Content-Disposition"] = "inline"
        return response

    return app   #  VERY IMPORTANT


#  RUN APP
if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)