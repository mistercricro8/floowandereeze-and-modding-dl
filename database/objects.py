"""
Database configuration and session management.
This module sets up SQLAlchemy with SQLite database and provides a global session
object.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from util.paths import get_database_path

base = declarative_base()
engine = create_engine(f"sqlite:///{get_database_path()}")
DBsession = sessionmaker(bind=engine, autoflush=False)
session = DBsession()
