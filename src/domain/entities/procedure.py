"""
Procedure Entity - Represents medical procedures performed in the SUS system
"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, date
from decimal import Decimal


@dataclass(frozen=True)
class Procedure:
    """
    Procedure entity representing medical procedures in the SUS healthcare system
    
    Encapsulates procedure codes, costs, timing, and complexity analysis
    according to SUS (Sistema Único de Saúde) standards.
    """
    procedure_code: str
    total_cost: Decimal
    admission_date: str  # Format: YYYYMMDD
    discharge_date: str  # Format: YYYYMMDD
    icu_days: int
    facility_code: str  # CNES code
    
    def __post_init__(self):
        """Validate procedure data after initialization"""
        self._validate()
    
    def _validate(self):
        """Validate procedure data for business rules"""
        if not self.procedure_code or not self.procedure_code.strip():
            raise ValueError("Procedure code cannot be empty")
        
        if self.total_cost < 0:
            raise ValueError(f"Total cost cannot be negative: {self.total_cost}")
        
        if self.icu_days < 0:
            raise ValueError(f"ICU days cannot be negative: {self.icu_days}")
        
        if not self._is_valid_date_format(self.admission_date):
            raise ValueError(f"Invalid admission date format: {self.admission_date}")
        
        if not self._is_valid_date_format(self.discharge_date):
            raise ValueError(f"Invalid discharge date format: {self.discharge_date}")
        
        # Check if discharge is after admission
        if self.admission_date and self.discharge_date:
            if self.discharge_date < self.admission_date:
                raise ValueError("Discharge date cannot be before admission date")
    
    def _is_valid_date_format(self, date_str: str) -> bool:
        """Validate date format YYYYMMDD"""
        if not date_str or len(date_str) != 8:
            return False
        
        try:
            year = int(date_str[:4])
            month = int(date_str[4:6])
            day = int(date_str[6:8])
            
            # Basic validation
            if not (1900 <= year <= 2100):
                return False
            if not (1 <= month <= 12):
                return False
            if not (1 <= day <= 31):
                return False
            
            # Try to create actual date to validate
            datetime(year, month, day)
            return True
        except (ValueError, TypeError):
            return False
    
    @property
    def length_of_stay(self) -> int:
        """Calculate length of stay in days"""
        try:
            admission = datetime.strptime(self.admission_date, "%Y%m%d")
            discharge = datetime.strptime(self.discharge_date, "%Y%m%d")
            return (discharge - admission).days
        except ValueError:
            return 0
    
    @property
    def cost_category(self) -> str:
        """Categorize procedure by cost"""
        cost_float = float(self.total_cost)
        
        if cost_float == 0:
            return "Sem custo"
        elif cost_float < 100:
            return "Baixo custo"
        elif cost_float < 1000:
            return "Custo moderado"
        elif cost_float < 5000:
            return "Alto custo"
        else:
            return "Custo muito alto"
    
    @property
    def complexity_level(self) -> str:
        """Determine procedure complexity based on ICU days and length of stay"""
        if self.icu_days > 0:
            if self.icu_days >= 7:
                return "Alta complexidade (UTI prolongada)"
            else:
                return "Média complexidade (UTI)"
        
        los = self.length_of_stay
        if los == 0:
            return "Ambulatorial"
        elif los == 1:
            return "Baixa complexidade (1 dia)"
        elif los <= 3:
            return "Baixa complexidade"
        elif los <= 7:
            return "Média complexidade"
        else:
            return "Alta complexidade (internação prolongada)"
    
    @property
    def requires_intensive_care(self) -> bool:
        """Check if procedure required intensive care"""
        return self.icu_days > 0
    
    @property
    def is_high_cost(self) -> bool:
        """Check if procedure is considered high cost"""
        return float(self.total_cost) >= 1000
    
    @property
    def is_emergency_indicator(self) -> bool:
        """Indicate if procedure might be emergency based on patterns"""
        # Emergency indicators: same day admission/discharge or ICU involvement
        return self.length_of_stay == 0 or self.icu_days > 0
    
    def get_admission_date_formatted(self) -> str:
        """Get formatted admission date"""
        try:
            date_obj = datetime.strptime(self.admission_date, "%Y%m%d")
            return date_obj.strftime("%d/%m/%Y")
        except ValueError:
            return self.admission_date
    
    def get_discharge_date_formatted(self) -> str:
        """Get formatted discharge date"""
        try:
            date_obj = datetime.strptime(self.discharge_date, "%Y%m%d")
            return date_obj.strftime("%d/%m/%Y")
        except ValueError:
            return self.discharge_date
    
    def calculate_daily_cost(self) -> Decimal:
        """Calculate average daily cost"""
        los = self.length_of_stay
        if los <= 0:
            return self.total_cost  # Same day or invalid dates
        return self.total_cost / los
    
    def get_procedure_summary(self) -> dict:
        """Get complete procedure summary"""
        return {
            "procedure_code": self.procedure_code,
            "total_cost": float(self.total_cost),
            "cost_category": self.cost_category,
            "length_of_stay": self.length_of_stay,
            "icu_days": self.icu_days,
            "complexity": self.complexity_level,
            "requires_icu": self.requires_intensive_care,
            "is_high_cost": self.is_high_cost,
            "is_emergency": self.is_emergency_indicator,
            "admission_date": self.get_admission_date_formatted(),
            "discharge_date": self.get_discharge_date_formatted(),
            "daily_cost": float(self.calculate_daily_cost()),
            "facility_code": self.facility_code
        }
    
    def compare_cost_with(self, other_procedure: 'Procedure') -> str:
        """Compare cost with another procedure"""
        cost_diff = self.total_cost - other_procedure.total_cost
        
        if cost_diff == 0:
            return "Mesmo custo"
        elif cost_diff > 0:
            percentage = (cost_diff / other_procedure.total_cost) * 100
            return f"{percentage:.1f}% mais caro"
        else:
            percentage = (abs(cost_diff) / self.total_cost) * 100
            return f"{percentage:.1f}% mais barato"