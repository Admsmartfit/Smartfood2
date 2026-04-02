class CostCalculator:
    @staticmethod
    def calculate_ingredient_real_cost(base_price_per_kg: float, fc: float, fcoc: float) -> float:
        """
        Custo Real Insumo = (Preço/kg * FC) / FCoc
        Calcula o custo por kg considerando as perdas e ganhos nas etapas.
        """
        if fcoc == 0:
            return 0.0
        return (base_price_per_kg * fc) / fcoc

    @staticmethod
    def calculate_item_cost(quantity: float, real_cost_per_kg: float) -> float:
        """Calcula o custo proporcional à quantidade."""
        return quantity * real_cost_per_kg

    @staticmethod
    def calculate_suggested_price(total_cost: float, labor_cost: float, energy_cost: float, markup: float) -> float:
        """
        Preço Sugerido = (Custo Total + Labor Cost + Energia) * Markup
        """
        return (total_cost + labor_cost + energy_cost) * markup

    @staticmethod
    def calculate_profit_margin(suggested_price: float, total_cost: float) -> float:
        """Calcula a margem em porcentagem."""
        if suggested_price == 0:
            return 0.0
        return ((suggested_price - total_cost) / suggested_price) * 100
