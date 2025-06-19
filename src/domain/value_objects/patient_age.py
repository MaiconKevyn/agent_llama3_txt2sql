"""
Patient Age Value Object - Immutable representation of patient age with business logic
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PatientAge:
    """
    Value object representing patient age with age group classification
    and demographic analysis capabilities.
    
    This value object encapsulates age-related business rules and provides
    meaningful categorization for healthcare analytics.
    """
    value: int
    
    def __post_init__(self):
        """Validate age value after initialization"""
        if not isinstance(self.value, int):
            raise TypeError("Age must be an integer")
        
        if not (0 <= self.value <= 150):
            raise ValueError(f"Age must be between 0 and 150, got {self.value}")
    
    @property
    def age_group(self) -> str:
        """Classify age into broad demographic groups"""
        if self.value < 18:
            return "Menor"
        elif self.value < 65:
            return "Adulto"
        else:
            return "Idoso"
    
    @property
    def age_category_for_analysis(self) -> str:
        """Detailed age categorization for epidemiological analysis"""
        if self.value < 5:
            return "0-4"
        elif self.value < 15:
            return "5-14"
        elif self.value < 25:
            return "15-24"
        elif self.value < 35:
            return "25-34"
        elif self.value < 45:
            return "35-44"
        elif self.value < 55:
            return "45-54"
        elif self.value < 65:
            return "55-64"
        elif self.value < 75:
            return "65-74"
        elif self.value < 85:
            return "75-84"
        else:
            return "85+"
    
    @property
    def is_pediatric(self) -> bool:
        """Check if age falls in pediatric range (0-17 years)"""
        return self.value < 18
    
    @property
    def is_elderly(self) -> bool:
        """Check if age falls in elderly range (65+ years)"""
        return self.value >= 65
    
    @property
    def is_working_age(self) -> bool:
        """Check if age falls in typical working age range (18-64 years)"""
        return 18 <= self.value < 65
    
    @property
    def life_stage(self) -> str:
        """Determine life stage based on age"""
        if self.value < 1:
            return "Recém-nascido"
        elif self.value < 3:
            return "Bebê"
        elif self.value < 6:
            return "Pré-escolar"
        elif self.value < 12:
            return "Criança"
        elif self.value < 18:
            return "Adolescente"
        elif self.value < 30:
            return "Jovem adulto"
        elif self.value < 50:
            return "Adulto"
        elif self.value < 65:
            return "Adulto maduro"
        elif self.value < 80:
            return "Idoso"
        else:
            return "Idoso avançado"
    
    @property
    def risk_category(self) -> str:
        """Assess general health risk category based on age"""
        if self.value < 1:
            return "Alto risco (neonatal)"
        elif self.value < 5:
            return "Médio risco (infantil)"
        elif self.value < 65:
            return "Baixo risco (adulto)"
        elif self.value < 80:
            return "Médio risco (idoso)"
        else:
            return "Alto risco (idoso avançado)"
    
    def years_until_retirement(self, retirement_age: int = 65) -> int:
        """Calculate years until retirement age"""
        if self.value >= retirement_age:
            return 0
        return retirement_age - self.value
    
    def is_in_age_range(self, min_age: int, max_age: int) -> bool:
        """Check if age falls within specified range (inclusive)"""
        return min_age <= self.value <= max_age
    
    def compare_with(self, other_age: 'PatientAge') -> str:
        """Compare this age with another PatientAge"""
        difference = self.value - other_age.value
        
        if difference == 0:
            return "Mesma idade"
        elif difference > 0:
            return f"{difference} anos mais velho"
        else:
            return f"{abs(difference)} anos mais novo"
    
    def get_demographic_info(self) -> dict:
        """Get comprehensive demographic information"""
        return {
            "age": self.value,
            "age_group": self.age_group,
            "age_category": self.age_category_for_analysis,
            "life_stage": self.life_stage,
            "risk_category": self.risk_category,
            "is_pediatric": self.is_pediatric,
            "is_elderly": self.is_elderly,
            "is_working_age": self.is_working_age,
            "years_until_retirement": self.years_until_retirement()
        }