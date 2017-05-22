from flask import Flask
from views import views, csrf
import os


def create_app():
    app = Flask(__name__)
    app.register_blueprint(views)
    csrf.init_app(app)
    app.secret_key = os.getenv('SECRET_KEY')

    return app

# Exposing so can be picked up by Zappa
app = create_app()

if __name__ == "__main__":
    import sys
    app = create_app()
    try:
        port = int(sys.argv[1])
    except (IndexError, ValueError):
        port = 5000
    app.run(debug=True, port=port)
