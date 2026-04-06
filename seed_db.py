from database import SessionLocal, engine
from models import Base, Ingredient, IngredientManufacturer

# Data structure provided by the user
seeds = {
    "Outros": {
        "Água": {"unit": "L", "brands": [("Rede Pública", 100, 5)]},
        "Óleo de Soja": {"unit": "L", "brands": [("Liza", 100, 5), ("Soya", 100, 4)]}
    },
    "Carnes": {
        "Peito de Frango": {"unit": "kg", "brands": [("Sadia", 75, 5), ("Perdigão", 75, 5), ("Copacol", 78, 4)]},
        "Carne Moída Bovina": {"unit": "kg", "brands": [("Friboi", 100, 5), ("Minerva", 100, 4)]},
        "Pernil Suíno Desossado": {"unit": "kg", "brands": [("Aurora", 85, 5), ("Seara", 85, 4)]}
    },
    "Carboidratos": {
        "Farinha de Trigo": {"unit": "kg", "brands": [("Suprema", 100, 5), ("Dona Benta", 100, 5), ("Coamo", 100, 4)]},
        "Farinha Panko": {"unit": "kg", "brands": [("Kenko", 100, 5), ("Alfa", 100, 4)]}
    },
    "Laticínios": {
        "Requeijão Culinário": {"unit": "kg", "brands": [("Catupiry", 100, 5), ("Scala", 100, 5)]},
        "Queijo Mussarela": {"unit": "kg", "brands": [("Tirol", 100, 5), ("Italac", 100, 4)]},
        "Margarina": {"unit": "kg", "brands": [("Qualy", 100, 5), ("Primor", 100, 4)]}
    },
    "Vegetais": {
        "Cebola Branca": {"unit": "kg", "brands": [("In Natura", 85, 4)]},
        "Cheiro Verde": {"unit": "kg", "brands": [("In Natura", 80, 4)]}
    },
    "Temperos": {
        "Sal Refinado": {"unit": "kg", "brands": [("Cisne", 100, 5), ("Lebre", 100, 4)]},
        "Alho Descascado": {"unit": "kg", "brands": [("Genérico", 100, 4)]},
        "Pimenta do Reino Pó": {"unit": "kg", "brands": [("Kitano", 100, 5), ("Hikari", 100, 4)]},
        "Caldo de Galinha Pó": {"unit": "kg", "brands": [("Knorr", 100, 5), ("Maggi", 100, 5)]}
    }
}

def seed():
    db = SessionLocal()
    # Optional: Ensure tables exist
    # Base.metadata.create_all(bind=engine)
    
    try:
        for category, items in seeds.items():
            for ing_name, data in items.items():
                # Step 1: Handle Ingredient
                ingredient = db.query(Ingredient).filter(Ingredient.name == ing_name).first()
                if not ingredient:
                    ingredient = Ingredient(
                        name=ing_name,
                        unit=data["unit"],
                        category=category
                    )
                    db.add(ingredient)
                    db.commit()
                    db.refresh(ingredient)
                
                # Step 2: Handle Brands
                for brand_name, yield_pct, quality in data["brands"]:
                    brand = db.query(IngredientManufacturer).filter(
                        IngredientManufacturer.ingredient_id == ingredient.id,
                        IngredientManufacturer.brand_name == brand_name
                    ).first()
                    
                    if not brand:
                        brand = IngredientManufacturer(
                            brand_name=brand_name,
                            yield_percentage=yield_pct,
                            quality_score=quality,
                            ingredient_id=ingredient.id
                        )
                        db.add(brand)
                        db.commit()
                        
        print("✅ Carga inicial de Insumos e Marcas concluída!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Erro durante a carga inicial: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
