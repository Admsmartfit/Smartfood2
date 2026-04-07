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
    current_stock = Column(Float, default=0.0)

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
    perda_desidratacao_pct = Column(Float, default=0.0)   # % weight loss in freezer
    markup_distribuicao = Column(Float, default=0.0)      # markup for distribution channel
    current_stock_units = Column(Integer, default=0)      # ready-to-sell frozen units

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
    display_unit = Column(String, default="")  # Unit chosen by user on screen (g, ml, etc.)

    manufacturer_id = Column(Integer, ForeignKey("ingredient_manufacturers.id"), nullable=True)

    section = relationship("RecipeSection", back_populates="items")
    ingredient = relationship("Ingredient")
    manufacturer = relationship("IngredientManufacturer")


# ── Module 3: Shopping Lists ─────────────────────────────────────────────────

class ShoppingList(Base):
    __tablename__ = "shopping_lists"

    id         = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    name       = Column(String, nullable=False)

    items = relationship("ShoppingListItem", back_populates="shopping_list",
                         cascade="all, delete-orphan")


class ShoppingListItem(Base):
    __tablename__ = "shopping_list_items"

    id            = Column(Integer, primary_key=True, index=True)
    list_id       = Column(Integer, ForeignKey("shopping_lists.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    qty           = Column(Float, nullable=False)

    shopping_list = relationship("ShoppingList", back_populates="items")
    ingredient    = relationship("Ingredient")


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


# ── Module 5: Stock Control ───────────────────────────────────────────────────

class StockMovement(Base):
    __tablename__ = "stock_movements"

    id          = Column(Integer, primary_key=True, index=True)
    type        = Column(String, nullable=False)   # 'IN' or 'OUT'
    item_type   = Column(String, nullable=False)   # 'INGREDIENT' or 'PRODUCT'
    item_id     = Column(Integer, nullable=False)
    quantity    = Column(Float, nullable=False)
    date        = Column(DateTime, default=datetime.utcnow)
    description = Column(String, default="")


# ── Module 6: Customers & Sales Orders ───────────────────────────────────────

class Customer(Base):
    __tablename__ = "customers"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, index=True, nullable=False)
    phone      = Column(String, default="")
    email      = Column(String, default="")
    address    = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    orders = relationship("SalesOrder", back_populates="customer",
                          cascade="all, delete-orphan")


class SalesOrder(Base):
    __tablename__ = "sales_orders"

    id           = Column(Integer, primary_key=True, index=True)
    customer_id  = Column(Integer, ForeignKey("customers.id"), nullable=False)
    order_date   = Column(DateTime, default=datetime.utcnow)
    status       = Column(String, default="PENDING")  # PENDING | DELIVERED | CANCELED
    total_amount = Column(Float, default=0.0)
    notes        = Column(Text, default="")

    customer = relationship("Customer", back_populates="orders")
    items    = relationship("SalesOrderItem", back_populates="order",
                            cascade="all, delete-orphan")


class SalesOrderItem(Base):
    __tablename__ = "sales_order_items"

    id         = Column(Integer, primary_key=True, index=True)
    order_id   = Column(Integer, ForeignKey("sales_orders.id"), nullable=False)
    recipe_id  = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    quantity   = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)

    order  = relationship("SalesOrder", back_populates="items")
    recipe = relationship("Recipe")
