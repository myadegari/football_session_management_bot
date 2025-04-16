from src.repositories.database import engine, Base
from src.repositories import models

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("All tables created successfully.")