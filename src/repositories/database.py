from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

URL_DATABASE = "mysql+pymysql://{username}:{password}@{host}:{port}/{db_name}".format(
    username='admin',
    password='admin',
    host='localhost',
    port='3306',
    db_name='laruni_db'
)
engine = create_engine(URL_DATABASE)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()