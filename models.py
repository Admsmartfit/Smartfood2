from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    unit = Column(String, nullable=False) # e.g., kg, L, un
    category = Column(String, default="Outros")

    manufacturers = relationship("IngredientManufacturer", back_populates="ingredient")
    catalog_entries = relationship("SupplierCatalog", back_populates="ingredient")

class IngredientManufacturer(Base):
    __tablename__ = "ingredient_manufacturers"

    id = Column(Integer, primary_key=True, index=True)
    brand_name = Column(String, index=True, nullable=False)
    yield_percentage = Column(Float, default=100.0) # 0 to 100
    quality_score = Column(Integer, default=5) # 1 to 5
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)

    ingredient = relationship("Ingredient", back_populates="manufacturers")
    catalog_entries = relationship("SupplierCatalog", back_populates="manufacturer")

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    contact_info = Column(String)

    catalog_entries = relationship("SupplierCatalog", back_populates="supplier")
    supplier_categories = relationship("SupplierCategory", back_populates="supplier",
                                       cascade="all, delete-orphan")


class SupplierCategory(Base):
    __tablename__ = "supplier_categories"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    category = Column(String, nullable=False)

    supplier = relationship("Supplier", back_populates="supplier_categories")

class SupplierCatalog(Base):
    __tablename__ = "supplier_catalog"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    manufacturer_id = Column(Integer, ForeignKey("ingredient_manufacturers.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    last_price = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    supplier = relationship("Supplier", back_populates="catalog_entries")
    manufacturer = relationship("IngredientManufacturer", back_populates="catalog_entries")
    ingredient = relationship("Ingredient", back_populates="catalog_entries")

class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(String)
    labor_cost = Column(Float, default=0.0)
    energy_cost = Column(Float, default=0.0)
    markup = Column(Float, default=1.0)
    
    margem_minima_pct = Column(Float, default=20.0)
    observacoes = Column(Text, default="")  # Equipamentos, configurações, notas gerais
    rendimento_unidades = Column(Integer, default=1)
    peso_porcao_g = Column(Float, default=0.0)

    sections = relationship("RecipeSection", back_populates="recipe")
    batches = relationship("ProductionBatch", back_populates="recipe")

class RecipeSection(Base):
    __tablename__ = "recipe_sections"

    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    name = Column(String, nullable=False) # e.g., 'Massa', 'Recheio'
    post_cooking_weight = Column(Float, default=0.0) # Peso final individual
    instrucoes = Column(Text, default="")  # Modo de preparo / forma de fazer

    recipe = relationship("Recipe", back_populates="sections")
    items = relationship("BOMItem", back_populates="section")

class BOMItem(Base):
    __tablename__ = "bom_items"

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("recipe_sections.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    correction_factor = Column(Float, default=1.0) # FC
    cooking_factor = Column(Float, default=1.0) # FCoc

    manufacturer_id = Column(Integer, ForeignKey("ingredient_manufacturers.id"), nullable=True)

    section = relationship("RecipeSection", back_populates="items")
    ingredient = relationship("Ingredient")
    manufacturer = relationship("IngredientManufacturer")


# ── Module 2: Labels ──────────────────────────────────────────────────────────

class LabelTemplate(Base):
    __tablename__ = "label_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    width_mm = Column(Float, nullable=False, default=62.0)
    height_mm = Column(Float, nullable=False, default=40.0)
    printer_type = Column(String, nullable=False, default="ZPL")   # ZPL | TSPL
    printer_ip = Column(String, default="")
    printer_port = Column(Integer, default=9100)
    # JSON array of field config objects
    fields_config = Column(Text, default="[]")

    batches = relationship("ProductionBatch", back_populates="label_template")


class ProductionBatch(Base):
    __tablename__ = "production_batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_number = Column(String, nullable=False, unique=True)
    product_name = Column(String, nullable=False)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=True)
    label_template_id = Column(Integer, ForeignKey("label_templates.id"), nullable=True)
    production_date = Column(DateTime, default=datetime.utcnow)
    expiry_date = Column(DateTime, nullable=False)
    weight_kg = Column(Float, default=0.0)
    ingredients_summary = Column(Text, default="")  # Short text printed on label
    tutorial_url = Column(String, default="")        # URL shown when product is fresh
    promo_url = Column(String, default="")           # URL shown near expiry date

    recipe = relationship("Recipe", back_populates="batches")
    label_template = relationship("LabelTemplate", back_populates="batches")
