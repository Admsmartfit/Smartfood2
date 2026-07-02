"""seed_admin.py — Cria o primeiro usuário ADMIN. Execute uma vez após ativar a Etapa A."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal
import models
models.Base.metadata.create_all(bind=__import__('database').engine)

import bcrypt as _bcrypt

def seed_admin():
    db = SessionLocal()
    try:
        admin = db.query(models.User).filter_by(email="admin@smartfood.com").first()
        if admin:
            print("Admin já existe: admin@smartfood.com")
            return
        senha_hash = _bcrypt.hashpw("smartfood2026".encode(), _bcrypt.gensalt()).decode()
        db.add(models.User(
            nome="Administrador",
            email="admin@smartfood.com",
            senha_hash=senha_hash,
            tipo_usuario="ADMIN",
        ))
        db.commit()
        print("Admin criado: admin@smartfood.com / smartfood2026")
        print("Troque a senha apos o primeiro login!")
    finally:
        db.close()

if __name__ == "__main__":
    seed_admin()
