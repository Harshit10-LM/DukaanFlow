from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from .config import Config
from .repository import Repository

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
csrf = CSRFProtect()

def create_app(config_override=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_override: app.config.update(config_override)
    if app.config['ENVIRONMENT'] == 'production' and (not app.config['SECRET_KEY'] or not app.config['MONGODB_URI']):
        raise RuntimeError('SECRET_KEY and MONGODB_URI are required in production.')
    if not app.config['SECRET_KEY']:
        app.config['SECRET_KEY'] = 'local-demo-only-change-me'
    app.extensions['repo'] = Repository(app.config)
    login_manager.init_app(app); csrf.init_app(app)
    from .models import User
    @login_manager.user_loader
    def load_user(user_id): return User(app.extensions['repo'].get_user(user_id))
    from .views import auth, dashboard, products, orders, integrations
    app.register_blueprint(auth); app.register_blueprint(dashboard); app.register_blueprint(products); app.register_blueprint(orders); app.register_blueprint(integrations)
    @app.get('/health')
    def health(): return {'status':'ok','database':app.extensions['repo'].status}, 200
    return app
