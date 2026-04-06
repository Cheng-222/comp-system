from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache


db = SQLAlchemy()
cors = CORS()
cache = Cache()
