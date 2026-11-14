"""Database tables. Works with SQLite locally and PostgreSQL in production.

Three tables:
  games    one row per room (code, which question we are on, when it ends)
  players  one row per person who joined, with their running score
  answers  one row per player per question (a player can answer only once)

Tokens are stored as SHA-256 hashes, so even someone who reads the database
cannot use them to take over a host or player session.
"""

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

import config


class Base(DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    host_token_hash: Mapped[str] = mapped_column(String(64))
    # lobby -> question -> reveal -> question -> ... -> finished
    phase: Mapped[str] = mapped_column(String(16), default="lobby")
    question_index: Mapped[int] = mapped_column(Integer, default=-1)
    question_started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    question_ends_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[float] = mapped_column(Float)


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (UniqueConstraint("game_code", "name_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_code: Mapped[str] = mapped_column(ForeignKey("games.code"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    name_key: Mapped[str] = mapped_column(String(40))  # lower-case, for duplicate checks
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    joined_at: Mapped[float] = mapped_column(Float)


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("player_id", "question_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    game_code: Mapped[str] = mapped_column(ForeignKey("games.code"), index=True)
    question_index: Mapped[int] = mapped_column(Integer)
    choice: Mapped[int] = mapped_column(Integer)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    points: Mapped[int] = mapped_column(Integer)
    answered_at: Mapped[float] = mapped_column(Float)


_connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(engine)
